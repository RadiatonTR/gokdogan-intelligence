# Sorun Giderme

## Uygulama açılmıyor

1. Gökdoğan'ın başka bir örneğinin tray'de açık olmadığını kontrol edin.
2. `start-here.log` ve `windows-desktop-build.log` dosyalarını inceleyin.
3. `GOKDOGAN-DIAGNOSTIC.zip` oluşturulduysa gizli değer içermediğini kontrol ederek geliştiriciye gönderin.
4. WebView2 Runtime'ın kurulu olduğunu doğrulayın.

## `managed_backend_*` hataları

Managed backend hataları çoğunlukla:

- eski süreç dosyaları kilitli tuttuğunda,
- runtime dosyası eksik/bozuk olduğunda,
- antivirüs/izin sistemi çalışma klasörünü engellediğinde

oluşabilir. Yeni sürümü eski kaynak klasörünün üzerine çıkarmayın.

## API anahtarı kaydedilmiyor

1. **Ayarlar → API Anahtarları** bölümünden tekrar kaydedin.
2. **API SİSTEMİNİ TEST ET** çalıştırın.
3. İstihbarat Merkezi'nde sağlayıcı durumuna bakın.
4. Anahtarın sağlayıcı tarafında aktif olduğunu doğrulayın.
5. Kota veya plan kısıtını kontrol edin.

## `ANAHTAR EKSİK`

Her eksik anahtar kritik değildir. Bazı sağlayıcılar yalnız zenginleştirme içindir. İlgili katmanın anahtarsız fallback/kamu kaynağı varsa sistem çalışmaya devam edebilir.

## AIS / gemi verisi geçici uyarısı

AISStream ilk bağlantıda gecikebilir veya sağlayıcı geçici olarak çevrimdışı olabilir. Kaynak sağlığını kontrol edin. Cache veya diğer deniz kaynakları varsa uygulama onları kullanabilir.

## Harici bağlantı açılmıyor

- Windows varsayılan tarayıcısının düzgün yapılandırıldığını kontrol edin.
- Uygulamayı yeniden başlatın.
- İlgili kaynak URL'sinin gerçekten `http/https` olduğunu doğrulayın.

## Kamera kaynağı açılmıyor

Kamu kamera URL'leri sağlayıcı tarafından kaldırılmış, taşınmış, oturum gerektiriyor veya bölgesel olarak engellenmiş olabilir. Gökdoğan erişim kısıtını aşmaz.

## Harita çok yavaş

- kullanılmayan katmanları kapatın,
- çalışma profilini `DENGELİ` yapın,
- aşırı yoğun küresel görünüm yerine bölgesel zoom kullanın,
- arka plandaki ağır uygulamaları kapatın.

## Kaynak 404/500/SSL hatası

Üçüncü taraf endpoint değişmiş veya geçici olarak bozuk olabilir. Kaynak sağlığı bunu uygulama çökmesi olarak değerlendirmemelidir. Sağlayıcının resmî adresini kontrol edin.
