"""Study app backend (Flask). Run:  python app.py   then open http://127.0.0.1:5000"""
import os, io, json
from pathlib import Path

ROOT = Path(__file__).parent


def load_env():
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
from flask import Flask, request, jsonify, Response, send_from_directory, stream_with_context  # noqa: E402
import engine  # noqa: E402
from gemini import gate  # noqa: E402

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024


def read_upload(f):
    raw = f.read()
    name = (f.filename or "").lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader  # pip install pypdf
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(raw)).pages)
    if name.endswith(".docx"):
        import docx  # pip install python-docx
        return "\n".join(p.text for p in docx.Document(io.BytesIO(raw)).paragraphs)
    for enc in ("utf-8-sig", "utf-16", "cp1254", "cp1256", "latin-1"):   # Turkish / Arabic Windows files too
        try: return raw.decode(enc)
        except Exception: continue
    return raw.decode("utf-8", "ignore")


def ok(**kw): return jsonify({"ok": True, **kw})
def fail(msg, code=400): return jsonify({"ok": False, "error": msg}), code


@app.get("/")
def index(): return send_from_directory("static", "index.html")


@app.get("/favicon.ico")
def favicon(): return send_from_directory("static", "favicon.svg", mimetype="image/svg+xml")


@app.get("/api/state")
def state(): return jsonify(engine.state())          # never talks to Gemini


@app.post("/api/settings")
def settings():
    d = request.get_json(silent=True) or {}
    with engine.LOCK:
        if d.get("lang") in ("tr", "ar"): engine.S["lang"] = d["lang"]
        if d.get("mascot") in engine.MASCOT_NAME: engine.S["mascot"] = d["mascot"]
        if "sound" in d: engine.S["sound"] = bool(d["sound"])
        if d.get("active") in engine.LES: engine.S["active"] = d["active"]
        engine.save_settings()
    return ok()


@app.post("/api/lessons")
def new_lesson():
    q, n = request.files.get("questions"), request.files.get("notes")
    if not q or not n: return fail("missing_files")
    try:
        lid = engine.create_lesson((request.form.get("title") or "").strip()[:60], read_upload(q), read_upload(n))
    except ValueError as e:
        return fail(str(e))
    except Exception as e:
        return fail("read_error: " + str(e)[:120])
    return ok(id=lid)


@app.post("/api/lessons/import")
def import_lesson():
    f = request.files.get("file")
    if not f: return fail("bad_file")
    try: data = json.loads(read_upload(f))
    except Exception: return fail("bad_file")
    try: return ok(id=engine.import_lesson(data))        # no AI call at all
    except ValueError as e: return fail(str(e))


@app.get("/api/lessons/<lid>/export")
def export_lesson(lid):
    if lid not in engine.LES: return fail("bad_request", 404)
    try: data = engine.export_lesson(lid)
    except ValueError as e: return fail(str(e))
    return Response(json.dumps(data, ensure_ascii=False), mimetype="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="foxy-lesson-{lid}.foxy"'})


@app.post("/api/reset")
def reset():
    d = request.get_json(silent=True) or {}
    if d.get("lesson") not in engine.LES: return fail("bad_request")
    engine.reset(d["lesson"], d.get("sid") or None); return ok()


@app.post("/api/chest")
def chest():
    d = request.get_json(silent=True) or {}
    if d.get("lesson") not in engine.LES: return fail("bad_request")
    try: engine.claim_chest(d["lesson"], d.get("sid"))
    except ValueError as e: return fail(str(e))
    return ok()


@app.post("/api/offline")
def offline():
    engine.set_offline(bool((request.get_json(silent=True) or {}).get("offline"))); return ok()


@app.delete("/api/lessons/<lid>")
def del_lesson(lid):
    engine.delete_lesson(lid); return ok()


@app.post("/api/retry")
def retry():
    d = request.get_json(silent=True) or {}
    if d.get("lesson") in engine.LES and d.get("what") in ("analyze", "stage", "grade"):
        engine.retry(d["lesson"], d["what"], d.get("sid"), d.get("key"))
    return ok()


@app.post("/api/read")
def read():
    d = request.get_json(silent=True) or {}
    if d.get("lesson") in engine.LES: engine.mark_read(d["lesson"], d.get("sid"))
    return ok()


@app.post("/api/answer")
def answer():
    d = request.get_json(silent=True) or {}
    text = str(d.get("answer", "")).strip()
    if d.get("lesson") not in engine.LES or not text: return fail("bad_request")
    try: key = engine.submit_answer(d["lesson"], int(d.get("qid", 0)), text, d.get("exam") or None)
    except (ValueError, TypeError) as e: return fail(str(e))
    return ok(key=key)


@app.post("/api/exam/start")
def exam_start():
    d = request.get_json(silent=True) or {}
    if d.get("lesson") not in engine.LES: return fail("bad_request")
    try: return ok(exam=engine.start_exam(d["lesson"]))
    except ValueError as e: return fail(str(e))


@app.post("/api/notifications/read")
def notif_read():
    ids = (request.get_json(silent=True) or {}).get("ids")
    with engine.LOCK:
        for n in engine.S["notifications"]:
            if ids is None or n["id"] in ids: n["read"] = True
        engine.save_settings()
    return ok()


@app.post("/api/ai/test")
def ai_test():
    return jsonify(gate.test())                       # the ONLY manual call: one tiny request


@app.post("/api/ai/key")
def ai_key():
    k = str((request.get_json(silent=True) or {}).get("key", "")).strip().strip('"').strip("'")
    if k and (len(k) < 20 or any(c.isspace() for c in k)): return fail("bad_key")
    engine.set_key(k)                                 # saved on this computer only, never sent back
    if gate.key(): engine.resume_paused()
    return ok()


@app.post("/api/ai/model")
def ai_model():
    try: engine.set_model(str((request.get_json(silent=True) or {}).get("model", "")))
    except ValueError as e: return fail(str(e))
    return ok()


@app.post("/api/ai/models")
def ai_models():
    from gemini import GeminiError
    try: return ok(models=gate.list_models())       # only when the button is pressed
    except GeminiError as e: return jsonify({"ok": False, "error": e.kind, "message": str(e)[:200]})


@app.post("/api/chat")
def chat():
    d = request.get_json(silent=True) or {}
    msg = str(d.get("message", "")).strip()
    if not msg: return fail("empty")

    def gen():
        for ev in engine.chat_stream(d.get("lesson"), d.get("sid"), d.get("qid"), msg, d.get("history")):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    engine.WORKER.start()
    engine.resume_all()
    key = bool(gate.key())
    print("\n  Study app: http://127.0.0.1:%s" % os.environ.get("PORT", "5000"))
    print("  Gemini key:", "found" if key else "MISSING -> copy .env.example to .env and paste your key", "\n")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), threaded=True, debug=False)
