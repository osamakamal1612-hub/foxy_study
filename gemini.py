"""Gemini client. One Gate per API key (every key = its own quota), each gate
 - spaces requests apart, obeys 429 'retry in Ns' with a shared cooldown,
 - switches to the other model when one model's quota is used up / unavailable,
 - never raises raw HTTP errors into the rest of the app.
It only talks to Gemini when something asks it to."""
import os, re, json, time, threading, hashlib
import requests

BASE = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
AUTO_QUALITY = "gemini-flash-latest"        # better lessons, small free daily quota
AUTO_CHEAP = "gemini-flash-lite-latest"     # much bigger free quota -> grading and chat
SKIP_MODELS = re.compile(r"embed|image|tts|live|audio|vision|aqa|computer|robotics|research|learnlm|gemma|nano|banana|veo|imagen")


class GeminiError(Exception):
    def __init__(self, message, kind="error", retry_after=0):
        super().__init__(message)
        self.kind = kind            # nokey auth bad rate quota_day overloaded network empty cancelled offline error
        self.retry_after = retry_after
        self.partial = False


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
    def __init__(self, key):
        self.key = key
        self._lock = threading.Lock()
        self._next_slot = 0.0
        self.cooldown_until = 0.0
        self.state, self.message, self.last_ok = "unknown", "", 0.0
        self.recent = []
        self.model_used = ""
        self.exhausted = {}            # model -> time when it is usable again

    # ---- models
    def gap(self, model):              # free tier: flash ~5 req/min, flash-lite ~15 req/min
        env = os.environ.get("GEMINI_MIN_GAP", "").strip()
        if env:
            try: return float(env)
            except ValueError: pass
        return 4.0 if "lite" in model else 12.0

    def fallback(self, pref=""):
        if not pref: return AUTO_CHEAP
        f = os.environ.get("GEMINI_FALLBACK_MODEL", "").strip()
        if f and f != pref: return f
        return AUTO_QUALITY if "lite" in pref else AUTO_CHEAP

    def _order(self, pref, prefer):
        """Auto (nothing chosen): Flash for building lessons, Flash-Lite for grading/chat, each the other's backup."""
        if pref: return [pref, self.fallback(pref)]
        return [AUTO_QUALITY, AUTO_CHEAP] if prefer == "quality" else [AUTO_CHEAP, AUTO_QUALITY]

    def _avail(self, pref="", prefer="quality"):
        now = time.time()
        return [m for m in self._order(pref, prefer) if self.exhausted.get(m, 0) <= now]

    def list_models(self, offline=False):
        if offline: raise GeminiError("offline mode", "offline")
        if not self.key: raise GeminiError("No API key", "nokey")
        try: r = requests.get(f"{BASE}/models?pageSize=200", headers={"x-goog-api-key": self.key}, timeout=(10, 30))
        except requests.RequestException as e: raise GeminiError(str(e)[:200], "network")
        if r.status_code != 200: self._raise_http(r)
        out = []
        for m in r.json().get("models", []):
            n = str(m.get("name", "")).replace("models/", "")
            if n.startswith("gemini") and "generateContent" in (m.get("supportedGenerationMethods") or []) and not SKIP_MODELS.search(n):
                out.append(n)
        return sorted(set(out))

    # ---- status for the UI
    def status(self, pref="", offline=False):
        now = time.time(); left = max(0, int(self.cooldown_until - now + 0.99))
        base = {"cooldown_left": 0, "per_minute": len([t for t in self.recent if t > now - 60]), "model": self.model_used or pref or AUTO_QUALITY,
                "last_ok": self.last_ok, "primary": pref, "mode": "manual" if pref else "auto", "fallback": self.fallback(pref),
                "exhausted": [m for m, u in self.exhausted.items() if u > now], "message": self.message[:240]}
        if offline: return {**base, "state": "offline", "message": ""}
        state = self.state
        if not self._avail(pref): state = "quota"
        elif state == "quota": state = "ok"
        if left and state not in ("nokey", "auth", "quota"): state = "cooling"
        if not self.key: state = "nokey"
        return {**base, "state": state, "cooldown_left": left}

    def _set(self, state, message=""):
        self.state, self.message = state, message

    # ---- pacing
    def _wait_slot(self, cancel, gap, off):
        with self._lock:
            slot = max(time.time(), self._next_slot, self.cooldown_until)
            self._next_slot = slot + gap
        while time.time() < max(slot, self.cooldown_until):
            if off(): raise GeminiError("offline mode", "offline")
            if cancel and cancel(): raise GeminiError("cancelled", "cancelled")
            time.sleep(0.4)
        self.recent = [t for t in self.recent if t > time.time() - 60] + [time.time()]

    # ---- request building
    @staticmethod
    def _contents(prompt):
        return [{"role": "user", "parts": [{"text": prompt}]}] if isinstance(prompt, str) else prompt

    def _body(self, prompt, system, json_mode, max_tokens, temperature):
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
                if p.get("text") and not p.get("thought"): out.append(p["text"])
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
        if code in (500, 502, 503, 504): raise GeminiError(msg, "overloaded")
        if code in (401, 403) or (code == 400 and "api key" in msg.lower()): raise GeminiError(msg, "auth")
        if code in (400, 404): raise GeminiError(msg, "bad")
        raise GeminiError(msg, "error")

    def _call(self, model, body, on_text, off):
        stream = on_text is not None
        url = f"{BASE}/models/{model}:" + ("streamGenerateContent?alt=sse" if stream else "generateContent")
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.key}
        try: r = requests.post(url, headers=headers, json=body, stream=stream, timeout=(10, 120))
        except requests.RequestException as e: raise GeminiError(str(e)[:200], "network")
        if r.status_code != 200: self._raise_http(r)
        if not stream:
            text = self._extract(r.json())
            if not text: raise GeminiError("Empty answer from AI", "empty")
            return text
        r.encoding = "utf-8"; got = ""
        try:
            for line in r.iter_lines(decode_unicode=True):
                if off():
                    err = GeminiError("offline mode", "offline"); err.partial = bool(got); raise err
                if not line or not line.startswith("data:"): continue
                data = line[5:].strip()
                if not data or data == "[DONE]": continue
                piece = self._extract(json.loads(data))
                if piece: got += piece; on_text(piece)
        except GeminiError: raise
        except (requests.RequestException, ValueError) as e:
            err = GeminiError(str(e)[:200], "network"); err.partial = bool(got); raise err
        finally: r.close()
        if not got: raise GeminiError("Empty answer from AI", "empty")
        return got

    # ---- public
    def generate(self, prompt, system=None, json_mode=False, max_tokens=None, on_text=None, cancel=None,
                 attempts=5, temperature=0.4, prefer="quality", pref="", offline=None):
        off = (lambda: bool(offline())) if callable(offline) else (lambda: bool(offline))
        if off(): raise GeminiError("offline mode", "offline")
        if not self.key:
            self._set("nokey", "No API key"); raise GeminiError("No API key", "nokey")
        body = self._body(prompt, system, json_mode, max_tokens, temperature)
        last = None
        for i in range(attempts):
            avail = self._avail(pref, prefer)
            if not avail:
                self._set("quota", "daily quota used up for all models")
                raise GeminiError("daily quota used up for all models", "quota_day")
            model = avail[1] if (i >= 2 and len(avail) > 1) else avail[0]
            self._wait_slot(cancel, self.gap(model), off)
            try:
                text = self._call(model, body, on_text, off)
                self.model_used = model; self.last_ok = time.time(); self._set("ok", "")
                return text
            except GeminiError as e:
                last = e
                if e.kind == "offline": raise
                if e.kind in ("nokey", "auth"): self._set("auth", str(e)); raise
                if e.kind == "bad":                                   # unknown / retired model -> try the other one
                    self.exhausted[model] = time.time() + 3600
                    if self._avail(pref, prefer): continue
                    self._set("error", str(e)); raise
                if e.kind == "quota_day":
                    self.exhausted[model] = _next_reset()
                    if self._avail(pref, prefer): continue
                    self._set("quota", str(e)); raise
                if e.partial: raise
                if e.kind == "rate":
                    d = min(max(e.retry_after + 1, 12 * (i + 1)), 90)
                    self.cooldown_until = max(self.cooldown_until, time.time() + d)
                    self._set("cooling", str(e))
                else:
                    self._set("error", str(e)); time.sleep(min(3 * (i + 1), 12))
        raise last

    def test(self, pref="", offline=None):
        try: self.generate("Reply with the single word OK.", attempts=2, prefer="cheap", pref=pref, offline=offline)
        except GeminiError: pass
        return self.status(pref, bool(offline() if callable(offline) else offline))


_gates, _glock = {}, threading.Lock()


def gate_for(key):
    key = (key or "").strip()
    h = hashlib.sha256(key.encode()).hexdigest() if key else "none"
    with _glock:
        if h not in _gates: _gates[h] = Gate(key)
        return _gates[h]
