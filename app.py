"""Study app backend (Flask) - multi-user.  Local:  python app.py   Hosting:  gunicorn -w 1 --threads 8 app:app"""
import os, io, json, time, threading
from pathlib import Path
from functools import wraps

ROOT = Path(__file__).parent


def load_env():
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
from flask import Flask, request, jsonify, Response, send_from_directory, stream_with_context, session  # noqa: E402
from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402
import engine  # noqa: E402
from gemini import gate_for, GeminiError  # noqa: E402

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config.update(SECRET_KEY=engine.APP_SECRET, MAX_CONTENT_LENGTH=12 * 1024 * 1024, SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
                  PERMANENT_SESSION_LIFETIME=30 * 24 * 3600)
engine.init()

CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
       "img-src 'self' data: blob:; connect-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")


@app.after_request
def headers(r):
    r.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "same-origin", "Content-Security-Policy": CSP})
    if request.path.startswith("/api/"): r.headers["Cache-Control"] = "no-store"
    return r


@app.before_request
def csrf_guard():                       # custom header cannot be sent cross-site without CORS approval
    if request.method in ("POST", "PUT", "DELETE") and request.path.startswith("/api/") and request.headers.get("X-Requested-With") != "foxy":
        return jsonify({"ok": False, "error": "csrf"}), 403


def ok(**kw): return jsonify({"ok": True, **kw})
def fail(msg, code=400): return jsonify({"ok": False, "error": msg}), code


def uid_now():
    uid = session.get("uid"); u = engine.U.get(uid) if uid else None
    return uid if u and not u["disabled"] else None


def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        uid = uid_now()
        if not uid: return fail("auth", 401)
        return f(uid, *a, **kw)
    return w


def admin_required(f):
    @wraps(f)
    def w(uid, *a, **kw):
        if not engine.U[uid]["is_admin"]: return fail("forbidden", 403)
        return f(uid, *a, **kw)
    return login_required(w)


def staff_required(f):                   # admin or teacher
    @wraps(f)
    def w(uid, *a, **kw):
        if not engine.staff(uid): return fail("forbidden", 403)
        return f(uid, *a, **kw)
    return login_required(w)


def ai_required(f):                      # AI settings: admin or users with their own key
    @wraps(f)
    def w(uid, *a, **kw):
        if not engine.can_ai(uid): return fail("forbidden", 403)
        return f(uid, *a, **kw)
    return login_required(w)


def read_upload(f):
    raw = f.read(); name = (f.filename or "").lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(raw)).pages)
    if name.endswith(".docx"):
        import docx
        return "\n".join(p.text for p in docx.Document(io.BytesIO(raw)).paragraphs)
    for enc in ("utf-8-sig", "utf-16", "cp1254", "cp1256", "latin-1"):
        try: return raw.decode(enc)
        except Exception: continue
    return raw.decode("utf-8", "ignore")


# ------------------------------------------------------------------ pages / pwa
@app.get("/")
def index(): return send_from_directory("static", "index.html")
@app.get("/favicon.ico")
def favicon(): return send_from_directory("static", "favicon.svg", mimetype="image/svg+xml")
@app.get("/manifest.webmanifest")
def manifest(): return send_from_directory("static", "manifest.webmanifest", mimetype="application/manifest+json")
@app.get("/sw.js")
def sw():
    r = send_from_directory("static", "sw.js", mimetype="application/javascript"); r.headers["Cache-Control"] = "no-cache"; return r


# ------------------------------------------------------------------ auth
FAILS, FLOCK = {}, threading.Lock()


def _throttled(key):
    with FLOCK:
        n, until = FAILS.get(key, (0, 0))
        return until > time.time()


def _fail(key):
    with FLOCK:
        n, until = FAILS.get(key, (0, 0)); n += 1
        FAILS[key] = (n, time.time() + 300 if n >= 8 else 0)
        if n >= 8: FAILS[key] = (0, time.time() + 300)


@app.get("/api/session")
def session_info():
    uid = uid_now()
    return jsonify({"setup": not engine.admin_exists(), "user": engine.me(uid) if uid else None})


