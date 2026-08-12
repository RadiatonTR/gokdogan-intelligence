# GitHub Paylaşım Metni

## Repository adı

`gokdogan-intelligence`

## About / kısa açıklama

**Türkçe, harita tabanlı açık kaynak OSINT ve küresel durum farkındalığı masaüstü platformu.**

## Orta uzunlukta tanıtım

Gökdoğan Intelligence; kamuya açık veya operatörün kullanım yetkisine sahip olduğu havacılık, denizcilik, afet, meteoroloji, uydu/uzay, trafik, haber, diplomasi, piyasa, altyapı ve kamu kamera kaynaklarını tek bir Windows masaüstü çalışma alanında bir araya getiren Türkçe OSINT ve durum farkındalığı platformudur. MapLibre tabanlı harita arayüzü, FastAPI/Python backend'i ve Tauri/Rust masaüstü kabuğu ile farklı sağlayıcıların kaynak sağlığını, harita katmanlarını ve olay ayrıntılarını ortak bir arayüzde sunar.

## Uzun tanıtım

Gökdoğan Intelligence v1.0.0, farklı açık veri ve OSINT kaynaklarını tek tek web sayfalarında takip etmek yerine bunları ortak bir harita ve operasyon panelinde birleştirmek için geliştirilmiştir. Kullanıcı; kamu ADS-B hava gözlemlerini, AIS deniz verilerini, doğal afetleri, hava/radar katmanlarını, uydu ve uzay verilerini, haber ve diplomasi akışlarını, trafik/sınır verilerini, piyasa göstergelerini ve kamu kamera kataloglarını aynı masaüstü uygulamasında inceleyebilir.

Uygulama her sağlayıcının durumunu ayrı değerlendirir. Bir kaynağın API anahtarı eksik, kotası dolu veya geçici olarak çevrimdışı olması tüm sistemin bozuk olduğu anlamına gelmez. Desteklenen katmanlarda cache, fallback ve kaynak sağlık göstergeleri kullanılır. API anahtarları release paketine gömülmez; kullanıcı tarafından yerel olarak yapılandırılır.

Gökdoğan yalnız kamuya açık veya kullanım yetkisi bulunan kaynaklar için tasarlanmıştır. Özel/kapalı kamera sistemlerine erişim kontrolü aşma, kişi hedefli gizli takip, gerçek zamanlı kolluk kaçınma veya hassas askerî hedefleme kamu sürümünün kapsamı dışındadır.

## Önerilen GitHub Topics

`osint` `situational-awareness` `geospatial` `maplibre` `fastapi` `tauri` `rust` `python` `typescript` `windows` `turkish` `adsb` `ais` `disaster-monitoring` `open-data`

## Release başlığı

**Gökdoğan Intelligence v1.0.0 — İlk Resmî Sürüm**

## Release kısa özeti

İlk resmî sürüm; Windows masaüstü installer'ı, Türkçe harita tabanlı arayüz, hava/deniz/afet/hava durumu/uydu/haber/piyasa katmanları, yerel API anahtar yönetimi, kaynak sağlığı, NSIS build zinciri ve Offline USB dağıtım desteğini içerir.

## Ekran görüntüsü başlıkları

1. Bölgesel operasyon haritası
2. Küresel operasyon görünümü
3. Kamu verisinden askerî hava aracı ayrıntısı
4. Denizcilik, uzay ve altyapı katmanları
5. API ilk kurulum ve yerel anahtar yönetimi
6. Entegrasyon hazırlık özeti
7. Veri katmanları paneli
8. Yardımcı araçlar ve analiz panelleri
9. Canlı veri durum çubuğu
10. Kamu kamera/CCTV kaynak kayıtları
