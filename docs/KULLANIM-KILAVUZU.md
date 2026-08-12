# Kullanım Kılavuzu

## Ana ekran

Gökdoğan'ın ana ekranı dört temel bölgeden oluşur:

1. **Sol Veri Katmanları:** veri ailelerini ve sayaçları yönetir.
2. **Merkez Harita:** coğrafi olayları, rotaları ve varlıkları gösterir.
3. **Sağ Operasyon Panelleri:** haber, diplomasi, hava/kara trafiği, piyasa ve filtre modüllerini açar.
4. **Alt Durum Çubuğu:** konum, harita stili ve bazı canlı kaynak sayaçlarını gösterir.

## Harita kullanımı

- Fare tekerleğiyle yakınlaştırın/uzaklaştırın.
- İşaret veya rota seçerek ayrıntı panelini açın.
- Katmanları sol panelden açıp kapatın.
- Uydu/standart altlıklar arasında geçiş yapın.
- Harita kalabalıksa kullanılmayan katmanları kapatın.

## Arama

Arama alanı desteklenen yapılandırmaya göre:

- yer adı,
- koordinat,
- çağrı işareti,
- bazı varlık kimlikleri

ile haritada konuma gitmek için kullanılabilir.

## Hava araçları

Bir hava aracı seçildiğinde mevcut veri setine göre şu alanlar gösterilebilir:

- çağrı işareti
- ICAO/tescil
- model
- operatör
- irtifa
- yer hızı
- yön
- ilk/son gözlem
- gözlenen iz/rota
- harici referans bağlantısı

Bazı alanlar ayrı sağlayıcı/API anahtarı gerektirir. `BİLİNMİYOR` alanı sistem arızası değil, veri kaynağında bilgi bulunmadığı anlamına gelebilir.

## Deniz araçları

AIS verisi mevcutsa:

- MMSI/IMO
- gemi adı/tipi
- konum
- hız/yön
- gözlenen iz
- son güncelleme

alanları kullanılabilir.

AISStream geçici olarak veri vermiyorsa uygulama bunu kaynak sağlığı üzerinden bildirir ve mevcutsa cache/fallback kaynaklarını kullanır.

## Kamu kamera kaynakları

Kamu kamera alanı:

- resmi trafik/kent kamera kataloglarını,
- operatörün yetkili biçimde eklediği katalog URL'lerini,
- API anahtarlı kamu sağlayıcılarını

yönetmek içindir.

Kamera bağlantısı seçildiğinde uygulama kaynağı sistem tarayıcısında açabilir. Kapalı/özel kamera ağlarına yetkisiz erişim desteklenmez.

## Haber ve diplomasi

Haber/diplomasi kartlarında:

- başlık
- kaynak
- zaman
- varsa konum/olay bağlamı
- harici kaynak bağlantısı

görülebilir. Başlık dili, kaynak yayınından gelebilir; Gökdoğan'ın arayüz kontrolleri Türkçedir.

## Afetler

Afet katmanlarını ayrı ayrı açarak deprem, yangın, yanardağ ve diğer olayları inceleyin. Kritik bir durum için her zaman ilgili resmî kurumun yayınını da doğrulayın.

## Meteoroloji

Hava tahmini, radar ve hava kalitesi katmanları farklı sağlayıcılardan gelebilir. Harita zamanı ve sağlayıcı güncelleme zamanı aynı olmayabilir.

## Piyasalar

Piyasa çubuğu ve Piyasa Merkezi; yapılandırılmış sağlayıcılardan fiyat göstergeleri gösterir. Bunlar yatırım tavsiyesi değildir ve gecikmeli olabilir.

## API yönetimi

**Ayarlar → API Anahtarları**:

1. sağlayıcı anahtarını girin,
2. kaydedin,
3. `API SİSTEMİNİ TEST ET` çalıştırın,
4. İstihbarat Merkezi'ndeki durumun `HAZIR/ETKİN` olduğunu kontrol edin.

API anahtarının kendisi arayüzde tekrar açık metin olarak gösterilmemelidir.

## Kaynak sağlığı

Bir katman veri göstermiyorsa önce kaynak durumuna bakın:

- anahtar eksik mi?
- servis kapalı mı?
- kota mı doldu?
- veri gecikmeli mi?
- cache mi gösteriliyor?

Bu ayrım, uygulamanın kendisinin bozuk olup olmadığını anlamanın en hızlı yoludur.

## Çalışma profilleri

- **DENGELİ:** önerilen varsayılan; kararlılık ve kaynak kotaları için uygundur.
- **MAKSİMUM:** güçlü bilgisayarlarda daha yüksek eşzamanlılık/harita bütçesi kullanır.

MAKSİMUM profil, dış API limitlerini aşmaz.
