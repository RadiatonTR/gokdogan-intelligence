# Gökdoğan Intelligence v1.0.0 yayın tetikleyicisi

Bu dosya ilk resmî `v1.0.0` Windows release workflow'unu bir kez tetiklemek için oluşturulmuştur.

Yayın kapıları başarılı olduğunda GitHub Actions:

1. Windows release testlerini çalıştırır.
2. NSIS installer ve dağıtım paketlerini üretir.
3. SHA-256 bütünlük özetini oluşturur.
4. Build provenance attestation üretir.
5. `v1.0.0` Git tag'ini oluşturur.
6. GitHub Release'i açar.
7. Installer, Windows bundle, Offline USB ZIP, hash ve attestation dosyalarını Release'e yükler.

Bu dosyanın sonraki sürümlerde değiştirilmesine gerek yoktur.
