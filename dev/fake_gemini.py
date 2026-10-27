"""Tiny fake Gemini server for offline testing:  python dev/fake_gemini.py
then run the app with  GEMINI_BASE_URL=http://127.0.0.1:9099/v1beta GEMINI_API_KEY=x GEMINI_MIN_GAP=1 python app.py
Every 7th call returns a 429 so you can see the cooldown logic work."""
import json, time, re
from flask import Flask, request, Response
app = Flask(__name__); N = [0]

def answer(prompt):
    if "Split the material" in prompt:
        qs = re.findall(r"^(\d+)\. ", prompt.split("QUESTIONS:")[-1], re.M)
        h = max(1, len(qs) // 2)
        notes = prompt.split("NOTES:")[1]
        first = " ".join(notes.split()[:8])
        second = " ".join(notes.split()[len(notes.split()) // 2:][:8])
        return json.dumps({"title": "Demo lesson", "language": "tr", "topics": [
            {"title": "Konu bir", "emoji": "🧪", "start_marker": first, "question_ids": [int(x) for x in qs[:h]], "outline": ["Giriş", "Detay"]},
            {"title": "Konu iki", "emoji": "🌍", "start_marker": second, "question_ids": [int(x) for x in qs[h:]], "outline": ["Temel", "Örnek", "Özet"]}]})
    if "SCORE:" in prompt and "STUDENT ANSWER: kötü" in prompt: return "SCORE: 30\nCevabın eksik. Notlara tekrar bak."
    if "SCORE:" in prompt: return "SCORE: 80\nGüzel cevap! Ana fikri yakaladın, küçük bir eksik var. İdeal cevap: kısa bir özet."
    if "### <section title>" in prompt:
        return "".join(f"### Bölüm {i}\nBu **önemli** bir kavramdır.\n- madde bir\n- madde iki\n\n" for i in range(1, 4))
    if prompt.strip().startswith("Reply with"): return "OK"
    return "Merhaba! Ben yardımcı karakterim. Bunu birlikte çözelim."

@app.get("/v1beta/models")
def models():
    return {"models": [{"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
                       {"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": ["generateContent"]},
                       {"name": "models/gemini-embedding-001", "supportedGenerationMethods": ["embedContent"]}]}

@app.post("/v1beta/models/<m>:<act>")
def gen(m, act):
    import os
    if os.environ.get("FAKE_DAILY") and "lite" not in m:
        return Response(json.dumps({"error": {"code": 429, "message": "You exceeded your current quota", "details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}), 429, mimetype="application/json")
    N[0] += 1
    if N[0] % 7 == 0:
        return Response(json.dumps({"error": {"code": 429, "message": "Quota exceeded. Please retry in 2s.", "details": [{"retryDelay": "2s"}]}}), 429, mimetype="application/json")
    body = request.get_json()
    prompt = body["contents"][-1]["parts"][0]["text"] + (body.get("systemInstruction") or {}).get("parts", [{}])[0].get("text", "")
    prompt = body["contents"][-1]["parts"][0]["text"]
    text = answer(prompt)
    if act.startswith("stream"):
        def s():
            words = text.split(" ")
            for i in range(0, len(words), 3):
                yield "data: " + json.dumps({"candidates": [{"content": {"parts": [{"text": " ".join(words[i:i+3]) + " "}]}}]}) + "\r\n\r\n"
                time.sleep(0.15)
        return Response(s(), mimetype="text/event-stream")
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}

if __name__ == "__main__": app.run(port=9099)
