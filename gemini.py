"""Gemini client. Every request goes through ONE gate that
 - spaces requests apart (free tier friendly),
 - obeys 429 'retry in Ns' answers with a shared cooldown (no hammering),
 - falls back to a lighter model when the main one is overloaded,
 - never raises 'raw' HTTP errors into the rest of the app.
It only talks to Gemini when something asks it to (build course / grade / chat / test)."""
import os, re, json, time, threading
import requests

BASE = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")


class GeminiError(Exception):
    def __init__(self, message, kind="error", retry_after=0):
        super().__init__(message)
        self.kind = kind            # nokey auth bad rate quota_day overloaded network empty cancelled error
        self.retry_after = retry_after
        self.partial = False        # True if text had already been streamed out


def _next_reset():
    """Free-tier daily quotas reset at midnight Pacific time."""
    try:
        import datetime as dt
        from zoneinfo import ZoneInfo
        now = dt.datetime.now(ZoneInfo("America/Los_Angeles"))
        return (now + dt.timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0).timestamp()
    except Exception:
        return time.time() + 6 * 3600


class Gate:
    def __init__(self):
        self._lock = threading.Lock()
        self._next_slot = 0.0
        self.cooldown_until = 0.0
        self.state, self.message, self.last_ok = "unknown", "", 0.0
        self.recent = []
        self.model_used = ""
        self.model_pref = ""          # model chosen in the website (empty = .env / default)
        self.exhausted = {}           # model -> time when its DAILY quota is back
        self.offline = False          # user pressed 'disconnect': NO request leaves the computer

    # ---- config (read lazily so .env loading order does not matter)
    def gap(self, model):             # free tier: flash ~5 requests/min, flash-lite ~15 requests/min
        env = os.environ.get("GEMINI_MIN_GAP", "").strip()
        if env:
            try: return float(env)
            except ValueError: pass
        return 4.0 if "lite" in model else 12.0
    def key(self): return os.environ.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    def primary(self): return self.model_pref or os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

    def fallback(self):
        f = os.environ.get("GEMINI_FALLBACK_MODEL", "").strip()
        if f and f != self.primary(): return f
        return "gemini-flash-latest" if "lite" in self.primary() else "gemini-flash-lite-latest"

    def _avail(self):
        now = time.time()
        return [m for m in (self.primary(), self.fallback()) if self.exhausted.get(m, 0) <= now]

    def list_models(self):
        if self.offline: raise GeminiError("offline mode", "offline")
        if not self.key(): raise GeminiError("No API key", "nokey")
        try: r = requests.get(f"{BASE}/models?pageSize=200", headers={"x-goog-api-key": self.key()}, timeout=(10, 30))
        except requests.RequestException as e: raise GeminiError(str(e)[:200], "network")
        if r.status_code != 200: self._raise_http(r)
        out = []
        for m in r.json().get("models", []):
            n = str(m.get("name", "")).replace("models/", "")
            if n.startswith("gemini") and "generateContent" in (m.get("supportedGenerationMethods") or []) and not re.search(r"embed|image|tts|live|audio|vision|aqa", n):
                out.append(n)
        return sorted(set(out))

    def reset(self):
        self.cooldown_until = 0.0
        self._set("unknown", "")

    # ---- status for the UI
    def _set(self, state, message=""):
        self.state, self.message = state, message

    def status(self):
        now = time.time()
        left = max(0, int(self.cooldown_until - now + 0.99))
        state = self.state
        if self.offline:
            return {"state": "offline", "message": "", "cooldown_left": 0, "per_minute": 0,
                    "model": self.model_used or self.primary(), "last_ok": self.last_ok,
                    "primary": self.primary(), "fallback": self.fallback(), "exhausted": []}
        if not self._avail(): state = "quota"
        elif state == "quota": state = "ok"
        if left and state not in ("nokey", "auth", "quota"):
            state = "cooling"
        if not self.key():
            state = "nokey"
        return {"state": state, "message": self.message[:240], "cooldown_left": left,
                "per_minute": len([t for t in self.recent if t > now - 60]),
                "model": self.model_used or self.primary(), "last_ok": self.last_ok,
                "primary": self.primary(), "fallback": self.fallback(),
                "exhausted": [m for m, u in self.exhausted.items() if u > now]}

    # ---- pacing
    def _wait_slot(self, cancel, gap):
        with self._lock:
            slot = max(time.time(), self._next_slot, self.cooldown_until)
            self._next_slot = slot + gap
        while time.time() < max(slot, self.cooldown_until):
            if self.offline:
                raise GeminiError("offline mode", "offline")
            if cancel and cancel():
                raise GeminiError("cancelled", "cancelled")
            time.sleep(0.4)
        self.recent = [t for t in self.recent if t > time.time() - 60] + [time.time()]

    # ---- request building
    @staticmethod
    def _contents(prompt):
        if isinstance(prompt, str):
            return [{"role": "user", "parts": [{"text": prompt}]}]
        return prompt

    def _body(self, prompt, system, json_mode, max_tokens, temperature=0.4):
        gc = {"temperature": temperature}
        if json_mode: gc["responseMimeType"] = "application/json"
        if max_tokens: gc["maxOutputTokens"] = max_tokens
        tb = os.environ.get("GEMINI_THINKING_BUDGET", "")
        if tb.lstrip("-").isdigit(): gc["thinkingConfig"] = {"thinkingBudget": int(tb)}
        body = {"contents": self._contents(prompt), "generationConfig": gc}
        if system: body["systemInstruction"] = {"parts": [{"text": system}]}
        return body

    @staticmethod
    def _extract(obj):
        out = []
        for cand in (obj.get("candidates") or [])[:1]:
            for p in (cand.get("content") or {}).get("parts") or []:
                if p.get("text") and not p.get("thought"):
                    out.append(p["text"])
        return "".join(out)

    @staticmethod
    def _raise_http(r):
        try: err = r.json().get("error", {})
        except Exception: err = {}
        msg = err.get("message") or r.text[:200] or f"HTTP {r.status_code}"
        code = r.status_code
        if code == 429:
            delay = 0.0
            for d in err.get("details", []) or []:
                rd = d.get("retryDelay")
                if rd:
                    try: delay = float(str(rd).rstrip("s"))
                    except ValueError: pass
            m = re.search(r"retry in ([\d.]+)\s*s", msg, re.I)
            if not delay and m: delay = float(m.group(1))
            daily = "perday" in json.dumps(err).lower().replace(" ", "").replace("_", "") or "per day" in msg.lower()
            raise GeminiError(msg, "quota_day" if daily else "rate", delay)
        if code in (500, 502, 503, 504):
            raise GeminiError(msg, "overloaded")
        if code in (401, 403) or (code == 400 and "api key" in msg.lower()):
            raise GeminiError(msg, "auth")
        if code in (400, 404):
            raise GeminiError(msg, "bad")
        raise GeminiError(msg, "error")

    def _call(self, model, body, on_text):
        stream = on_text is not None
        url = f"{BASE}/models/{model}:" + ("streamGenerateContent?alt=sse" if stream else "generateContent")
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.key()}
        try:
            r = requests.post(url, headers=headers, json=body, stream=stream, timeout=(10, 120))
        except requests.RequestException as e:
            raise GeminiError(str(e)[:200], "network")
        if r.status_code != 200:
            self._raise_http(r)
        if not stream:
            text = self._extract(r.json())
            if not text: raise GeminiError("Empty answer from AI", "empty")
            return text
        r.encoding = "utf-8"
        got = ""
        try:
            for line in r.iter_lines(decode_unicode=True):
                if self.offline:
                    err = GeminiError("offline mode", "offline"); err.partial = bool(got); raise err
                if not line or not line.startswith("data:"): continue
                data = line[5:].strip()
                if not data or data == "[DONE]": continue
                piece = self._extract(json.loads(data))
                if piece:
                    got += piece
                    on_text(piece)
        except GeminiError:
            raise
        except (requests.RequestException, ValueError) as e:
            err = GeminiError(str(e)[:200], "network"); err.partial = bool(got); raise err
        finally:
            r.close()
        if not got: raise GeminiError("Empty answer from AI", "empty")
        return got

    # ---- public
    def generate(self, prompt, system=None, json_mode=False, max_tokens=None,
                 on_text=None, cancel=None, attempts=5, temperature=0.4):
        if self.offline:
            raise GeminiError("offline mode", "offline")
        if not self.key():
            self._set("nokey", "GEMINI_API_KEY is missing (.env)")
            raise GeminiError("No API key", "nokey")
        body = self._body(prompt, system, json_mode, max_tokens, temperature)
        last = None
        for i in range(attempts):
            avail = self._avail()
            if not avail:
                self._set("quota", "daily quota used up for all models")
                raise GeminiError("daily quota used up for all models", "quota_day")
            model = avail[1] if (i >= 2 and len(avail) > 1) else avail[0]
            self._wait_slot(cancel, self.gap(model))
            try:
                text = self._call(model, body, on_text)
                self.model_used = model; self.last_ok = time.time()
                self._set("ok", "")
                return text
            except GeminiError as e:
                last = e
                if e.kind == "offline": raise
                if e.kind in ("nokey", "auth", "bad"):
                    self._set("auth" if e.kind != "bad" else "error", str(e)); raise
                if e.kind == "quota_day":
                    self.exhausted[model] = _next_reset()      # this model is done for today -> try the other one
                    if self._avail(): continue
                    self._set("quota", str(e)); raise
                if e.partial: raise
                if e.kind == "rate":
                    d = min(max(e.retry_after + 1, 12 * (i + 1)), 90)
                    self.cooldown_until = max(self.cooldown_until, time.time() + d)
                    self._set("cooling", str(e))
                else:
                    self._set("error", str(e))
                    time.sleep(min(3 * (i + 1), 12))
        raise last

    def test(self):
        try:
            self.generate("Reply with the single word OK.", attempts=2)
        except GeminiError:
            pass
        return self.status()


gate = Gate()
