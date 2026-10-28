"""Study engine v4: SQLite storage, users, per-user progress, shared lessons, AI tasks, shop."""
import os, re, json, time, uuid, random, shutil, threading, heapq, itertools, queue, traceback, sqlite3, base64, hashlib, secrets
from pathlib import Path
from cryptography.fernet import Fernet
from werkzeug.security import generate_password_hash, check_password_hash
from gemini import gate_for, GeminiError

ROOT = Path(__file__).parent
DATA = Path(os.environ.get("DATA_DIR", ROOT / "data"))
DATA.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()
LANG_NAME = {"tr": "Turkish", "ar": "Arabic"}
MASCOT_NAME = {"fox": "Foxy", "panda": "Pandi", "robot": "Robo"}
MASCOT_LOOK = {"fox": "a cheerful fox", "panda": "a sleepy-but-kind panda", "robot": "a friendly little robot"}
PASS = 75
HEART_PRICE = 5
HEART_REGEN = 1800            # one free heart every 30 minutes (safety net)
USERNAME_RE = re.compile(r"^[\w.\-]{3,32}$")


# ------------------------------------------------------------------ secrets / encryption
def _app_secret():
    s = os.environ.get("APP_SECRET", "").strip()
    if s: return s
    f = DATA / "app_secret"
    if f.exists(): return f.read_text().strip()
    s = secrets.token_hex(32); f.write_text(s)
    try: os.chmod(f, 0o600)
    except OSError: pass
    return s


APP_SECRET = _app_secret()
_FERNET = Fernet(base64.urlsafe_b64encode(hashlib.sha256(("enc:" + APP_SECRET).encode()).digest()))
def enc(s): return _FERNET.encrypt(s.encode()).decode() if s else ""
def dec(s):
    try: return _FERNET.decrypt(s.encode()).decode() if s else ""
    except Exception: return ""


# ------------------------------------------------------------------ database
DB = sqlite3.connect(str(DATA / "app.db"), check_same_thread=False, isolation_level=None)
DB.row_factory = sqlite3.Row
DB.execute("PRAGMA journal_mode=WAL"); DB.execute("PRAGMA foreign_keys=ON")
DB.executescript("""
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL COLLATE NOCASE,
  password_hash TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0, disabled INTEGER NOT NULL DEFAULT 0, created REAL, data TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS lessons(id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT, created REAL, course TEXT NOT NULL, notes TEXT DEFAULT '', shared TEXT NOT NULL DEFAULT '[]', shared_all INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS progress(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, lesson_id TEXT NOT NULL,
  data TEXT NOT NULL, PRIMARY KEY(user_id, lesson_id));
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
""")


def db(sql, args=()):
    with LOCK: return DB.execute(sql, args)
def dball(sql, args=()):
    with LOCK: return DB.execute(sql, args).fetchall()
def dbone(sql, args=()):
    with LOCK: return DB.execute(sql, args).fetchone()
def get_setting(k, default=""):
    r = dbone("SELECT value FROM settings WHERE key=?", (k,)); return r["value"] if r else default