@app.post("/api/setup")
def setup():
    if engine.admin_exists(): return fail("setup_closed", 403)          # the wizard is gone for good once an admin exists
    d = request.get_json(silent=True) or {}
    try: uid = engine.create_user(d.get("username"), d.get("password") or "", "admin")
    except ValueError as e: return fail(str(e))
    engine.migrate_legacy(uid)
    session.clear(); session["uid"] = uid; session.permanent = True
    return ok()


@app.post("/api/login")
def login():
    d = request.get_json(silent=True) or {}; name = str(d.get("username", "")).strip().lower()
    key = (request.remote_addr or "?") + "|" + name
    if _throttled(key) or _throttled(request.remote_addr or "?"): return fail("too_many", 429)
    uid = engine.verify_login(name, d.get("password"))
    if not uid:
        _fail(key); _fail(request.remote_addr or "?"); return fail("bad_login", 401)
    session.clear(); session["uid"] = uid; session.permanent = True
    engine.U[uid]["d"]["last_active"] = time.time(); engine.save_user(uid)
    return ok()


@app.post("/api/logout")
def logout(): session.clear(); return ok()


@app.post("/api/password")
@login_required
def change_password(uid):
    d = request.get_json(silent=True) or {}
    if not engine.check_password(uid, d.get("old")): return fail("bad_login")
    try: engine.set_password(uid, d.get("new") or "")
    except ValueError as e: return fail(str(e))
    return ok()


# ------------------------------------------------------------------ app data
@app.get("/api/state")
@login_required
def state(uid): return jsonify(engine.state(uid))            # never talks to Gemini


@app.post("/api/settings")
@login_required
def settings(uid):
    d = request.get_json(silent=True) or {}; u = engine.U[uid]["d"]
    if d.get("lang") in ("tr", "ar"): u["lang"] = d["lang"]
    if d.get("mascot") in engine.char_ids(): u["mascot"] = d["mascot"]
    if "sound" in d: u["sound"] = bool(d["sound"])
    if d.get("active"): engine.set_active(uid, d["active"])
    engine.save_user(uid); return ok()


@app.post("/api/lessons")
@login_required
def new_lesson(uid):
    q, n = request.files.get("questions"), request.files.get("notes")
    if not q or not n: return fail("missing_files")
    try: lid = engine.create_lesson(uid, (request.form.get("title") or "").strip()[:60], read_upload(q), read_upload(n))
    except ValueError as e: return fail(str(e), 403 if str(e) == "no_permission" else 400)
    except Exception as e: return fail("read_error: " + str(e)[:120])
    return ok(id=lid)


@app.post("/api/lessons/import")
@login_required
def import_lesson(uid):
    f = request.files.get("file")
    if not f: return fail("bad_file")
    try: data = json.loads(read_upload(f))
    except Exception: return fail("bad_file")
    try: return ok(id=engine.import_lesson(uid, data))
    except ValueError as e: return fail(str(e))


