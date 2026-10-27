"""Course engine: storage, background worker, course building, grading, rewards."""
import os, re, json, time, uuid, random, shutil, threading, heapq, itertools, queue, traceback
from pathlib import Path
from gemini import gate, GeminiError

ROOT = Path(__file__).parent
_ENV_KEY = os.environ.get("GEMINI_API_KEY", "")      # key from .env / environment (fallback)
DATA = ROOT / "data"
LDIR = DATA / "lessons"
LDIR.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()
LANG_NAME = {"tr": "Turkish", "ar": "Arabic"}
MASCOT_NAME = {"fox": "Foxy", "panda": "Pandi", "robot": "Robo"}
MASCOT_LOOK = {"fox": "a cheerful fox", "panda": "a sleepy-but-kind panda", "robot": "a friendly little robot"}


def _write(path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _read(path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default


# ------------------------------------------------------------------ settings / stats
SETTINGS_F = DATA / "settings.json"
S = _read(SETTINGS_F, {})
S.setdefault("lang", "tr"); S.setdefault("mascot", "fox"); S.setdefault("sound", True)
S.setdefault("active", None); S.setdefault("offline", False); S.setdefault("model", ""); S.setdefault("notifications", []); S.setdefault("nid", 0)
S.setdefault("stats", {"xp": 0, "gems": 0, "streak": 0, "last_day": "", "daily_xp": 0,
                       "hearts": 5, "hearts_ts": time.time(), "badges": []})


gate.offline = bool(S.get("offline"))
gate.model_pref = str(S.get("model") or "")
PASS = 75


def save_settings():
    with LOCK: _write(SETTINGS_F, S)


def notify(kind, **data):
    with LOCK:
        S["nid"] += 1
        S["notifications"].append({"id": S["nid"], "kind": kind, "ts": time.time(), "read": False, **data})
        S["notifications"] = S["notifications"][-60:]
        save_settings()


def _enotify(**kw):
    if kw.get("kind") != "offline": notify("error", **kw)


def _day(offset=0): return time.strftime("%Y-%m-%d", time.localtime(time.time() - offset * 86400))


def touch_streak():
    st = S["stats"]
    if st["last_day"] == _day(): return
    st["streak"] = st["streak"] + 1 if st["last_day"] == _day(1) else 1
    st["last_day"] = _day(); st["daily_xp"] = 0


def give_badge(bid):
    st = S["stats"]
    if bid not in st["badges"]:
        st["badges"].append(bid); notify("badge", badge=bid)


def add_xp(xp, gems=0):
    st = S["stats"]
    touch_streak()
    st["xp"] += xp; st["gems"] += gems; st["daily_xp"] += xp
    if st["xp"] >= 100: give_badge("xp100")
    if st["xp"] >= 500: give_badge("xp500")
    if st["streak"] >= 3: give_badge("streak3")
    if st["streak"] >= 7: give_badge("streak7")


def regen_hearts():
    st = S["stats"]; now = time.time()
    if st["hearts"] >= 5: st["hearts"] = 5; st["hearts_ts"] = now; return
    while st["hearts"] < 5 and now - st["hearts_ts"] >= 900:
        st["hearts"] += 1; st["hearts_ts"] += 900


# ------------------------------------------------------------------ API key chosen from the website
SECRET_F = DATA / "secret.json"


def load_secret():
    k = str(_read(SECRET_F, {}).get("GEMINI_API_KEY", "")).strip()
    if k: os.environ["GEMINI_API_KEY"] = k


def set_key(k):
    """Save the key typed in the site (empty = remove it and fall back to .env)."""
    k = (k or "").strip().strip('"').strip("'")
    if k:
        SECRET_F.write_text(json.dumps({"GEMINI_API_KEY": k}), encoding="utf-8")
        try: os.chmod(SECRET_F, 0o600)
        except OSError: pass
        os.environ["GEMINI_API_KEY"] = k
    else:
        SECRET_F.unlink(missing_ok=True)
        if _ENV_KEY: os.environ["GEMINI_API_KEY"] = _ENV_KEY
        else: os.environ.pop("GEMINI_API_KEY", None)
    gate.reset()


def resume_paused():
    """A new key arrived: restart everything that stopped because of the old one."""
    for lid, L in list(LES.items()):
        if L["course"]["status"] == "paused" and not L["course"]["stages"]: retry(lid, "analyze")
        retry(lid, "stage"); retry(lid, "grade")


# ------------------------------------------------------------------ lessons store
LES = {}


def _empty_progress(): return {"read": {}, "answers": {}, "exams": [], "stage_done": {}, "chests": {}}


def load_all():
    for d in sorted(LDIR.iterdir()):
        c = _read(d / "course.json", None) if d.is_dir() else None
        if c:
            LES[d.name] = {"course": c, "progress": _read(d / "progress.json", _empty_progress())}


def save_course(lid):
    with LOCK:
        if lid in LES: _write(LDIR / lid / "course.json", LES[lid]["course"])


def save_progress(lid):
    with LOCK:
        if lid in LES: _write(LDIR / lid / "progress.json", LES[lid]["progress"])


def split_questions(text):
    text = text.replace("\r", "")
    pat = re.compile(r"^\s*(?:soru\s*)?\(?\d{1,3}\s*[\.\)\-:]\s*(.+)", re.I)
    items, cur = [], None
    for line in text.split("\n"):
        m = pat.match(line)
        if m:
            cur = [m.group(1).strip()]; items.append(cur)
        elif cur is not None and line.strip():
            cur.append(line.strip())
    items = [" ".join(x) for x in items]
    if len(items) < 2:
        items = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(items) < 2:
        items = [l.strip() for l in text.split("\n") if l.strip()]
    return [q[:600] for q in items if len(q) > 3][:200]


def create_lesson(title, qtext, ntext):
    lid = uuid.uuid4().hex[:8]
    qs = split_questions(qtext)
    if not qs: raise ValueError("no_questions")
    if len(ntext.strip()) < 40: raise ValueError("no_notes")
    course = {"id": lid, "title": title or "Yeni ders", "custom_title": bool(title), "created": time.time(),
              "status": "analyzing", "error": None, "lang": None,
              "questions": [{"id": i + 1, "text": q} for i, q in enumerate(qs)], "stages": []}
    (LDIR / lid).mkdir(parents=True)
    (LDIR / lid / "notes.txt").write_text(ntext, encoding="utf-8")
    with LOCK:
        LES[lid] = {"course": course, "progress": _empty_progress()}
        S["active"] = lid
    save_course(lid); save_progress(lid); save_settings()
    WORKER.add(("analyze", lid), 1)
    return lid


def delete_lesson(lid):
    with LOCK:
        LES.pop(lid, None)
        if S["active"] == lid:
            S["active"] = next(iter(sorted(LES, key=lambda i: -LES[i]["course"]["created"])), None)
        save_settings()
    shutil.rmtree(LDIR / lid, ignore_errors=True)


# ------------------------------------------------------------------ AI helpers
def parse_json(raw):
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try: return json.loads(raw)
    except Exception: pass
    a, b = raw.find("{"), raw.rfind("}")
    if a >= 0 and b > a:
        try: return json.loads(raw[a:b + 1])
        except Exception: return None
    return None


def slice_notes(notes, topics):
    """Cut the notes into one excerpt per topic using the 'start_marker' the AI gave."""
    pos = []
    for t in topics:
        words = re.sub(r"\s+", " ", str(t.get("start_marker", ""))).strip().split(" ")
        m = re.search(r"\s+".join(map(re.escape, words)), notes, re.I) if len(" ".join(words)) >= 8 else None
        pos.append(m.start() if m else -1)
    ok = all(p >= 0 for p in pos) and pos == sorted(pos) and len(set(pos)) == len(pos)
    if not ok:
        return [notes[:20000]] * len(topics)
    pos[0] = 0
    return [notes[pos[i]:(pos[i + 1] if i + 1 < len(pos) else len(notes))][:20000] for i in range(len(pos))]


def parse_sections(text):
    parts = re.split(r"(?m)^\s*#{2,4}\s*", text)[1:]
    out = []
    for p in parts:
        title, _, body = p.partition("\n")
        out.append({"title": title.strip(" *"), "body": body.strip()})
    return out


SCORE_RE = re.compile(r"\s*\**\s*SCORE\s*\**\s*[:：]\s*\**\s*(\d{1,3})[^\n]*\n", re.I)


# ------------------------------------------------------------------ tasks
def t_analyze(lid):
    with LOCK:
        L = LES.get(lid)
        if not L: return
        c = L["course"]; c["status"] = "analyzing"; c["error"] = None
    save_course(lid)
    notes = (LDIR / lid / "notes.txt").read_text(encoding="utf-8")
    qlist = "\n".join(f"{q['id']}. {q['text'][:300]}" for q in c["questions"])
    prompt = (
        "Below are a student's study NOTES and a numbered list of QUESTIONS about them.\n"
        "Split the material into 3-10 topics, in the logical order of the notes.\n"
        'Return ONLY JSON: {"title": "short lesson title", "language": "tr or ar or en...", "topics": ['
        '{"title": "topic title", "emoji": "one emoji", '
        '"start_marker": "the first 6-10 words of the notes where this topic begins, copied EXACTLY", '
        '"question_ids": [ints], "outline": ["3-5 short section titles to explain this topic"]}]}\n'
        "Rules: every question id appears in exactly one topic (the topic whose notes contain its answer). "
        "Titles and outline are written in the language of the notes. start_marker must be copied verbatim.\n\n"
        f"NOTES:\n<<<\n{notes[:120000]}\n>>>\n\nQUESTIONS:\n{qlist}")
    data, err = None, None
    for _ in range(2):
        try:
            raw = gate.generate(prompt, system="You organise study material. Output valid JSON only.",
                                json_mode=True, max_tokens=8192, cancel=lambda: lid not in LES)
        except GeminiError as e:
            err = e; break
        data = parse_json(raw)
        if isinstance(data, dict) and isinstance(data.get("topics"), list) and data["topics"]: break
        data = None
    if lid not in LES: return
    with LOCK:
        if data is None:
            c["status"] = "paused"
            c["error"] = {"kind": err.kind if err else "format",
                          "message": (str(err) if err else "AI reply was not understood")[:300]}
            save_course(lid)
            _enotify(lesson=lid, what="analyze", kind=c["error"]["kind"])
            return
        ids = {q["id"] for q in c["questions"]}
        topics = [t for t in data["topics"] if isinstance(t, dict)][:12]
        slices = slice_notes(notes, topics)
        assigned, stages = set(), []
        for i, tp in enumerate(topics):
            qids = []
            for x in tp.get("question_ids") or []:
                try: x = int(x)
                except (TypeError, ValueError): continue
                if x in ids and x not in assigned: qids.append(x); assigned.add(x)
            title = str(tp.get("title") or f"{i + 1}")[:80]
            outline = [str(o)[:80] for o in (tp.get("outline") or []) if o][:6] or [title]
            stages.append({"id": f"s{i + 1}", "title": title, "emoji": str(tp.get("emoji") or "📘")[:8],
                           "outline": outline, "question_ids": qids, "notes": slices[i],
                           "status": "pending", "sections": [], "partial": None, "error": None})
        rest = sorted(ids - assigned)
        if rest and stages: stages[-1]["question_ids"] += rest
        if not stages: c["status"] = "paused"; c["error"] = {"kind": "format", "message": "No topics"}; save_course(lid); return
        c["stages"] = stages
        if not c.get("custom_title") and data.get("title"): c["title"] = str(data["title"])[:60]
        c["lang"] = str(data.get("language") or "tr")[:8]
        c["status"] = "building"
    save_course(lid)
    notify("lesson_ready", lesson=lid)
    for st in stages: WORKER.add(("stage", lid, st["id"]), 1)


def _stage(lid, sid):
    L = LES.get(lid)
    return next((s for s in L["course"]["stages"] if s["id"] == sid), None) if L else None


def t_stage(lid, sid):
    with LOCK:
        st = _stage(lid, sid)
        if not st: return
        st["status"] = "building"; st["error"] = None; st["partial"] = None
        lang = LES[lid]["course"].get("lang") or "tr"
        title, notes, outline = st["title"], st["notes"], list(st["outline"])
    last_err = None
    for attempt in range(3):
        with LOCK:
            base = list(st["sections"]); remaining = outline[len(base):]
        if not remaining and base: break
        if not remaining: remaining = [title]
        prompt = (
            f'NOTES for the topic "{title}":\n<<<\n{notes}\n>>>\n\n'
            f"Write a study lesson for this topic using ONLY the notes above, in the same language as the notes ({lang}). "
            "Make it short and easy to read, like small cards. Use EXACTLY this format and nothing else:\n"
            "### <section title>\n<2-5 short sentences or short '- ' bullets; put key terms in **bold**>\n\n"
            "Write only these sections, in this order:\n" + "\n".join(f"{i + 1}. {r}" for i, r in enumerate(remaining)) +
            ("\n(The earlier sections are already written; continue with the next ones.)" if base else ""))
        buf = ""

        def on_text(piece):
            nonlocal buf
            buf += piece
            secs = parse_sections(buf)
            with LOCK:
                if lid not in LES: return
                done, cur = (secs[:-1], secs[-1]) if secs else ([], None)
                st["sections"] = base + done
                st["partial"] = cur
        try:
            gate.generate(prompt, system="You are a warm, clear teacher writing short lesson cards.",
                          on_text=on_text, max_tokens=4096, cancel=lambda: lid not in LES)
            with LOCK:
                if lid not in LES: return
                st["sections"] = base + parse_sections(buf); st["partial"] = None
            save_course(lid)
            last_err = None
            if len(st["sections"]) >= len(outline): break
        except GeminiError as e:
            last_err = e
            with LOCK:
                if lid not in LES: return
                secs = parse_sections(buf)
                st["sections"] = base + (secs[:-1] if secs else []); st["partial"] = None
            save_course(lid)
            if e.kind in ("nokey", "auth", "bad", "quota_day", "cancelled", "offline"): break
    with LOCK:
        if lid not in LES: return
        if last_err and not st["sections"]:
            st["status"] = "paused"; st["error"] = {"kind": last_err.kind, "message": str(last_err)[:300]}
            _enotify(lesson=lid, what="stage", sid=sid, kind=last_err.kind)
        elif last_err and len(st["sections"]) < len(outline):
            st["status"] = "paused"; st["error"] = {"kind": last_err.kind, "message": str(last_err)[:300]}
        else:
            st["status"] = "ready"
        c = LES[lid]["course"]
        if all(s["status"] == "ready" for s in c["stages"]): c["status"] = "ready"
    save_course(lid)


def t_grade(lid, key):
    with LOCK:
        L = LES.get(lid); rec = L["progress"]["answers"].get(key) if L else None
        if not rec: return
        st = _stage(lid, rec["sid"])
        q = next((q for q in L["course"]["questions"] if q["id"] == rec["qid"]), None)
        if not st or not q: return
        rec.update(status="grading", text="", score=None, error=None)
        answer, ui = rec["answer"], LANG_NAME.get(rec.get("lang"), "Turkish")
        notes = st["notes"][:9000]; question = q["text"]
    prompt = (
        "You are a kind teacher checking a student's WRITTEN answer.\n"
        f"NOTES:\n<<<\n{notes}\n>>>\nQUESTION: {question}\nSTUDENT ANSWER: {answer}\n\n"
        f"Write your reply in {ui}. Use EXACTLY this format:\nSCORE: <integer 0-100>\n"
        "<2-4 short encouraging sentences: what is right, what is missing, and a short ideal answer>")
    buf, err = "", None
    for _ in range(2):
        buf = ""

        def on_text(piece):
            nonlocal buf
            buf += piece
            with LOCK:
                if lid not in LES or L["progress"]["answers"].get(key) is not rec: return
                m = SCORE_RE.match(buf)
                if m: rec["score"] = min(100, int(m.group(1))); rec["text"] = buf[m.end():].lstrip()
                elif len(buf) > 40 and "score" not in buf[:12].lower(): rec["text"] = buf
        try:
            gate.generate(prompt, system="You grade fairly using the notes. Follow the output format exactly.",
                          on_text=on_text, max_tokens=2048, cancel=lambda: lid not in LES)
            err = None; break
        except GeminiError as e:
            err = e
            if not e.partial or e.kind in ("auth", "nokey", "offline"): break
    with LOCK:
        if lid not in LES or L["progress"]["answers"].get(key) is not rec: return
        if err:
            rec["status"] = "paused"; rec["error"] = {"kind": err.kind, "message": str(err)[:300]}
            _enotify(lesson=lid, what="grade", key=key, kind=err.kind)
        else:
            m = SCORE_RE.match(buf + "\n")
            if m: rec["score"] = min(100, int(m.group(1))); rec["text"] = (buf + "\n")[m.end():].strip()
            else: rec["text"] = buf.strip()
            if rec["score"] is None: rec["score"] = 50
            rec["status"] = "done"
            _reward(lid, rec)
    save_progress(lid); save_settings()


def _reward(lid, rec):
    s = rec["score"]
    add_xp(10 if s >= 70 else 5 if s >= 40 else 2, 2 if s >= 70 else 0)
    if s < 40: S["stats"]["hearts"] = max(0, S["stats"]["hearts"] - 1)
    if s >= 100: give_badge("perfect")
    q = next((q for q in LES[lid]["course"]["questions"] if q["id"] == rec["qid"]), {})
    notify("graded", lesson=lid, key=rec["key"], sid=rec["sid"], qid=rec["qid"], score=s, q=q.get("text", "")[:90])
    if rec.get("exam"):
        P = LES[lid]["progress"]
        ex = next((e for e in P["exams"] if e["id"] == rec["exam"]), None)
        if ex and not ex.get("done") and all(P["answers"].get(f"{ex['id']}:{x}", {}).get("status") == "done" for x in ex["qids"]):
            ex["done"] = True; add_xp(30, 10); give_badge("exam")


# ------------------------------------------------------------------ worker
def dispatch(task):
    {"analyze": t_analyze, "stage": t_stage, "grade": t_grade}[task[0]](*task[1:])


class Worker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.cv, self.heap, self.keys, self.n, self.current = threading.Condition(), [], set(), itertools.count(), None

    def add(self, task, prio=1):
        with self.cv:
            if task in self.keys or task == self.current: return
            self.keys.add(task); heapq.heappush(self.heap, (prio, next(self.n), task)); self.cv.notify()

    def busy(self):
        with self.cv: return bool(self.heap) or self.current is not None

    def run(self):
        while True:
            with self.cv:
                while not self.heap: self.cv.wait()
                _, _, task = heapq.heappop(self.heap); self.keys.discard(task); self.current = task
            try: dispatch(task)
            except Exception:
                traceback.print_exc()
                with LOCK:
                    L = LES.get(task[1])
                    if L and task[0] == "stage":
                        st = _stage(task[1], task[2])
                        if st: st["status"] = "paused"; st["error"] = {"kind": "error", "message": "internal error"}
                    elif L and task[0] == "grade":
                        r = L["progress"]["answers"].get(task[2])
                        if r: r["status"] = "paused"; r["error"] = {"kind": "error", "message": "internal error"}
                    elif L and task[0] == "analyze":
                        L["course"]["status"] = "paused"; L["course"]["error"] = {"kind": "error", "message": "internal error"}
            finally:
                with self.cv: self.current = None


WORKER = Worker()


def resume_all():
    """After a restart / crash: continue exactly where things stopped (nothing is regenerated twice)."""
    for lid, L in LES.items():
        c = L["course"]
        if c["status"] == "analyzing": WORKER.add(("analyze", lid), 1)
        for st in c["stages"]:
            if st["status"] in ("pending", "building"):
                st["status"] = "pending"; st["partial"] = None; WORKER.add(("stage", lid, st["id"]), 1)
        for key, r in L["progress"]["answers"].items():
            if r["status"] in ("queued", "grading"): r["status"] = "queued"; WORKER.add(("grade", lid, key), 0)


def retry(lid, what, sid=None, key=None):
    with LOCK:
        L = LES.get(lid)
        if not L: return
        if what == "analyze": L["course"]["status"] = "analyzing"; L["course"]["error"] = None
        if what == "stage":
            for st in ([_stage(lid, sid)] if sid else [s for s in L["course"]["stages"] if s["status"] == "paused"]):
                if st: st["status"] = "pending"; st["error"] = None; WORKER.add(("stage", lid, st["id"]), 1)
        if what == "grade":
            keys = [key] if key else [k for k, r in L["progress"]["answers"].items() if r["status"] == "paused"]
            for k in keys:
                if k in L["progress"]["answers"]: L["progress"]["answers"][k]["status"] = "queued"; WORKER.add(("grade", lid, k), 0)
    if what == "analyze": WORKER.add(("analyze", lid), 1)
    save_course(lid); save_progress(lid)


# ------------------------------------------------------------------ pass rule (75%), reset, chests
def stage_stats_for(lid):
    L = LES[lid]; P = L["progress"]; out = {}
    for s in L["course"]["stages"]:
        qids = s["question_ids"]; total = len(qids)
        recs = [P["answers"].get(f"{s['id']}:{q}") for q in qids]
        graded = [r for r in recs if r and r["status"] == "done" and r.get("score") is not None]
        avg = round(sum(r["score"] for r in graded) / total) if total and len(graded) == total else None
        passed = bool(P["read"].get(s["id"])) if total == 0 else (avg is not None and avg >= PASS)
        out[s["id"]] = {"total": total, "answered": len([r for r in recs if r]), "graded": len(graded),
                        "avg": avg, "passed": passed}
    return out


def reset(lid, sid=None):
    """Delete the answers of one stage (or of the whole lesson) so it can be redone from zero."""
    with LOCK:
        P = LES[lid]["progress"]
        if sid:
            for k in [k for k, r in P["answers"].items() if r["sid"] == sid and not r.get("exam")]: del P["answers"][k]
            P["stage_done"].pop(sid, None)
        else:
            P["answers"].clear(); P["exams"].clear(); P["stage_done"].clear(); P["read"].clear()
    save_progress(lid)


def claim_chest(lid, sid):
    with LOCK:
        P = LES[lid]["progress"]; ch = P.setdefault("chests", {})
        if sid in ch or not stage_stats_for(lid).get(sid, {}).get("passed"): raise ValueError("locked")
        ch[sid] = time.time(); add_xp(15, 10)
    save_progress(lid); save_settings()


def set_model(name):
    name = (name or "").strip().replace("models/", "")
    if name and not re.fullmatch(r"[A-Za-z0-9._-]{3,80}", name): raise ValueError("bad_model")
    with LOCK:
        S["model"] = name; gate.model_pref = name; save_settings()


def set_offline(flag):
    with LOCK:
        S["offline"] = bool(flag); gate.offline = bool(flag); save_settings()
    if not flag: resume_paused()


# ------------------------------------------------------------------ share a lesson as a file (no AI needed to open it)
def export_lesson(lid):
    with LOCK:
        c = LES[lid]["course"]
        if c["status"] != "ready" or not c["stages"] or any(not s["sections"] for s in c["stages"]): raise ValueError("not_ready")
        return {"format": "foxy-lesson", "version": 1, "course": {
            "title": c["title"], "lang": c.get("lang"), "questions": c["questions"],
            "stages": [{k: s[k] for k in ("title", "emoji", "outline", "question_ids", "notes", "sections")} for s in c["stages"]]}}


def import_lesson(data):
    try:
        if not isinstance(data, dict) or data.get("format") != "foxy-lesson": raise ValueError
        c = data["course"]
        qs = [{"id": int(q["id"]), "text": str(q["text"])[:600]} for q in c["questions"]][:200]
        ids = {q["id"] for q in qs}; stages = []
        for i, s in enumerate(c["stages"][:12]):
            secs = [{"title": str(x["title"])[:120], "body": str(x["body"])[:4000]} for x in s["sections"]][:12]
            if not secs: continue
            stages.append({"id": f"s{len(stages) + 1}", "title": str(s["title"])[:80], "emoji": str(s.get("emoji") or "📘")[:8],
                           "outline": [str(o)[:80] for o in s.get("outline", [])][:6] or [str(s["title"])[:80]],
                           "question_ids": [int(x) for x in s.get("question_ids", []) if int(x) in ids],
                           "notes": str(s.get("notes", ""))[:20000], "status": "ready", "sections": secs, "partial": None, "error": None})
        if not stages or not qs: raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("bad_file")
    lid = uuid.uuid4().hex[:8]
    course = {"id": lid, "title": str(c.get("title") or "Ders")[:60], "custom_title": True, "created": time.time(),
              "status": "ready", "error": None, "lang": str(c.get("lang") or "tr")[:8], "questions": qs, "stages": stages}
    (LDIR / lid).mkdir(parents=True)
    with LOCK:
        LES[lid] = {"course": course, "progress": _empty_progress()}; S["active"] = lid
    save_course(lid); save_progress(lid); save_settings()
    return lid


# ------------------------------------------------------------------ student actions
def stage_of(lid, qid):
    for s in LES[lid]["course"]["stages"]:
        if qid in s["question_ids"]: return s["id"]


def submit_answer(lid, qid, answer, exam_id=None):
    with LOCK:
        L = LES[lid]; P = L["progress"]
        sid = stage_of(lid, qid)
        if not sid: raise ValueError("bad_question")
        sg = L["course"]["stages"]; idx = next(i for i, x in enumerate(sg) if x["id"] == sid)
        if idx > 0 and not stage_stats_for(lid)[sg[idx - 1]["id"]]["passed"]: raise ValueError("locked")
        key = f"{exam_id or sid}:{qid}"
        if exam_id and not any(e["id"] == exam_id and qid in e["qids"] for e in P["exams"]): raise ValueError("bad_exam")
        old = P["answers"].get(key)
        if old and old["status"] in ("queued", "grading"): return key
        P["answers"][key] = {"key": key, "sid": sid, "qid": qid, "exam": exam_id, "answer": answer[:4000],
                             "status": "queued", "text": "", "score": None, "error": None, "ts": time.time(),
                             "lang": S["lang"]}
        touch_streak(); give_badge("first_answer")
        stage = _stage(lid, sid)
        if not exam_id and sid not in P["stage_done"] and all(f"{sid}:{x}" in P["answers"] for x in stage["question_ids"]):
            P["stage_done"][sid] = {"ts": time.time()}
            add_xp(20, 5); give_badge("stage1")
    save_progress(lid); save_settings()
    WORKER.add(("grade", lid, key), 0)
    return key


def mark_read(lid, sid):
    with LOCK:
        L = LES.get(lid); st = _stage(lid, sid)
        if not st: return
        P = L["progress"]; P["read"][sid] = True
        if not st["question_ids"] and sid not in P["stage_done"]:
            P["stage_done"][sid] = {"ts": time.time()}; add_xp(15, 3); give_badge("stage1")
    save_progress(lid); save_settings()


def start_exam(lid):
    with LOCK:
        L = LES[lid]; P = L["progress"]
        if not all(v["passed"] for v in stage_stats_for(lid).values()): raise ValueError("locked")
        cur = next((e for e in P["exams"] if not e.get("done") and not all(f"{e['id']}:{x}" in P["answers"] for x in e["qids"])), None)
        if cur: return cur["id"]
        ids = [q["id"] for q in L["course"]["questions"]]
        random.shuffle(ids)
        ex = {"id": f"x{len(P['exams']) + 1}", "qids": ids[:int(os.environ.get("EXAM_SIZE", "10"))], "ts": time.time(), "done": False}
        P["exams"].append(ex)
    save_progress(lid)
    return ex["id"]


# ------------------------------------------------------------------ state for the UI
def state():
    with LOCK:
        regen_hearts()
        active = S["active"] if S["active"] in LES else None
        lessons = []
        for lid in sorted(LES, key=lambda i: -LES[i]["course"]["created"]):
            c, P = LES[lid]["course"], LES[lid]["progress"]
            sg = c["stages"]
            lessons.append({"id": lid, "title": c["title"], "status": c["status"], "created": c["created"],
                            "total_q": len(c["questions"]),
                            "answered": len([k for k in P["answers"] if not P["answers"][k].get("exam")]),
                            "stages": len(sg), "ready": len([s for s in sg if s["status"] == "ready"])})
        course = progress = None
        if active:
            course = json.loads(json.dumps(LES[active]["course"]))
            for s in course["stages"]: s.pop("notes", None)
            progress = json.loads(json.dumps(LES[active]["progress"]))
            progress["stage_stats"] = stage_stats_for(active); progress.setdefault("chests", {})
        st = dict(S["stats"])
        if st["last_day"] not in (_day(), _day(1)): st["streak"] = 0
        if st["last_day"] != _day(): st["daily_xp"] = 0
        out = {"settings": {"lang": S["lang"], "mascot": S["mascot"], "sound": S["sound"], "active": active, "offline": S["offline"], "model": S["model"]},
               "stats": st, "lessons": lessons, "course": course, "progress": progress,
               "notifications": list(reversed(S["notifications"]))[:40], "ai": gate.status(),
               "server_time": time.time()}
    k = gate.key()
    out["ai"]["key_hint"] = ("•••• " + k[-4:]) if k else ""
    out["ai"]["key_source"] = "site" if SECRET_F.exists() and k else ("env" if k else "none")
    out["busy"] = WORKER.busy()
    return out


# ------------------------------------------------------------------ helper chat (streamed)
def chat_stream(lid, sid, qid, message, history):
    with LOCK:
        mascot, ui = S["mascot"], LANG_NAME.get(S["lang"], "Turkish")
        ctx = ""
        L = LES.get(lid)
        if L:
            st = _stage(lid, sid) if sid else None
            ctx = f'Lesson: {L["course"]["title"]}\n'
            if st: ctx += f'Current topic: {st["title"]}\nNOTES:\n{st["notes"][:8000]}\n'
            q = next((q for q in L["course"]["questions"] if q["id"] == qid), None) if qid else None
            if q: ctx += f'The student is looking at this question: {q["text"]}\n'
    system = (f"You are {MASCOT_NAME.get(mascot, 'Foxy')}, {MASCOT_LOOK.get(mascot, 'a friendly mascot')} who helps a student study. "
              f"ALWAYS answer in {ui}. Be warm, short and simple (max ~120 words), use the notes when relevant, "
              "explain step by step if asked, and translate any text when asked. Do not just give away the answer to a question "
              "the student is practising unless they ask for it.\n" + ctx)
    contents = [{"role": "user" if h.get("role") == "user" else "model", "parts": [{"text": str(h.get("text", ""))[:1500]}]}
                for h in (history or [])[-6:]]
    contents.append({"role": "user", "parts": [{"text": message[:2000]}]})
    q, stop = queue.Queue(), threading.Event()

    def run():
        try:
            gate.generate(contents, system=system, on_text=lambda t: q.put(("t", t)), max_tokens=2048,
                          attempts=3, cancel=stop.is_set)
        except GeminiError as e:
            q.put(("e", {"kind": e.kind, "message": str(e)[:200], "retry": int(e.retry_after)}))
        except Exception as e:
            q.put(("e", {"kind": "error", "message": str(e)[:200]}))
        q.put(("d", None))
    threading.Thread(target=run, daemon=True).start()
    try:
        while True:
            try: kind, val = q.get(timeout=1)
            except queue.Empty:
                yield {"w": gate.status()["cooldown_left"]}; continue
            if kind == "t": yield {"t": val}
            elif kind == "e": yield {"error": val}
            else: yield {"done": True}; break
    finally:
        stop.set()


load_secret()
load_all()
