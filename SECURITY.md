# Güvenlik Politikası — Gökdoğan Intelligence

**Türkçe** | [English](SECURITY.en.md)

## Desteklenen sürümler

Aktif olarak desteklenen kamu sürümü `v1.x` serisidir. Güvenlik düzeltmeleri mümkün olduğunda en güncel kararlı sürüme uygulanır.

## Güvenlik açığı bildirme

Bir güvenlik açığı tespit ederseniz bunu herkese açık GitHub Issue, Discussion, ekran görüntüsü veya sosyal medya gönderisi olarak yayımlamayın.

GitHub repository üzerindeki **Security** bölümünde Private Vulnerability Reporting kullanılabiliyorsa onu tercih edin. Bu özellik kullanılamıyorsa, açık Issue açmadan önce proje sahibiyle GitHub profili üzerinden özel iletişim kanalı kurun.

Bildirimde mümkün olduğunca şunları paylaşın:

- etkilenen Gökdoğan sürümü,
- sorunun kısa teknik açıklaması,
- güvenli ve minimum tekrar üretme adımları,
- beklenen etki,
- varsa önerilen düzeltme.

## Kesinlikle paylaşmayın

- gerçek API anahtarları veya tokenlar,
- parolalar,
- PFX/PEM/private key dosyaları,
- kişisel veriler,
- üçüncü taraf sistemlerden izinsiz elde edilmiş içerikler,
- kapalı kamera/sistem kimlik bilgileri,
- hassas kişi veya operasyonel hedef verileri.

## Projenin güvenlik yaklaşımı

Release paketi aşağıdaki kontrolleri kullanır:

- `scripts/check_release_cleanliness.py`,
- runtime bütünlük manifesti,
- SHA-256 artifact özeti,
- release attestation / provenance,
- bağımlılık kilit dosyaları,
- Windows runtime self-test,
- GitHub Actions CI ve release kapıları.

Windows üretim dağıtımında Authenticode code-signing sertifikası kullanılması önerilir. Sertifika ve özel anahtarı kaynak koda veya release paketine gömülmemelidir.

## API anahtarları

API anahtarları GitHub deposuna commit edilmemelidir. `.env.example` yalnız örnek değişken adları ve güvenli örnek değerler içermelidir. Gerçek anahtarlar yerel kullanıcı ortamında/güvenli saklama katmanında tutulmalıdır.

## Kapsam dışı

Gökdoğan Intelligence erişim kontrolü aşma, parola kırma, özel/kapalı kamera keşfi veya hassas kişi/hedef takibi amacıyla tasarlanmamıştır. Bu tür yetenek talepleri güvenlik açığı veya desteklenen kullanım senaryosu olarak değerlendirilmez.