@app.get("/api/lessons/<lid>/export")
@login_required
def export_lesson(uid, lid):
    if not engine.manages(uid, lid): return fail("forbidden", 403)
    try: data = engine.export_lesson(lid)
    except ValueError as e: return fail(str(e))
    return Response(json.dumps(data, ensure_ascii=False), mimetype="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="foxy-lesson-{lid}.foxy"'})


@app.delete("/api/lessons/<lid>")
@login_required
def del_lesson(uid, lid):
    if not engine.manages(uid, lid): return fail("forbidden", 403)
    engine.delete_lesson(lid); return ok()


@app.post("/api/reset")
@login_required
def reset(uid):
    d = request.get_json(silent=True) or {}
    if not engine.visible(uid, d.get("lesson")): return fail("bad_request")
    engine.reset(uid, d["lesson"], d.get("sid") or None); return ok()


@app.post("/api/retry")
@login_required
def retry(uid):
    d = request.get_json(silent=True) or {}
    if d.get("what") in ("analyze", "stage", "grade"): engine.retry(uid, d.get("lesson"), d["what"], d.get("sid"), d.get("key"))
    return ok()


@app.post("/api/read")
@login_required
def read(uid):
    d = request.get_json(silent=True) or {}; engine.mark_read(uid, d.get("lesson"), d.get("sid")); return ok()


@app.post("/api/answer")
@login_required
def answer(uid):
    d = request.get_json(silent=True) or {}; text = str(d.get("answer", "")).strip()
    if not text: return fail("bad_request")
    try: key = engine.submit_answer(uid, d.get("lesson"), int(d.get("qid", 0)), text, d.get("exam") or None)
    except (ValueError, TypeError, KeyError) as e: return fail(str(e))
    return ok(key=key)


@app.post("/api/exam/start")
@login_required
def exam_start(uid):
    d = request.get_json(silent=True) or {}
    try: return ok(exam=engine.start_exam(uid, d.get("lesson")))
    except (ValueError, KeyError) as e: return fail(str(e))


@app.post("/api/chest")
@login_required
def chest(uid):
    d = request.get_json(silent=True) or {}
    if not engine.visible(uid, d.get("lesson")): return fail("bad_request")
    try: engine.claim_chest(uid, d["lesson"], d.get("sid"))
    except ValueError as e: return fail(str(e))
    return ok()


@app.post("/api/shop/buy")
@login_required
def shop(uid):
    try: engine.shop_buy(uid, (request.get_json(silent=True) or {}).get("item"))
    except ValueError as e: return fail(str(e))
    return ok()


@app.post("/api/shop/convert")
@login_required
def shop_convert(uid):
    try: engine.shop_convert(uid, (request.get_json(silent=True) or {}).get("xp"))
    except (ValueError, TypeError) as e: return fail(str(e))
    return ok()


@app.post("/api/notifications/read")
@login_required
def notif_read(uid):
    ids = (request.get_json(silent=True) or {}).get("ids"); d = engine.U[uid]["d"]
    with engine.LOCK:
        for n in d["notifications"]:
            if ids is None or n["id"] in ids: n["read"] = True
        engine.save_user(uid)
    return ok()


@app.post("/api/notifications/delete")
@login_required
def notif_delete(uid):
    d = request.get_json(silent=True) or {}; ud = engine.U[uid]["d"]
    with engine.LOCK:
        ids = None if d.get("all") else {int(x) for x in (d.get("ids") or []) if str(x).isdigit()}
        ud["notifications"] = [] if ids is None else [n for n in ud["notifications"] if n["id"] not in ids]; engine.save_user(uid)
    return ok()


# ------------------------------------------------------------------ AI settings
@app.post("/api/ai/key")
@login_required
def ai_key(uid):                         # everybody may add THEIR OWN key (admin: sets the shared default key)
    try: engine.set_own_key(uid, str((request.get_json(silent=True) or {}).get("key", "")))
    except ValueError as e: return fail(str(e))
    return ok()


@app.post("/api/offline")
@ai_required
def offline(uid): engine.set_offline(uid, bool((request.get_json(silent=True) or {}).get("offline"))); return ok()


@app.post("/api/ai/model")
@ai_required
def ai_model(uid):
    try: engine.set_model(uid, str((request.get_json(silent=True) or {}).get("model", "")))
    except ValueError as e: return fail(str(e))
    return ok()


@app.post("/api/ai/models")
@ai_required
def ai_models(uid):
    ctx = engine.ai_ctx(uid)
    try: return ok(models=gate_for(ctx["key"]).list_models(ctx["offline"]))
    except GeminiError as e: return jsonify({"ok": False, "error": e.kind, "message": str(e)[:200]})


@app.post("/api/ai/test")
@ai_required
def ai_test(uid):
    ctx = engine.ai_ctx(uid)
    return jsonify(gate_for(ctx["key"]).test(ctx["model"], lambda: engine.ai_ctx(uid)["offline"]))


@app.post("/api/chat")
@login_required
def chat(uid):
    d = request.get_json(silent=True) or {}; msg = str(d.get("message", "")).strip()
    if not msg: return fail("empty")

    def gen():
        for ev in engine.chat_stream(uid, d.get("lesson"), d.get("sid"), d.get("qid"), msg, d.get("history")):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
    return Response(stream_with_context(gen()), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ admin dashboard
@app.get("/api/admin/overview")
@admin_required
def admin_overview(uid): return jsonify({"ok": True, **engine.admin_overview()})


@app.post("/api/admin/users")
@admin_required
def admin_create(uid):
    d = request.get_json(silent=True) or {}
    try: new = engine.create_user(d.get("username"), d.get("password") or "", d.get("role") if d.get("role") in ("teacher", "student") else "student")
    except ValueError as e: return fail(str(e))
    return ok(id=new)


@app.post("/api/admin/users/<int:target>/password")
@admin_required
def admin_pw(uid, target):
    if target not in engine.U: return fail("bad_user")
    try: engine.set_password(target, (request.get_json(silent=True) or {}).get("password") or "")
    except ValueError as e: return fail(str(e))
    return ok()


@app.post("/api/admin/users/<int:target>/disable")
@admin_required
def admin_disable(uid, target):
    u = engine.U.get(target)
    if not u or u["is_admin"]: return fail("bad_user")
    u["disabled"] = bool((request.get_json(silent=True) or {}).get("disabled")); engine.save_user(target); return ok()


@app.delete("/api/admin/users/<int:target>")
@admin_required
def admin_delete(uid, target):
    try: engine.delete_user(target)
    except ValueError as e: return fail(str(e))
    return ok()


@app.post("/api/admin/users/<int:target>/grant")
@admin_required
def admin_grant(uid, target):
    d = request.get_json(silent=True) or {}
    try: engine.admin_grant(target, d.get("gems"), d.get("xp"), d.get("hearts"))
    except (ValueError, TypeError) as e: return fail(str(e))
    return ok()


@app.post("/api/admin/users/<int:target>/role")
@admin_required
def admin_role(uid, target):
    try: engine.set_role(target, (request.get_json(silent=True) or {}).get("role"))
    except ValueError as e: return fail(str(e))
    return ok()


@app.post("/api/lessons/<lid>/share")
@staff_required
def share_lesson(uid, lid):
    d = request.get_json(silent=True) or {}
    try: engine.set_sharing(uid, lid, d.get("users") or [], d.get("all"))
    except (ValueError, TypeError) as e: return fail(str(e), 403 if str(e) == "forbidden" else 400)
    return ok()


@app.get("/api/monitor")
@staff_required
def monitor(uid): return jsonify({"ok": True, **engine.monitor(uid)})


@app.get("/api/characters")
@login_required
def characters(uid): return jsonify({"ok": True, **engine.chars_public()})


@app.post("/api/admin/characters")
@admin_required
def admin_char(uid):
    try: cid = engine.admin_save_character(request.get_json(silent=True) or {})
    except (ValueError, TypeError) as e: return fail(str(e))
    return ok(id=cid)


@app.delete("/api/admin/characters/<cid>")
@admin_required
def admin_char_del(uid, cid):
    try: engine.admin_delete_character(cid)
    except ValueError as e: return fail(str(e))
    return ok()


@app.post("/api/admin/theme")
@admin_required
def admin_theme(uid):
    d = request.get_json(silent=True) or {}
    try: engine.admin_set_theme(d.get("char"), d.get("theme"))
    except ValueError as e: return fail(str(e))
    return ok()


@app.post("/api/admin/phrases")
@admin_required
def admin_phrases(uid):
    d = request.get_json(silent=True) or {}
    try: engine.admin_phrase(d.get("action"), d)
    except ValueError as e: return fail(str(e))
    return ok()


@app.post("/api/admin/phrase_mode")
@admin_required
def admin_phrase_mode(uid):
    d = request.get_json(silent=True) or {}
    try: engine.admin_phrase_mode(d.get("target"), d.get("mode"))
    except ValueError as e: return fail(str(e))
    return ok()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print("\n  Study app: http://127.0.0.1:%d" % port)
    print("  First run? Open the page and create the admin account.\n" if not engine.admin_exists() else "")
    app.run(host=os.environ.get("HOST", "0.0.0.0"), port=port, threaded=True, debug=False)
