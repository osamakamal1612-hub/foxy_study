# Foxy Study — ders sitesi / موقع دراسة 

## Çalıştırma / التشغيل
1. `pip install -r requirements.txt`
2. `.env.example` dosyasını `.env` olarak kopyala ve anahtarını yaz: `GEMINI_API_KEY=...`
   (انسخ `.env.example` إلى `.env` وضع مفتاحك. لا تشارك المفتاح مع أحد.)
3. `python app.py` → tarayıcıda `http://127.0.0.1:5000`

## Nasıl çalışır / كيف يعمل
- Soru dosyası + anlatım dosyası yükle (txt/md; istersen pdf/docx için `pypdf`, `python-docx` kur).
- Yapay zekâ konuları ayırır → her konu bir **aşama** olur. Aşama hazır olunca haritada belirir, kalanlar arka planda hazırlanır.
- Her aşama: kısa anlatım kartları → yazılı cevaplı sorular. Hepsi bitince **final sınavı** (tüm sorulardan rastgele).
- Cevap kontrolü uzun sürerse **sonraki soruya geç**; bitince 🔔 bildirimi gelir, tıklayınca cevap görünür.
- Dersler `data/lessons/` içinde saklanır; üstteki 📚 menüsünden istediğin an ders değiştirirsin, eskisi kaybolmaz.
- Karakter: Foxy / Pandi / Robo (⚙️ ayarlar). Alt köşedeki düğmeye basınca ona her şeyi sorabilirsin.

## Çevrimdışı deneme / تجربة بدون إنترنت
`python dev/fake_gemini.py` sonra: `GEMINI_BASE_URL=http://127.0.0.1:9099/v1beta GEMINI_API_KEY=x GEMINI_MIN_GAP=1 python app.py`
