# Foxy Study — Duolingo tarzı ders sitesi / موقع دراسة شبيه بدولينغو

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

## Gemini limitleri (429) / حدود الطلبات
- Gemini'ye **sadece gerektiğinde** gidilir: ders hazırlama, cevap kontrolü, sohbet, "bağlantıyı test et".
- Tüm istekler tek kapıdan geçer: istekler arası en az `GEMINI_MIN_GAP` sn, 429 gelince Gemini'nin söylediği süre kadar ortak bekleme, sonra otomatik devam. Çökme yok.
- Günlük limit dolarsa iş durur (⛔) ve "Tekrar dene" düğmesi çıkar. Sunucu yeniden başlarsa yarım kalan işler kaldığı yerden devam eder.
- Tarayıcı sadece yerel Python sunucusunu yoklar (hata olursa aralık büyür), Gemini'yi asla doğrudan çağırmaz.

## Çevrimdışı deneme / تجربة بدون إنترنت
`python dev/fake_gemini.py` sonra: `GEMINI_BASE_URL=http://127.0.0.1:9099/v1beta GEMINI_API_KEY=x GEMINI_MIN_GAP=1 python app.py`

## Yeni / جديد
- 🌐/✈️ **İnternet düğmesi:** tek tıkla yapay zekâ bağlantısını kes; bekleyen işler bağlanınca devam eder.
- **%75 kuralı:** bir aşamanın tüm sorularının ortalaması ≥ %75 değilse sonraki aşama gri/kilitli kalır. 🏋️ ile aşamayı sıfırlayıp baştan yapabilirsin.
- **Sandıklar 🎁:** aşamayı geçince açılır (+10 💎 +15 ⚡). **Final** için tüm aşamalar geçilmeli.
- **Ders dosyası (.foxy):** 📚 menüsünde ⬇️ ile indir; arkadaşın "Yeni ders → Ders dosyası içe aktar" ile yükler, yapay zekâya hiç gitmeden açılır.
- Sesler: ⚙️ içinde ses açma/kapama ve ses seviyesi.
- 🧠 **Model seçimi (⚙️):** Flash-Lite (günlük limit çok yüksek) / Flash / hesabındaki diğer modeller. Seçilen modelin günlük limiti dolarsa diğerine otomatik geçilir; her model için istek aralığı otomatik ayarlanır.
