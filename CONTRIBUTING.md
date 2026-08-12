# Gökdoğan Intelligence'a Katkı Rehberi

Gökdoğan Intelligence'a katkıda bulunmak istediğiniz için teşekkürler.

Bu proje; kamuya açık veya kullanım yetkisi bulunan OSINT/veri kaynaklarını Türkçe, harita tabanlı bir masaüstü çalışma alanında birleştirmeyi amaçlar. Katkıların güvenli, sürdürülebilir ve geriye dönük uyumlu olması beklenir.

## Başlamadan önce

1. Mevcut Issues bölümünü kontrol edin.
2. Büyük değişikliklerde önce bir özellik isteği veya tasarım tartışması açın.
3. Güvenlik açığını herkese açık Issue olarak paylaşmayın; `SECURITY.md` yönergelerini izleyin.
4. API anahtarı, token, parola, özel anahtar, kullanıcı verisi veya çalışma zamanı veritabanı commit etmeyin.

## Geliştirme ilkeleri

- Kullanıcıya görünen yeni metinler Türkçe olmalıdır.
- Kamuya açık veya yetkili veri kaynakları kullanılmalıdır.
- Erişim kontrolü aşma, parola kırma, kapalı kamera keşfi veya hassas kişi/hedef takibi eklenmemelidir.
- Yeni sağlayıcılarda lisans, atıf, kota ve API anahtarı gereksinimi belgelenmelidir.
- Bir kaynak geçici olarak çevrimdışı olduğunda uygulama çökmemeli; sağlık/fallback/cache davranışı tercih edilmelidir.
- Gizli bilgiler hiçbir log, hata mesajı veya API yanıtında düz metin olarak gösterilmemelidir.

## Yerel geliştirme

Windows kaynak derlemesi için proje kökündeki `START-HERE.bat` kullanılabilir. Bu akış bağımlılıkları, release kapılarını, testleri, Tauri/Rust derlemesini ve Windows paketlemeyi doğrular.

Bileşenler:

- Frontend: TypeScript / Next.js / MapLibre
- Backend: Python / FastAPI
- Desktop: Rust / Tauri / WebView2

## Değişiklik göndermeden önce

Mümkün olduğunda:

- ilgili backend testlerini çalıştırın,
- frontend lint/typecheck/test kapılarını çalıştırın,
- Rust/Tauri testlerini çalıştırın,
- yeni JSON/YAML yapılandırmalarının geçerli olduğunu doğrulayın,
- yeni veri sağlayıcısı ekliyorsanız `DATA-ATTRIBUTION.md` ve ilgili dokümantasyonu güncelleyin.

## Commit mesajları

Kısa ve açıklayıcı mesajlar tercih edilir:

- `fix: AIS yeniden bağlantı davranışını düzelt`
- `feat: yeni kamu afet kaynağı ekle`
- `docs: API kurulum notlarını güncelle`
- `test: Windows runtime regresyonunu genişlet`

## Pull Request

Pull Request açıklamasında şunları belirtin:

- ne değişti,
- neden gerekliydi,
- nasıl test edildi,
- kullanıcı arayüzü değiştiyse ekran görüntüsü,
- yeni dış kaynak varsa lisans/atıf/API gereksinimi.

PR göndererek proje davranış kurallarına ve lisans koşullarına uymayı kabul etmiş olursunuz.
