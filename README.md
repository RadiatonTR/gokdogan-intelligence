# Gökdoğan Intelligence

[![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsors-EA4AAA?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/RadiatonTR)

**Türkçe, harita tabanlı açık kaynak OSINT ve küresel durum farkındalığı masaüstü platformu.**

Gökdoğan Intelligence; kamuya açık veya operatörün kullanım yetkisine sahip olduğu veri kaynaklarını tek bir Windows masaüstü çalışma alanında birleştirir. Amaç; farklı web sayfaları, API panelleri ve harita servisleri arasında sürekli geçiş yapmak yerine kaynakların durumunu, harita katmanlarını, olayları ve bağlantılı ayrıntıları tek arayüzde izleyebilmektir.

**Sürüm:** `v1.0.0` · **Teknik çekirdek:** `R24 / 0.10.3` · **Platform:** Windows 10/11 x64 · **Varsayılan dil:** Türkçe · **Lisans:** AGPL-3.0

> [!IMPORTANT]
> Gökdoğan Intelligence bir erişim kontrolü aşma aracı değildir. Yalnız kamuya açık veya kullanım yetkinizin bulunduğu kaynaklarla çalıştırılmalıdır. Özel/kapalı kameralar, yetkisiz sistemler, gizli kimlik bilgileri, kişi hedefli izleme veya hassas askerî hedefleme bu kamu sürümünün amacı değildir.

## Proje durumu

- Kaynak kodu: yayımlandı
- GitHub Sponsors: aktif
- CI ve Windows release workflow: mevcut
- İlk resmî sürüm: `v1.0.0` yayın hazırlığı tamamlanıyor

## Dokümantasyon

- [Kurulum](docs/KURULUM.md)
- [Kullanım Kılavuzu](docs/KULLANIM-KILAVUZU.md)
- [Veri Kaynakları ve API](docs/VERI-KAYNAKLARI-VE-API.md)
- [Referanslar](docs/REFERANSLAR.md)
- [Ekran Görüntüleri](docs/EKRAN-GORUNTULERI.md)
- [Sorun Giderme](docs/SORUN-GIDERME.md)
- [Yasal Uyarı ve Sorumlu Kullanım](docs/YASAL-UYARI-VE-SORUMLU-KULLANIM.md)
- [Katkı Rehberi](CONTRIBUTING.md)
- [Davranış Kuralları](CODE_OF_CONDUCT.md)
- [Güvenlik Politikası](SECURITY.md)
- [Destek / Donate](SUPPORT.md)
- [Sponsor Hedefleri](docs/SPONSOR-HEDEFLERI.md)

## Başlıca yetenekler

### Harita ve coğrafi çalışma alanı

- MapLibre tabanlı etkileşimli harita
- standart ve uydu altlıkları
- koordinat / yer / çağrı işareti araması
- katman açma-kapama ve filtreleme
- zaman makinesi ve geçmiş gözlem kayıtları
- kaynak tazelik/sağlık göstergeleri
- olay, rota ve varlık ayrıntı panelleri

### Havacılık

- kamu ADS-B kaynaklarından hava aracı gözlemleri
- sivil/ticari uçuşlar ve sağlayıcının yayımladığı diğer kamu gözlemleri
- çağrı işareti, tescil/ICAO, irtifa, hız ve yön gibi mevcut telemetri
- gözlenen rota izi ve zaman serisi
- OpenSky/Airframes gibi yapılandırılmış zenginleştirmeler

> Askerî görünüm yalnız kamuya açık gözlem/referans verisini sunmak içindir; gizli uçuş planı, kapalı telemetri veya hedefleme verisi sağlamaz.

### Denizcilik

- AISStream ve diğer yapılandırılmış kamu/yetkili deniz kaynakları
- MMSI/IMO ve gemi meta verisi mevcut olduğunda ayrıntı görünümü
- gözlenen rota/iz, yön ve hız
- canlı/önbellek/fallback davranışı
- Global Fishing Watch gibi isteğe bağlı açık veri zenginleştirmeleri

### Kamu kamera ve trafik görüntü kaynakları

- kamu kurumlarının yayımladığı trafik/kent kamera katalogları
- operatörün yetkili şekilde eklediği resmi kamu kamera listeleri
- sağlayıcı bağlantısını sistem tarayıcısında açma
- API anahtarı gerektiren sağlayıcılar için yerel anahtar yönetimi

Gökdoğan **kapalı CCTV sistemlerini taramaz, parola kırmaz ve erişim kontrolü aşmaz**.

### Afet, meteoroloji, haber, trafik ve piyasalar

- deprem, yangın, yanardağ ve küresel afet uyarıları
- hava tahmini, radar, hava kalitesi ve uzay havası
- Türkiye ve küresel haber başlıkları
- trafik akışı/olay verileri ve sağlayıcı yayımlıyorsa sınır bekleme süreleri
- döviz, değerli metaller, enerji/emtia, kripto ve endeks göstergeleri

### Uydu ve uzay

- CelesTrak TLE verileriyle uydu konumları
- NASA GIBS ve yapılandırılmış görüntü sağlayıcıları
- Copernicus/Sentinel tabanlı optik veya SAR görüntü iş akışları
- son mevcut görüntü zamanı ve sağlayıcı durumu

## Canlı veri durumları

| Durum | Anlamı |
|---|---|
| `CANLI` | Sağlayıcı güncel veri veriyor. |
| `GECİKMELİ` | Kaynak veri yayımlıyor ancak zaman farkı var. |
| `ÖNBELLEK` | Son başarılı veri gösteriliyor. |
| `ANAHTAR GEREKLİ` | İlgili özellik için kullanıcı API anahtarı gerekiyor. |
| `KAYNAK KAPALI` | Sağlayıcı erişilemiyor veya geçici hata veriyor. |
| `SINIRLI` | Kota, bölgesel kapsama veya lisans sınırlaması var. |

## Kurulum

### Son kullanıcı

GitHub Releases bölümünden yayımlanan Windows `Setup.exe` dosyasını ve SHA-256 manifestini indirin. Hash doğrulamasından sonra installer'ı çalıştırın.

### Kaynaktan derleme

1. Depoyu yeni ve boş bir klasöre klonlayın veya Source ZIP'i çıkarın.
2. `START-HERE.bat` çalıştırın.
3. Builder bağımlılıkları ve release kapılarını doğrular.
4. Frontend, backend ve Rust/Tauri testleri çalışır.
5. NSIS installer oluşturulur.
6. Kurulu runtime self-test yapılır.
7. Başarılı build sonunda `dist` altında Windows bundle ve Offline USB paketi oluşturulur.

Ayrıntılı kurulum: [`docs/KURULUM.md`](docs/KURULUM.md)

## API anahtarları

1. **Ayarlar → API Anahtarları** bölümünü açın.
2. Kullanacağınız sağlayıcıların anahtarlarını girin.
3. **API SİSTEMİNİ TEST ET** ile runtime durumunu doğrulayın.
4. Kaynak Sağlığı üzerinden sonucu kontrol edin.

Anahtarlar kaynak koduna yazılmamalı ve GitHub'a gönderilmemelidir.

## Uygulama görüntüleri

### Bölgesel operasyon haritası
![Bölgesel operasyon haritası](docs/screenshots/01-bolgesel-operasyon-haritasi.png)

### Küresel operasyon görünümü
![Küresel operasyon görünümü](docs/screenshots/02-kuresel-operasyon-gorunumu.png)

### Askerî hava aracı ayrıntı görünümü
<p align="center"><img src="docs/screenshots/03-askeri-hava-araci-detayi.png" alt="Askerî hava aracı ayrıntısı" width="520" /></p>

### Denizcilik, uzay ve altyapı katmanları
<p align="center"><img src="docs/screenshots/04-denizcilik-uzay-altyapi-katmanlari.png" alt="Denizcilik uzay altyapı katmanları" width="420" /></p>

### API ilk kurulum
<p align="center"><img src="docs/screenshots/05-api-ilk-kurulum.png" alt="API ilk kurulum" width="620" /></p>

### Entegrasyon hazırlık özeti
![Entegrasyon hazırlık özeti](docs/screenshots/06-entegrasyon-hazirlik-ozeti.png)

Daha fazla görsel: [`docs/EKRAN-GORUNTULERI.md`](docs/EKRAN-GORUNTULERI.md)

## Veri kaynakları ve referanslar

Örnek kaynak aileleri: adsb.lol, OpenSky Network, Airframes.io, AISStream, Global Fishing Watch, USGS, NASA FIRMS, NASA EONET, GDACS, Open-Meteo, RainViewer, NOAA, TomTom, TRT Haber, Anadolu Ajansı, GDELT, NASA GIBS, CelesTrak, Copernicus Data Space, OpenStreetMap, CARTO, Esri, OpenAQ ve Wikidata.

Her sağlayıcının kendi lisansı, kotası, bölgesel kapsamı ve kullanım koşulları geçerlidir. Ayrıntılar için [`DATA-ATTRIBUTION.md`](DATA-ATTRIBUTION.md) ve [`docs/REFERANSLAR.md`](docs/REFERANSLAR.md) dosyalarına bakın.

## Güvenlik ve topluluk

- API anahtarlarını commit etmeyin.
- Özel/kapalı sistemlerin erişim kontrolünü aşmayın.
- Kamu kamera kaynaklarını sağlayıcı lisans ve mahremiyet koşullarına göre kullanın.
- Hassas kişi/konum takibi veya operasyonel hedefleme amacıyla kullanmayın.
- Güvenlik açıklarını herkese açık Issue olarak paylaşmayın.
- Katkı göndermeden önce [`CONTRIBUTING.md`](CONTRIBUTING.md) dosyasını okuyun.

## ❤️ Projeyi destekleyin

Gökdoğan Intelligence ücretsiz ve açık kaynak olarak geliştirilmektedir.

[![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsors-EA4AAA?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/RadiatonTR)

**İlk hedef: 10 düzenli aylık sponsor.**

Destekler özellikle şu alanlara katkı sağlar:

- Windows build, release ve code-signing giderleri
- test ve kalite güvence altyapısı
- harita ve performans geliştirmeleri
- kamuya açık/yetkili veri kaynağı entegrasyonları
- güvenlik ve bağımlılık güncellemeleri
- dokümantasyon ve sürdürülebilir bakım

Ayrıntılar: [`SUPPORT.md`](SUPPORT.md)

> Sponsorluk herhangi bir özel, gizli, erişim kontrollü veya normalde erişilemeyen veri kaynağına erişim hakkı sağlamaz.
