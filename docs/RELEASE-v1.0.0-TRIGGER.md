# Gökdoğan Intelligence v1.0.0 yayın tetikleyicisi

Bu dosya ilk resmî `v1.0.0` Windows release workflow'unu tetiklemek için kullanılır.

## Deneme 4

Önceki yayın denemelerinde CI/release ortamına ait sorunlar giderildi:

1. Windows konsolu UTF-8'e geçirildi.
2. Backend test bağımlılıkları kilitli `uv` ortamından kuruluyor.
3. v1.0.0 GitHub görsel sözleşmesi gerçek yayın dosya adlarıyla hizalandı (`02-kuresel-operasyon-gorunumu.png`).

Yayın kapıları başarılı olduğunda GitHub Actions:

1. Windows release testlerini çalıştırır.
2. NSIS installer ve dağıtım paketlerini üretir.
3. SHA-256 bütünlük özetini oluşturur.
4. Build provenance attestation üretir.
5. `v1.0.0` Git tag'ini oluşturur.
6. GitHub Release'i açar.
7. Installer, Windows bundle, Offline USB ZIP, hash ve attestation dosyalarını Release'e yükler.
