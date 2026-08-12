# Gökdoğan Intelligence v1.0.0 yayın tetikleyicisi

Bu dosya ilk resmî `v1.0.0` Windows release workflow'unu tetiklemek için kullanılır.

## Deneme 2

İlk GitHub-hosted Windows denemesi, release-cleanliness kontrolü başarılı olmasına rağmen Windows konsolunun `cp1252` encoding'i Türkçe `ğ` karakterini yazdıramadığı için `UnicodeEncodeError` ile durdu.

İkinci denemede:

- `PYTHONUTF8=1`
- `PYTHONIOENCODING=utf-8`
- `actions/checkout@v7`
- `actions/setup-node@v7`
- `actions/setup-python@v7`
- `actions/upload-artifact@v7`

kullanılır.

Yayın kapıları başarılı olduğunda GitHub Actions:

1. Windows release testlerini çalıştırır.
2. NSIS installer ve dağıtım paketlerini üretir.
3. SHA-256 bütünlük özetini oluşturur.
4. Build provenance attestation üretir.
5. `v1.0.0` Git tag'ini oluşturur.
6. GitHub Release'i açar.
7. Installer, Windows bundle, Offline USB ZIP, hash ve attestation dosyalarını Release'e yükler.
