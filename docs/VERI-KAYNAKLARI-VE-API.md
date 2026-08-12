# Veri Kaynakları ve API Rehberi

Gökdoğan Intelligence, veri sağlayıcılarının erişim biçimini değiştirmez. Kaynak anahtarsızsa doğrudan, API anahtarı gerekiyorsa kullanıcının kendi anahtarıyla çalışır.

## Anahtar yönetimi ilkeleri

- API anahtarı kaynak koda gömülmez.
- `.env` veya anahtar dosyaları GitHub'a commit edilmemelidir.
- Uygulama anahtarı yerel çalışma katmanına kaydeder ve runtime'a uygular.
- `API SİSTEMİNİ TEST ET` anahtar değerini geri göstermeden durum kontrolü yapar.
- Sağlayıcının geçersiz anahtarını, ücretli plan şartını veya kotasını uygulama aşamaz.

## Sağlayıcı matrisi

| Sağlayıcı / aile | Kullanım | Anahtar durumu |
|---|---|---|
| adsb.lol | ADS-B hava gözlemleri | Genellikle kamu erişimi; sağlayıcı koşulları geçerli |
| OpenSky Network | Hava aracı zenginleştirme / kimlikli erişim | Bazı özelliklerde hesap/kimlik doğrulama yararlı veya gerekli |
| Airframes.io | ACARS/VDL/airframe zenginleştirme | API anahtarı gerekir |
| AISStream | Canlı AIS akışı | API anahtarı gerekir |
| Global Fishing Watch | Deniz/balıkçılık etkinliği zenginleştirme | Özelliğe/endpoint'e göre token gerekebilir |
| Sentinel Hub / Copernicus | Optik/SAR görüntü iş akışları | İlgili hesap/istemci kimliği gerekir |
| TomTom | Trafik akışı/olay | API anahtarı gerekir |
| Shodan | Yetkili internet varlığı araması | API anahtarı gerekir |
| Finnhub | Piyasa zenginleştirmesi | İsteğe bağlı API anahtarı |
| Open-Meteo | Hava ve bazı çevresel veriler | Kamu endpoint'leri anahtarsız olabilir |
| RainViewer | Radar | Sağlayıcının güncel koşulları geçerli |
| NASA/USGS/NOAA | Afet/uydu/uzay havası | Çoğu kamu servisi; endpoint koşulları geçerli |

## Kamu kamera / CCTV kaynakları

Gökdoğan kaynak kodunda veya release paketinde özel kamera kimlik bilgileri bulunmamalıdır. Desteklenen yaklaşım:

- kamu trafik kamera API'leri,
- belediye/ulaşım kurumu açık katalogları,
- operatörün yetkili biçimde eklediği resmi URL listeleri.

Bir kamera kaynağı parola, VPN veya kapalı ağ gerektiriyorsa yalnız yetkili kullanıcı kendi ortamında yapılandırmalıdır; Gökdoğan erişim kontrolü aşmaz.

## Kamu kamera sağlayıcıları için güncel notlar

- **Singapore LTA DataMall:** Dinamik API'ler kayıtlı kullanıcıya verilen Account Key ile çalışır. LTA, 30 Haziran 2026 sonrasında trafik kamera kapsamını Woodlands/Tuas kontrol noktaları, bu noktalara giden bazı AYE/BKE kameraları ve Sentosa Gateway ile sınırladığını duyurmuştur. Kaynak sayısının azalması Gökdoğan hatası değildir.
- **Ontario 511:** Resmî `GET Cameras` API'si kamera kimliği, yol, yön, enlem/boylam ve diğer alanları sağlayabilir.
- **ASFINAG:** Trafik verisi portalı kamuya açık webcam verilerini trafik veri hizmetinin parçası olarak sunar. Kamuya açık webcam ile erişim kontrollü operasyon kameraları aynı şey değildir.

Bu sağlayıcıların güncel kullanım şartları ve API belgeleri, uygulama kaynak kodundan önce gelir.

## Hava ve deniz verilerinde eksik alanlar

ADS-B/AIS yayınları her alanı sağlamaz. Şu durumlar normaldir:

- kalkış/varış bilinmiyor,
- rota bilinmiyor,
- uçak/gemi tipi bilinmiyor,
- operatör bilinmiyor,
- geçmiş iz kısa,
- son mesaj eski.

Zenginleştirme sağlayıcısı eklenirse bazı alanlar tamamlanabilir.

## Kaynak tazeliği

Her sağlayıcının güncelleme aralığı farklıdır. UI'daki canlılık göstergesi veri kaynağının son başarılı güncellemesine göre yorumlanmalıdır.

## Referans bağlantıları

Ayrıntılı sağlayıcı, lisans ve atıf listesi için [`../DATA-ATTRIBUTION.md`](../DATA-ATTRIBUTION.md) belgesine bakın.