def set_setting(k, v): db("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, v))
def _j(x): return json.dumps(x, ensure_ascii=False)


# ------------------------------------------------------------------ users
U, LES, PROG = {}, {}, {}


def _new_udata():
    return {"lang": "tr", "mascot": "fox", "sound": True, "offline": False, "model": "", "own_key": "", "active": None,
            "nid": 0, "notifications": [],
            "stats": {"xp": 0, "xp_carry": 0, "gems": 0, "streak": 0, "last_day": "", "daily_xp": 0, "hearts": 5,
                      "hearts_ts": time.time(), "badges": []}}


def _load_user(r):
    d = _new_udata()
    try: d.update(json.loads(r["data"] or "{}"))
    except Exception: pass
    d["stats"] = {**_new_udata()["stats"], **d.get("stats", {})}
    U[r["id"]] = {"id": r["id"], "username": r["username"], "is_admin": bool(r["is_admin"]), "disabled": bool(r["disabled"]), "d": d}


def save_user(uid):
    with LOCK:
        u = U.get(uid)
        if u: db("UPDATE users SET data=?, disabled=?, is_admin=? WHERE id=?", (_j(u["d"]), int(u["disabled"]), int(u["is_admin"]), uid))


def admin_exists(): return bool(dbone("SELECT 1 FROM users WHERE is_admin=1 LIMIT 1"))


def check_username(name):
    if not USERNAME_RE.match(name or ""): raise ValueError("bad_username")


def create_user(username, password, is_admin=False):
    username = (username or "").strip(); check_username(username)
    if len(password or "") < (8 if is_admin else 6): raise ValueError("weak_password")
    with LOCK:
        if dbone("SELECT 1 FROM users WHERE username=?", (username,)): raise ValueError("exists")
        cur = db("INSERT INTO users(username,password_hash,is_admin,created,data) VALUES(?,?,?,?,?)",
                 (username, generate_password_hash(password, method="pbkdf2:sha256:600000"), int(is_admin), time.time(), _j(_new_udata())))
        _load_user(dbone("SELECT * FROM users WHERE id=?", (cur.lastrowid,)))
        return cur.lastrowid


def verify_login(username, password):
    r = dbone("SELECT * FROM users WHERE username=?", ((username or "").strip(),))
    ok = check_password_hash(r["password_hash"], password or "") if r else check_password_hash(generate_password_hash("x"), "y")
    if not r or not ok or r["disabled"]: return None
    return r["id"]


def set_password(uid, new):
    if len(new or "") < (8 if U[uid]["is_admin"] else 6): raise ValueError("weak_password")
    db("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new, method="pbkdf2:sha256:600000"), uid))


def check_password(uid, pw):
    r = dbone("SELECT password_hash FROM users WHERE id=?", (uid,)); return bool(r) and check_password_hash(r["password_hash"], pw or "")


def delete_user(uid):
    with LOCK:
        if U.get(uid, {}).get("is_admin"): raise ValueError("cannot_delete_admin")
        for lid in [l for l, L in LES.items() if L["owner"] == uid]: LES.pop(lid, None); PROG_drop(lid)
        for k in [k for k in PROG if k[0] == uid]: PROG.pop(k, None)
        db("DELETE FROM users WHERE id=?", (uid,)); U.pop(uid, None)
        for L in LES.values(): L["shared"] = [x for x in L["shared"] if x != uid]


def PROG_drop(lid):
    for k in [k for k in PROG if k[1] == lid]: PROG.pop(k, None)


# ------------------------------------------------------------------ AI context (who pays for the call, which model)
def admin_key(): return dec(get_setting("api_key_enc")) or os.environ.get("GEMINI_API_KEY", "").strip()


def ai_ctx(uid):
    u = U[uid]; d = u["d"]; own = dec(d.get("own_key", ""))
    if u["is_admin"]: return {"key": admin_key(), "model": get_setting("default_model"), "offline": bool(d["offline"]), "source": "admin"}
    if own: return {"key": own, "model": d["model"], "offline": bool(d["offline"]), "source": "own"}
    return {"key": admin_key(), "model": get_setting("default_model"), "offline": False, "source": "shared"}


def can_ai(uid): u = U[uid]; return u["is_admin"] or bool(dec(u["d"].get("own_key", "")))


def gen(uid, *a, **kw):
    ctx = ai_ctx(uid)
    return gate_for(ctx["key"]).generate(*a, pref=ctx["model"], offline=lambda: ai_ctx(uid)["offline"], **kw)


def set_own_key(uid, key):
    key = (key or "").strip().strip('"').strip("'")
    if key and (len(key) < 20 or any(c.isspace() for c in key)): raise ValueError("bad_key")
    if U[uid]["is_admin"]: set_setting("api_key_enc", enc(key))
    else: U[uid]["d"]["own_key"] = enc(key); save_user(uid)
    resume_paused()


def set_model(uid, name):
    name = (name or "").strip().replace("models/", "")
    if name and not re.fullmatch(r"[A-Za-z0-9._-]{3,80}", name): raise ValueError("bad_model")
    if U[uid]["is_admin"]: set_setting("default_model", name)
    else: U[uid]["d"]["model"] = name; save_user(uid)


def set_offline(uid, flag):
    U[uid]["d"]["offline"] = bool(flag); save_user(uid)
    if not flag: resume_paused()


def ai_status(uid):
    ctx = ai_ctx(uid); return gate_for(ctx["key"]).status(ctx["model"], ctx["offline"])


# ------------------------------------------------------------------ stats / rewards / notifications
def _day(offset=0): return time.strftime("%Y-%m-%d", time.localtime(time.time() - offset * 86400))
def stats(uid): return U[uid]["d"]["stats"]


def notify(uid, kind, **data):
    with LOCK:
        d = U[uid]["d"]; d["nid"] += 1
        d["notifications"].append({"id": d["nid"], "kind": kind, "ts": time.time(), "read": False, **data})
        d["notifications"] = d["notifications"][-60:]; save_user(uid)


def _enotify(uid, **kw):
    if kw.get("kind") != "offline": notify(uid, "error", **kw)


def touch_streak(uid):
    st = stats(uid)
    if st["last_day"] == _day(): return
    st["streak"] = st["streak"] + 1 if st["last_day"] == _day(1) else 1
    st["last_day"] = _day(); st["daily_xp"] = 0


def give_badge(uid, bid):
    st = stats(uid)
    if bid not in st["badges"]: st["badges"].append(bid); notify(uid, "badge", badge=bid)


def add_xp(uid, xp, bonus_gems=0):
    """Gems come from XP: every 10 XP = 1 gem (chests / stage rewards add bonus gems)."""
    st = stats(uid); touch_streak(uid)
    st["xp"] += xp; st["daily_xp"] += xp; st["xp_carry"] += xp
    st["gems"] += st["xp_carry"] // 10 + bonus_gems; st["xp_carry"] %= 10
    if st["xp"] >= 100: give_badge(uid, "xp100")
    if st["xp"] >= 500: give_badge(uid, "xp500")
    if st["streak"] >= 3: give_badge(uid, "streak3")
    if st["streak"] >= 7: give_badge(uid, "streak7")


def regen_hearts(uid):
    st = stats(uid); now = time.time()
    if st["hearts"] >= 5: st["hearts"] = 5; st["hearts_ts"] = now; return
    while st["hearts"] < 5 and now - st["hearts_ts"] >= HEART_REGEN:
        st["hearts"] += 1; st["hearts_ts"] += HEART_REGEN


def shop_buy(uid, item):
    with LOCK:
        st = stats(uid); admin = U[uid]["is_admin"]; regen_hearts(uid)
        if item == "heart": cost, n = HEART_PRICE, 1
        elif item == "hearts_full": cost, n = HEART_PRICE * 4, 5
        else: raise ValueError("bad_item")
        if st["hearts"] >= 5: raise ValueError("hearts_full")
        if not admin and st["gems"] < cost: raise ValueError("no_gems")
        if not admin: st["gems"] -= cost
        st["hearts"] = min(5, st["hearts"] + n); st["hearts_ts"] = time.time(); save_user(uid)


def admin_grant(target, gems=0, xp=0, hearts=0):
    with LOCK:
        if target not in U: raise ValueError("bad_user")
        clamp = lambda v: max(-100000, min(100000, int(v or 0)))
        gems, xp, hearts = clamp(gems), clamp(xp), clamp(hearts); st = stats(target)
        st["gems"] = max(0, st["gems"] + gems)
        if xp: st["xp"] = max(0, st["xp"] + xp); st["daily_xp"] = max(0, st["daily_xp"] + max(xp, 0))
        if hearts: st["hearts"] = max(0, min(5, st["hearts"] + hearts)); st["hearts_ts"] = time.time()
        save_user(target)


# ------------------------------------------------------------------ lessons / progress storage
def _empty_progress(): return {"read": {}, "answers": {}, "exams": [], "stage_done": {}, "chests": {}}


def load_all():
    for r in dball("SELECT * FROM users"): _load_user(r)
    for r in dball("SELECT * FROM lessons"):
        try: LES[r["id"]] = {"course": json.loads(r["course"]), "owner": r["user_id"], "shared": json.loads(r["shared"] or "[]"), "shared_all": bool(r["shared_all"])}
        except Exception: pass
    for r in dball("SELECT * FROM progress"):
        try: PROG[(r["user_id"], r["lesson_id"])] = json.loads(r["data"])
        except Exception: pass


def get_prog(uid, lid):
    with LOCK:
        if (uid, lid) not in PROG:
            r = dbone("SELECT data FROM progress WHERE user_id=? AND lesson_id=?", (uid, lid))
            PROG[(uid, lid)] = json.loads(r["data"]) if r else _empty_progress()
        return PROG[(uid, lid)]


def save_progress(uid, lid):
    with LOCK:
        if lid in LES and (uid, lid) in PROG and uid in U:
            db("INSERT OR REPLACE INTO progress(user_id,lesson_id,data) VALUES(?,?,?)", (uid, lid, _j(PROG[(uid, lid)])))


def save_course(lid):
    with LOCK:
        L = LES.get(lid)
        if L: db("UPDATE lessons SET course=?, title=?, shared=?, shared_all=? WHERE id=?", (_j(L["course"]), L["course"]["title"], _j(L["shared"]), int(L["shared_all"]), lid))


def visible(uid, lid):
    L, u = LES.get(lid), U.get(uid)
    return bool(L and u and (u["is_admin"] or L["owner"] == uid or L["shared_all"] or uid in L["shared"]))


def manages(uid, lid):
    L, u = LES.get(lid), U.get(uid)
    return bool(L and u and (u["is_admin"] or L["owner"] == uid))


def visible_ids(uid): return [lid for lid in LES if visible(uid, lid)]


def active_lesson(uid):
    a = U[uid]["d"].get("active")
    if a and visible(uid, a): return a
    ids = sorted(visible_ids(uid), key=lambda i: -LES[i]["course"]["created"])
    return ids[0] if ids else None


def set_active(uid, lid):
    if visible(uid, lid): U[uid]["d"]["active"] = lid; save_user(uid)


def split_questions(text):
    text = text.replace("\r", "")
    pat = re.compile(r"^\s*(?:soru\s*)?\(?\d{1,3}\s*[\.\)\-:]\s*(.+)", re.I)
    items, cur = [], None
    for line in text.split("\n"):
        m = pat.match(line)
        if m: cur = [m.group(1).strip()]; items.append(cur)
        elif cur is not None and line.strip(): cur.append(line.strip())
    items = [" ".join(x) for x in items]
    if len(items) < 2: items = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(items) < 2: items = [l.strip() for l in text.split("\n") if l.strip()]
    return [q[:600] for q in items if len(q) > 3][:200]


def _insert_lesson(uid, course, notes=""):
    lid = course["id"]
    with LOCK:
        LES[lid] = {"course": course, "owner": uid, "shared": [], "shared_all": False}
        db("INSERT INTO lessons(id,user_id,title,created,course,notes) VALUES(?,?,?,?,?,?)", (lid, uid, course["title"], course["created"], _j(course), notes))
        U[uid]["d"]["active"] = lid; save_user(uid)


def create_lesson(uid, title, qtext, ntext):
    if not can_ai(uid): raise ValueError("no_permission")
    qs = split_questions(qtext)
    if not qs: raise ValueError("no_questions")
    if len(ntext.strip()) < 40: raise ValueError("no_notes")
    lid = uuid.uuid4().hex[:8]
    course = {"id": lid, "title": title or "Yeni ders", "custom_title": bool(title), "created": time.time(), "status": "analyzing",
              "error": None, "lang": None, "questions": [{"id": i + 1, "text": q} for i, q in enumerate(qs)], "stages": []}
    _insert_lesson(uid, course, ntext)
    WORKER.add(("analyze", lid), 1)
    return lid


def delete_lesson(lid):
    with LOCK:
        LES.pop(lid, None); PROG_drop(lid); db("DELETE FROM lessons WHERE id=?", (lid,)); db("DELETE FROM progress WHERE lesson_id=?", (lid,))


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
    pos = []
    for t in topics:
        words = re.sub(r"\s+", " ", str(t.get("start_marker", ""))).strip().split(" ")
        m = re.search(r"\s+".join(map(re.escape, words)), notes, re.I) if len(" ".join(words)) >= 8 else None
        pos.append(m.start() if m else -1)
    ok = all(p >= 0 for p in pos) and pos == sorted(pos) and len(set(pos)) == len(pos)
    if not ok: return [notes[:20000]] * len(topics)
    pos[0] = 0
    return [notes[pos[i]:(pos[i + 1] if i + 1 < len(pos) else len(notes))][:20000] for i in range(len(pos))]


def parse_sections(text):
    out = []
    for p in re.split(r"(?m)^\s*#{2,4}\s*", text)[1:]:
        title, _, body = p.partition("\n"); out.append({"title": title.strip(" *"), "body": body.strip()})
    return out


SCORE_RE = re.compile(r"\s*\**\s*SCORE\s*\**\s*[:：]\s*\**\s*(\d{1,3})[^\n]*\n", re.I)


# ------------------------------------------------------------------ tasks
def _stage(lid, sid):
    L = LES.get(lid)
    return next((s for s in L["course"]["stages"] if s["id"] == sid), None) if L else None


def t_analyze(lid):
    with LOCK:
        L = LES.get(lid)
        if not L: return
        c, owner = L["course"], L["owner"]; c["status"] = "analyzing"; c["error"] = None
    save_course(lid)
    notes = (dbone("SELECT notes FROM lessons WHERE id=?", (lid,)) or {"notes": ""})["notes"] or ""
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
            raw = gen(owner, prompt, system="You organise study material. Output valid JSON only.", json_mode=True, max_tokens=8192, cancel=lambda: lid not in LES)
        except GeminiError as e:
            err = e; break
        data = parse_json(raw)
        if isinstance(data, dict) and isinstance(data.get("topics"), list) and data["topics"]: break
        data = None
    if lid not in LES: return
    with LOCK:
        if data is None:
            c["status"] = "paused"
            c["error"] = {"kind": err.kind if err else "format", "message": (str(err) if err else "AI reply was not understood")[:300]}
            save_course(lid); _enotify(owner, lesson=lid, what="analyze", kind=c["error"]["kind"]); return
        ids = {q["id"] for q in c["questions"]}
        topics = [t for t in data["topics"] if isinstance(t, dict)][:12]
        slices = slice_notes(notes, topics); assigned, stages = set(), []
        for i, tp in enumerate(topics):
            qids = []
            for x in tp.get("question_ids") or []:
                try: x = int(x)
                except (TypeError, ValueError): continue
                if x in ids and x not in assigned: qids.append(x); assigned.add(x)
            title = str(tp.get("title") or f"{i + 1}")[:80]
            outline = [str(o)[:80] for o in (tp.get("outline") or []) if o][:6] or [title]
            stages.append({"id": f"s{i + 1}", "title": title, "emoji": str(tp.get("emoji") or "📘")[:8], "outline": outline,
                           "question_ids": qids, "notes": slices[i], "status": "pending", "sections": [], "partial": None, "error": None})
        rest = sorted(ids - assigned)
        if rest and stages: stages[-1]["question_ids"] += rest
        if not stages:
            c["status"] = "paused"; c["error"] = {"kind": "format", "message": "No topics"}; save_course(lid); return
        c["stages"] = stages
        if not c.get("custom_title") and data.get("title"): c["title"] = str(data["title"])[:60]
        c["lang"] = str(data.get("language") or "tr")[:8]; c["status"] = "building"
    save_course(lid); notify(owner, "lesson_ready", lesson=lid)
    for st in stages: WORKER.add(("stage", lid, st["id"]), 1)


def t_stage(lid, sid):
    with LOCK:
        st = _stage(lid, sid)
        if not st: return
        owner = LES[lid]["owner"]; st["status"] = "building"; st["error"] = None; st["partial"] = None
        lang = LES[lid]["course"].get("lang") or "tr"; title, notes, outline = st["title"], st["notes"], list(st["outline"])
    last_err = None
    for attempt in range(3):
        with LOCK: base = list(st["sections"]); remaining = outline[len(base):]
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
            buf += piece; secs = parse_sections(buf)
            with LOCK:
                if lid not in LES: return
                done, cur = (secs[:-1], secs[-1]) if secs else ([], None)
                st["sections"] = base + done; st["partial"] = cur
        try:
            gen(owner, prompt, system="You are a warm, clear teacher writing short lesson cards.", on_text=on_text, max_tokens=4096, cancel=lambda: lid not in LES)
            with LOCK:
                if lid not in LES: return
                st["sections"] = base + parse_sections(buf); st["partial"] = None
            save_course(lid); last_err = None
            if len(st["sections"]) >= len(outline): break
        except GeminiError as e:
            last_err = e
            with LOCK:
                if lid not in LES: return
                secs = parse_sections(buf); st["sections"] = base + (secs[:-1] if secs else []); st["partial"] = None
            save_course(lid)
            if e.kind in ("nokey", "auth", "bad", "quota_day", "cancelled", "offline"): break
    with LOCK:
        if lid not in LES: return
        if last_err and not st["sections"]:
            st["status"] = "paused"; st["error"] = {"kind": last_err.kind, "message": str(last_err)[:300]}; _enotify(owner, lesson=lid, what="stage", sid=sid, kind=last_err.kind)
        elif last_err and len(st["sections"]) < len(outline):
            st["status"] = "paused"; st["error"] = {"kind": last_err.kind, "message": str(last_err)[:300]}
        else: st["status"] = "ready"
        c = LES[lid]["course"]
        if all(s["status"] == "ready" for s in c["stages"]): c["status"] = "ready"
    save_course(lid)


def t_grade(uid, lid, key):
    with LOCK:
        L = LES.get(lid); P = get_prog(uid, lid) if L and uid in U else None; rec = P["answers"].get(key) if P else None
        if not rec: return
        st = _stage(lid, rec["sid"]); q = next((q for q in L["course"]["questions"] if q["id"] == rec["qid"]), None)
        if not st or not q: return
        rec.update(status="grading", text="", score=None, error=None)
        answer, ui = rec["answer"], LANG_NAME.get(rec.get("lang"), "Turkish"); notes = st["notes"][:9000]; question = q["text"]
    prompt = ("You are a kind teacher checking a student's WRITTEN answer.\n"
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
                if lid not in LES or P["answers"].get(key) is not rec: return
                m = SCORE_RE.match(buf)
                if m: rec["score"] = min(100, int(m.group(1))); rec["text"] = buf[m.end():].lstrip()
                elif len(buf) > 40 and "score" not in buf[:12].lower(): rec["text"] = buf
        try:
            gen(uid, prompt, system="You grade fairly using the notes. Follow the output format exactly.", on_text=on_text, max_tokens=2048,
                cancel=lambda: lid not in LES or uid not in U, prefer="cheap")
            err = None; break
        except GeminiError as e:
            err = e
            if not e.partial or e.kind in ("auth", "nokey", "offline"): break
    with LOCK:
        if lid not in LES or uid not in U or P["answers"].get(key) is not rec: return
        if err:
            rec["status"] = "paused"; rec["error"] = {"kind": err.kind, "message": str(err)[:300]}; _enotify(uid, lesson=lid, what="grade", key=key, kind=err.kind)
        else:
            m = SCORE_RE.match(buf + "\n")
            if m: rec["score"] = min(100, int(m.group(1))); rec["text"] = (buf + "\n")[m.end():].strip()
            else: rec["text"] = buf.strip()
            if rec["score"] is None: rec["score"] = 50
            rec["status"] = "done"; _reward(uid, lid, rec)
    save_progress(uid, lid); save_user(uid)


def _reward(uid, lid, rec):
    s = rec["score"]
    add_xp(uid, 10 if s >= 70 else 5 if s >= 50 else 2)
    if s < 50 and not U[uid]["is_admin"]:                      # < 50 costs a heart (admin never loses hearts)
        st = stats(uid); st["hearts"] = max(0, st["hearts"] - 1); st["hearts_ts"] = time.time()
    if s >= 100: give_badge(uid, "perfect")
    q = next((q for q in LES[lid]["course"]["questions"] if q["id"] == rec["qid"]), {})
    notify(uid, "graded", lesson=lid, key=rec["key"], sid=rec["sid"], qid=rec["qid"], score=s, q=q.get("text", "")[:90], lost_heart=(s < 50 and not U[uid]["is_admin"]))
    if rec.get("exam"):
        P = get_prog(uid, lid); ex = next((e for e in P["exams"] if e["id"] == rec["exam"]), None)
        if ex and not ex.get("done") and all(P["answers"].get(f"{ex['id']}:{x}", {}).get("status") == "done" for x in ex["qids"]):
            ex["done"] = True; add_xp(uid, 30, 10); give_badge(uid, "exam")


# ------------------------------------------------------------------ worker pool
def dispatch(task):
    {"analyze": t_analyze, "stage": t_stage, "grade": t_grade}[task[0]](*task[1:])


class Worker:
    def __init__(self, n=3):
        self.cv, self.heap, self.keys, self.n, self.current, self.threads = threading.Condition(), [], set(), itertools.count(), set(), []
        self.count = n

    def start(self):
        for _ in range(self.count):
            t = threading.Thread(target=self.run, daemon=True); t.start(); self.threads.append(t)

    def add(self, task, prio=1):
        with self.cv:
            if task in self.keys or task in self.current: return
            self.keys.add(task); heapq.heappush(self.heap, (prio, next(self.n), task)); self.cv.notify()

    def busy(self):
        with self.cv: return bool(self.heap) or bool(self.current)

    def busy_for(self, uid):
        with self.cv:
            tasks = [t for _, _, t in self.heap] + list(self.current)
        return any((t[0] == "grade" and t[1] == uid) or (t[0] != "grade" and LES.get(t[1], {}).get("owner") == uid) for t in tasks)

    def run(self):
        while True:
            with self.cv:
                while not self.heap: self.cv.wait()
                _, _, task = heapq.heappop(self.heap); self.keys.discard(task); self.current.add(task)
            try: dispatch(task)
            except Exception:
                traceback.print_exc(); _mark_broken(task)
            finally:
                with self.cv: self.current.discard(task)


def _mark_broken(task):
    with LOCK:
        if task[0] == "grade":
            r = (get_prog(task[1], task[2])["answers"].get(task[3]) if task[2] in LES else None)
            if r: r["status"] = "paused"; r["error"] = {"kind": "error", "message": "internal error"}
        elif task[1] in LES:
            if task[0] == "stage":
                st = _stage(task[1], task[2])
                if st: st["status"] = "paused"; st["error"] = {"kind": "error", "message": "internal error"}
            else: LES[task[1]]["course"]["status"] = "paused"; LES[task[1]]["course"]["error"] = {"kind": "error", "message": "internal error"}


WORKER = Worker(int(os.environ.get("WORKERS", "3")))


def resume_all():
    """After a restart: continue exactly where things stopped."""
    for lid, L in LES.items():
        c = L["course"]
        if c["status"] == "analyzing": WORKER.add(("analyze", lid), 1)
        for st in c["stages"]:
            if st["status"] in ("pending", "building"): st["status"] = "pending"; st["partial"] = None; WORKER.add(("stage", lid, st["id"]), 1)
    for (uid, lid), P in list(PROG.items()):
        for key, r in P["answers"].items():
            if r["status"] in ("queued", "grading"): r["status"] = "queued"; WORKER.add(("grade", uid, lid, key), 0)


def resume_paused():
    """A key / connection changed: restart everything that stopped."""
    with LOCK:
        for lid, L in LES.items():
            if L["course"]["status"] == "paused" and not L["course"]["stages"]: L["course"]["status"] = "analyzing"; L["course"]["error"] = None; WORKER.add(("analyze", lid), 1)
            for st in L["course"]["stages"]:
                if st["status"] == "paused": st["status"] = "pending"; st["error"] = None; WORKER.add(("stage", lid, st["id"]), 1)
        for (uid, lid), P in PROG.items():
            for k, r in P["answers"].items():
                if r["status"] == "paused": r["status"] = "queued"; WORKER.add(("grade", uid, lid, k), 0)


def retry(uid, lid, what, sid=None, key=None):
    with LOCK:
        L = LES.get(lid)
        if not L or not visible(uid, lid): return
        mine = manages(uid, lid)
        if what == "analyze" and mine: L["course"]["status"] = "analyzing"; L["course"]["error"] = None; WORKER.add(("analyze", lid), 1)
        if what == "stage" and mine:
            for st in ([_stage(lid, sid)] if sid else [s for s in L["course"]["stages"] if s["status"] == "paused"]):
                if st: st["status"] = "pending"; st["error"] = None; WORKER.add(("stage", lid, st["id"]), 1)
        if what == "grade":
            P = get_prog(uid, lid)
            for k in ([key] if key else [k for k, r in P["answers"].items() if r["status"] == "paused"]):
                if k in P["answers"]: P["answers"][k]["status"] = "queued"; WORKER.add(("grade", uid, lid, k), 0)
    save_course(lid)
    save_progress(uid, lid)


# ------------------------------------------------------------------ pass rule (75%), reset, chests
def stage_stats_for(uid, lid):
    L = LES[lid]; P = get_prog(uid, lid); out = {}
    for s in L["course"]["stages"]:
        qids = s["question_ids"]; total = len(qids)
        recs = [P["answers"].get(f"{s['id']}:{q}") for q in qids]
        graded = [r for r in recs if r and r["status"] == "done" and r.get("score") is not None]
        avg = round(sum(r["score"] for r in graded) / total) if total and len(graded) == total else None
        passed = bool(P["read"].get(s["id"])) if total == 0 else (avg is not None and avg >= PASS)
        out[s["id"]] = {"total": total, "answered": len([r for r in recs if r]), "graded": len(graded), "avg": avg, "passed": passed}
    return out


def reset(uid, lid, sid=None):
    with LOCK:
        P = get_prog(uid, lid)
        if sid:
            for k in [k for k, r in P["answers"].items() if r["sid"] == sid and not r.get("exam")]: del P["answers"][k]
            P["stage_done"].pop(sid, None)
        else: P["answers"].clear(); P["exams"].clear(); P["stage_done"].clear(); P["read"].clear()
    save_progress(uid, lid)


def claim_chest(uid, lid, sid):
    with LOCK:
        P = get_prog(uid, lid); ch = P.setdefault("chests", {})
        if sid in ch or not stage_stats_for(uid, lid).get(sid, {}).get("passed"): raise ValueError("locked")
        ch[sid] = time.time(); add_xp(uid, 15, 10)
    save_progress(uid, lid); save_user(uid)


def stage_of(lid, qid):
    for s in LES[lid]["course"]["stages"]:
        if qid in s["question_ids"]: return s["id"]


def submit_answer(uid, lid, qid, answer, exam_id=None):
    with LOCK:
        if not visible(uid, lid): raise ValueError("bad_request")
        P = get_prog(uid, lid); sid = stage_of(lid, qid)
        if not sid: raise ValueError("bad_question")
        regen_hearts(uid)
        if not U[uid]["is_admin"] and stats(uid)["hearts"] <= 0: raise ValueError("no_hearts")
        sg = LES[lid]["course"]["stages"]; idx = next(i for i, x in enumerate(sg) if x["id"] == sid)
        if idx > 0 and not stage_stats_for(uid, lid)[sg[idx - 1]["id"]]["passed"]: raise ValueError("locked")
        key = f"{exam_id or sid}:{qid}"
        if exam_id and not any(e["id"] == exam_id and qid in e["qids"] for e in P["exams"]): raise ValueError("bad_exam")
        old = P["answers"].get(key)
        if old and old["status"] in ("queued", "grading"): return key
        P["answers"][key] = {"key": key, "sid": sid, "qid": qid, "exam": exam_id, "answer": answer[:4000], "status": "queued", "text": "",
                             "score": None, "error": None, "ts": time.time(), "lang": U[uid]["d"]["lang"]}
        touch_streak(uid); give_badge(uid, "first_answer"); stage = _stage(lid, sid)
        if not exam_id and sid not in P["stage_done"] and all(f"{sid}:{x}" in P["answers"] for x in stage["question_ids"]):
            P["stage_done"][sid] = {"ts": time.time()}; add_xp(uid, 20, 5); give_badge(uid, "stage1")
    save_progress(uid, lid); save_user(uid); WORKER.add(("grade", uid, lid, key), 0)
    return key


def mark_read(uid, lid, sid):
    with LOCK:
        st = _stage(lid, sid)
        if not st or not visible(uid, lid): return
        P = get_prog(uid, lid); P["read"][sid] = True
        if not st["question_ids"] and sid not in P["stage_done"]:
            P["stage_done"][sid] = {"ts": time.time()}; add_xp(uid, 15, 3); give_badge(uid, "stage1")
    save_progress(uid, lid); save_user(uid)


def start_exam(uid, lid):
    with LOCK:
        if not visible(uid, lid): raise ValueError("bad_request")
        P = get_prog(uid, lid)
        if not all(v["passed"] for v in stage_stats_for(uid, lid).values()): raise ValueError("locked")
        cur = next((e for e in P["exams"] if not e.get("done") and not all(f"{e['id']}:{x}" in P["answers"] for x in e["qids"])), None)
        if cur: return cur["id"]
        ids = [q["id"] for q in LES[lid]["course"]["questions"]]; random.shuffle(ids)
        ex = {"id": f"x{len(P['exams']) + 1}", "qids": ids[:int(os.environ.get("EXAM_SIZE", "10"))], "ts": time.time(), "done": False}
        P["exams"].append(ex)
    save_progress(uid, lid)
    return ex["id"]


# ------------------------------------------------------------------ share a lesson as a file
def export_lesson(lid):
    with LOCK:
        c = LES[lid]["course"]
        if c["status"] != "ready" or not c["stages"] or any(not s["sections"] for s in c["stages"]): raise ValueError("not_ready")
        return {"format": "foxy-lesson", "version": 1, "course": {"title": c["title"], "lang": c.get("lang"), "questions": c["questions"],
                "stages": [{k: s[k] for k in ("title", "emoji", "outline", "question_ids", "notes", "sections")} for s in c["stages"]]}}


def import_lesson(uid, data):
    try:
        if not isinstance(data, dict) or data.get("format") != "foxy-lesson": raise ValueError
        c = data["course"]; qs = [{"id": int(q["id"]), "text": str(q["text"])[:600]} for q in c["questions"]][:200]
        ids = {q["id"] for q in qs}; stages = []
        for s in c["stages"][:12]:
            secs = [{"title": str(x["title"])[:120], "body": str(x["body"])[:4000]} for x in s["sections"]][:12]
            if not secs: continue
            stages.append({"id": f"s{len(stages) + 1}", "title": str(s["title"])[:80], "emoji": str(s.get("emoji") or "📘")[:8],
                           "outline": [str(o)[:80] for o in s.get("outline", [])][:6] or [str(s["title"])[:80]],
                           "question_ids": [int(x) for x in s.get("question_ids", []) if int(x) in ids], "notes": str(s.get("notes", ""))[:20000],
                           "status": "ready", "sections": secs, "partial": None, "error": None})
        if not stages or not qs: raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("bad_file")
    lid = uuid.uuid4().hex[:8]
    _insert_lesson(uid, {"id": lid, "title": str(c.get("title") or "Ders")[:60], "custom_title": True, "created": time.time(), "status": "ready",
                         "error": None, "lang": str(c.get("lang") or "tr")[:8], "questions": qs, "stages": stages})
    return lid


# ------------------------------------------------------------------ admin
def set_sharing(lid, user_ids, all_users):
    with LOCK:
        L = LES.get(lid)
        if not L: raise ValueError("bad_request")
        L["shared"] = [int(x) for x in user_ids if int(x) in U and int(x) != L["owner"]]; L["shared_all"] = bool(all_users)
    save_course(lid)


def admin_overview():
    with LOCK:
        users = []
        for uid, u in U.items():
            st = u["d"]["stats"]
            users.append({"id": uid, "username": u["username"], "is_admin": u["is_admin"], "disabled": u["disabled"], "has_key": bool(dec(u["d"].get("own_key", ""))),
                          "xp": st["xp"], "gems": st["gems"], "hearts": st["hearts"], "streak": st["streak"],
                          "lessons": len([1 for L in LES.values() if L["owner"] == uid])})
        lessons = [{"id": lid, "title": L["course"]["title"], "owner": L["owner"], "owner_name": U.get(L["owner"], {}).get("username", "?"), "status": L["course"]["status"],
                    "shared": L["shared"], "shared_all": L["shared_all"], "stages": len(L["course"]["stages"])} for lid, L in LES.items()]
        return {"users": users, "lessons": sorted(lessons, key=lambda x: x["title"])}


def migrate_legacy(admin_uid):
    """Bring the old single-user data (data/lessons/*, data/settings.json) into the new database, owned by the admin."""
    old = DATA / "lessons"
    try:
        if not old.is_dir() or not any(old.iterdir()): return 0
    except OSError: return 0
    n = 0
    for d in sorted(old.iterdir()):
        try:
            course = json.loads((d / "course.json").read_text(encoding="utf-8"))
            if course["id"] in LES: continue
            notes = (d / "notes.txt").read_text(encoding="utf-8") if (d / "notes.txt").exists() else ""
            _insert_lesson(admin_uid, course, notes)
            P = json.loads((d / "progress.json").read_text(encoding="utf-8")) if (d / "progress.json").exists() else _empty_progress()
            for k in ("read", "answers", "exams", "stage_done", "chests"): P.setdefault(k, {} if k != "exams" else [])
            with LOCK: PROG[(admin_uid, course["id"])] = P
            save_progress(admin_uid, course["id"]); n += 1
            if course["status"] in ("analyzing", "building"): WORKER.add(("analyze" if course["status"] == "analyzing" else "stage", course["id"]), 1)
        except Exception: traceback.print_exc()
    f = DATA / "settings.json"
    if f.exists():
        try:
            s = json.loads(f.read_text(encoding="utf-8")); d = U[admin_uid]["d"]
            for k in ("lang", "mascot", "sound"):
                if k in s: d[k] = s[k]
            d["stats"].update({k: v for k, v in s.get("stats", {}).items() if k in d["stats"]}); save_user(admin_uid)
        except Exception: pass
    sf = DATA / "secret.json"
    if sf.exists() and not get_setting("api_key_enc"):
        try: set_setting("api_key_enc", enc(json.loads(sf.read_text(encoding="utf-8")).get("GEMINI_API_KEY", "")))
        except Exception: pass
    try: old.rename(DATA / "lessons_migrated")
    except OSError: pass
    return n


# ------------------------------------------------------------------ state for the UI
def me(uid):
    u = U[uid]; own = dec(u["d"].get("own_key", "")); ctx = ai_ctx(uid)
    return {"id": uid, "username": u["username"], "is_admin": u["is_admin"], "can_ai": can_ai(uid), "can_upload": can_ai(uid),
            "has_own_key": bool(own) or (u["is_admin"] and bool(ctx["key"])), "key_source": ctx["source"],
            "key_hint": ("•••• " + (own if not u["is_admin"] else ctx["key"])[-4:]) if (own or (u["is_admin"] and ctx["key"])) else ""}


def state(uid):
    with LOCK:
        regen_hearts(uid); u = U[uid]; d = u["d"]; active = active_lesson(uid); lessons = []
        for lid in sorted(visible_ids(uid), key=lambda i: -LES[i]["course"]["created"]):
            L = LES[lid]; c = L["course"]; P = get_prog(uid, lid); sg = c["stages"]
            lessons.append({"id": lid, "title": c["title"], "status": c["status"], "created": c["created"], "total_q": len(c["questions"]),
                            "answered": len([k for k in P["answers"] if not P["answers"][k].get("exam")]), "stages": len(sg),
                            "ready": len([s for s in sg if s["status"] == "ready"]), "mine": L["owner"] == uid, "can_manage": manages(uid, lid),
                            "owner_name": U.get(L["owner"], {}).get("username", "?")})
        course = progress = None
        if active:
            course = json.loads(json.dumps(LES[active]["course"]))
            for s in course["stages"]: s.pop("notes", None)
            progress = json.loads(json.dumps(get_prog(uid, active))); progress["stage_stats"] = stage_stats_for(uid, active); progress.setdefault("chests", {})
        st = dict(d["stats"])
        if st["last_day"] not in (_day(), _day(1)): st["streak"] = 0
        if st["last_day"] != _day(): st["daily_xp"] = 0
        ai = ai_status(uid); ctx = ai_ctx(uid)
        if not can_ai(uid): ai = {"state": ai["state"] if ai["state"] in ("ok", "cooling", "quota", "nokey", "unknown") else "error", "cooldown_left": ai["cooldown_left"], "exhausted": [], "fallback": "", "mode": "", "primary": "", "model": "", "message": ""}
        ai["key_source"] = ctx["source"]
        out = {"me": me(uid), "settings": {"lang": d["lang"], "mascot": d["mascot"], "sound": d["sound"], "active": active, "offline": bool(d["offline"]) if can_ai(uid) else False,
                                           "model": (get_setting("default_model") if u["is_admin"] else d["model"]) if can_ai(uid) else ""},
               "stats": st, "lessons": lessons, "course": course, "progress": progress, "notifications": list(reversed(d["notifications"]))[:40], "ai": ai,
               "server_time": time.time(), "constants": {"heart_price": HEART_PRICE}}
    out["busy"] = WORKER.busy_for(uid)
    return out


# ------------------------------------------------------------------ helper chat (streamed)
def chat_stream(uid, lid, sid, qid, message, history):
    with LOCK:
        d = U[uid]["d"]; mascot, ui = d["mascot"], LANG_NAME.get(d["lang"], "Turkish"); ctx = ""
        if lid and visible(uid, lid):
            L = LES[lid]; st = _stage(lid, sid) if sid else None; ctx = f'Lesson: {L["course"]["title"]}\n'
            if st: ctx += f'Current topic: {st["title"]}\nNOTES:\n{st["notes"][:8000]}\n'
            q = next((q for q in L["course"]["questions"] if q["id"] == qid), None) if qid else None
            if q: ctx += f'The student is looking at this question: {q["text"]}\n'
    system = (f"You are {MASCOT_NAME.get(mascot, 'Foxy')}, {MASCOT_LOOK.get(mascot, 'a friendly mascot')} who helps a student study. "
              f"ALWAYS answer in {ui}. Be warm, short and simple (max ~120 words), use the notes when relevant, explain step by step if asked, "
              "and translate any text when asked. Do not just give away the answer to a question the student is practising unless they ask for it.\n" + ctx)
    contents = [{"role": "user" if h.get("role") == "user" else "model", "parts": [{"text": str(h.get("text", ""))[:1500]}]} for h in (history or [])[-6:]]
    contents.append({"role": "user", "parts": [{"text": message[:2000]}]})
    q, stop = queue.Queue(), threading.Event()

    def run():
        try: gen(uid, contents, system=system, on_text=lambda t: q.put(("t", t)), max_tokens=2048, attempts=3, cancel=stop.is_set, prefer="cheap")
        except GeminiError as e: q.put(("e", {"kind": e.kind, "message": str(e)[:200], "retry": int(e.retry_after)}))
        except Exception as e: q.put(("e", {"kind": "error", "message": str(e)[:200]}))
        q.put(("d", None))
    threading.Thread(target=run, daemon=True).start()
    try:
        while True:
            try: kind, val = q.get(timeout=1)
            except queue.Empty: yield {"w": ai_status(uid)["cooldown_left"]}; continue
            if kind == "t": yield {"t": val}
            elif kind == "e": yield {"error": val}
            else: yield {"done": True}; break
    finally: stop.set()


def init():
    load_all(); WORKER.start(); resume_all()
