# Gökdoğan Intelligence v1.0.0 yayın tetikleyicisi

Bu dosya ilk resmî `v1.0.0` Windows release workflow'unu tetiklemek için kullanılır.

## Deneme 7

Deneme 6'da sürüm sözleşmesi, kilitli bağımlılık kontrolleri, backend release testleri, npm audit kapıları, taşınabilir Python hazırlığı ve Rust/Tauri testleri geçti. Başarısızlık yalnız `npm --prefix desktop-shell run build:desktop:clean` alt derlemesinde kaldı; alt PowerShell sürecinin ayrıntılı stdout/stderr çıktısı üst transcript'e taşınmadığı için gerçek Tauri/NSIS hata satırı kayboluyordu.

Bu denemede `desktop-shell/scripts/run-desktop-build.cjs`, alt derleme çıktısını hem canlı terminale hem `build-reports/desktop-build-inner.log` dosyasına kaydediyor. Böylece paketleme hatası varsa doğrudan tanılanabilir; başarılı olursa normal v1.0.0 yayın zinciri devam eder.

Yayın kapıları başarılı olduğunda GitHub Actions:

1. Windows release testlerini çalıştırır.
2. NSIS installer ve dağıtım paketlerini üretir.
3. SHA-256 bütünlük özetini oluşturur.
4. Build provenance attestation üretir.
5. `v1.0.0` Git tag'ini oluşturur.
6. GitHub Release'i açar.
7. Installer, Windows bundle, Offline USB ZIP, hash ve attestation dosyalarını Release'e yükler.
