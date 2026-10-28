# Foxy Study — çok kullanıcılı / متعدد المستخدمين

## 1) İlk çalıştırma / التشغيل الأول
1. `pip install -r requirements.txt`
2. `python app.py` → `http://127.0.0.1:5000`
3. **Kurulum sihirbazı** açılır: admin kullanıcı adı + şifreni belirle (şifre hash'lenerek kaydedilir; sihirbaz bir daha açılmaz).
   Eski tek kullanıcılı `data/lessons` klasörün varsa dersler ve ilerleme admin hesabına otomatik taşınır.
4. ⚙️ → **Ortak API anahtarı**: Gemini anahtarını gir (şifreli saklanır, arkadaşlar asla göremez).

## 2) Arkadaşlar / الأصدقاء
- 🛡️ **Yönetim**: arkadaşlara kullanıcı adı + şifre ver, elmas/XP/can ekle, hesabı kapat/sil.
- **Dersler ve görünürlük**: her dersi kimin göreceğini sen seçersin (kişi kişi ya da herkes).
- Arkadaş kendi API anahtarını ⚙️'den eklerse: ders yükleyebilir ve yapay zekâ/internet ayarlarını görür. Yüklediği dersi sadece kendisi görür; sen onu istediğin kişilerle paylaşırsın.
- Anahtarı olmayan arkadaş: yalnızca sana açılan dersleri çözer; cevap kontrolü ortak anahtarla yapılır. İnternet/model/test düğmeleri ona gösterilmez.
- Herkesin ilerlemesi, rozetleri, XP'si, canı, bildirimleri ayrıdır.

## 3) Can ve mağaza
- Cevap **50'nin altında** alırsa −1 ❤️. Canı bitince cevap veremez; 💎 ile mağazadan can alır (1 can = 5 💎, hepsi = 20 💎). Ayrıca 30 dakikada 1 can kendiliğinden gelir.
- 💎 XP'den gelir: her 10 XP = 1 💎 (sandık ve aşama ödülleri ekstra verir).
- Admin: mağaza ücretsiz, canı bitmez; kendine veya herkese 💎/XP/❤️ ekleyebilir.

## 4) Telefona uygulama olarak yükleme (PWA)
Site **https** ile yayınlandıktan sonra telefonda Chrome'da aç → ⋮ → **Ana ekrana ekle / Uygulamayı yükle** (iPhone: Safari → Paylaş → Ana Ekrana Ekle). Simge, tam ekran ve hızlı açılış dahildir (`manifest.webmanifest`, `sw.js`, `static/icons`).

## 5) Yayınlama / النشر
Uygulama **tek süreç + çok iş parçacığı** çalışır ve veriyi `DATA_DIR` içindeki SQLite'ta tutar → kalıcı disk gerekir.
- **Render / Railway / Fly.io:** repoyu yükle, `Dockerfile` ya da `Procfile` kullanılır. Kalıcı disk/volume'u `/data` olarak bağla; ortam değişkenleri: `APP_SECRET` (uzun rastgele metin), `COOKIE_SECURE=1`, `DATA_DIR=/data`. (`render.yaml` hazır.)
- **VPS (en ucuz):** `docker build -t foxy . && docker run -d -p 8000:8000 -v foxy-data:/data -e APP_SECRET=... foxy`, önüne Caddy/Nginx ile https koy.
- **Kendi bilgisayarın:** `python app.py` + Cloudflare Tunnel / ngrok ile https adresi aç (bilgisayar açık olduğu sürece).
- ❗ `-w 1` kalmalı (birden çok süreç olursa bellekteki durum bozulur). `APP_SECRET`'i değiştirme/kaybetme: kayıtlı API anahtarları çözülemez olur.

## 6) Güvenlik özeti
Şifreler `pbkdf2:sha256` ile hash'lenir · API anahtarları AES (Fernet) ile şifreli saklanır, hiçbir yanıtta dönmez · oturum çerezi HttpOnly + SameSite · CSRF başlığı zorunlu · giriş denemesi sınırı · CSP ve güvenlik başlıkları · giriş yapmadan hiçbir veri/yükleme yok.

---
## Önceki özellikler (kısa)

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
- 🎨 **Renkler karaktere göre:** Foxy = turuncu, Robo = mavi, Pandi = siyah-beyaz.
- ✨ **Model: Otomatik (varsayılan):** ders hazırlamada Flash, cevap kontrolü/sohbette Flash-Lite; biri dolunca diğerine geçer. Elle seçersen otomatik kapanır.
- Logo'ya tıkla = ana sayfa. Sorularda ◀ Önceki düğmesi (yazdığın taslak korunur). 🔔 içinde bildirimleri tek tek veya hepsini silebilirsin.
