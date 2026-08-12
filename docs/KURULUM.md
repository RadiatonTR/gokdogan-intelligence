# Kurulum Kılavuzu

Bu belge Gökdoğan Intelligence v1.0.0 için Windows kurulum ve kaynaktan derleme notlarını içerir.

## 1. Desteklenen ortam

- Windows 10/11 x64
- Microsoft Edge WebView2 Runtime
- PowerShell 5.1 veya daha yeni
- kaynaktan build için internet bağlantısı
- kaynaktan build için birkaç GB boş disk alanı önerilir

Builder kendi release sözleşmesinde Node 24.x, Rust 1.97.1 ve Python 3.12 çalışma zincirini doğrular/kurar.

## 2. Son kullanıcı kurulumu

GitHub Releases üzerinden şu dosyalar yayımlanabilir:

- `Gokdogan-Intelligence-v1.0.0-Setup.exe`
- `Gokdogan-Intelligence-v1.0.0-Windows-Desktop-Bundle.zip`
- `Gokdogan-Intelligence-v1.0.0-OFFLINE-USB.zip`
- `SHA256SUMS.txt`

### SHA-256 doğrulama

PowerShell örneği:

```powershell
Get-FileHash .\Gokdogan-Intelligence-v1.0.0-Setup.exe -Algorithm SHA256
```

Çıktıyı GitHub Release içindeki `SHA256SUMS.txt` değeriyle karşılaştırın.

> Code-signing sertifikası kullanılmadan oluşturulan ilk sürüm Windows tarafından imzasız (`NotSigned`) görünebilir. Hash eşleşmeden installer çalıştırmayın.

## 3. Kaynaktan tek tık derleme

1. Source ZIP'i yeni ve boş bir klasöre çıkarın.
2. Klasör yolunun mümkün olduğunca kısa olmasını tercih edin.
3. `START-HERE.bat` dosyasını çalıştırın.
4. Gerekirse Windows güvenlik/UAC pencerelerini okuyup onaylayın.
5. Build tamamlanana kadar terminali kapatmayın.

### Builder'ın yaptığı işlemler

- Windows ve mimari preflight kontrolü
- WebView2 kontrolü
- Node/npm locked dependency kurulumu
- npm audit/release güvenlik kapıları
- Python 3.12 managed runtime hazırlanması
- `uv.lock` üzerinden hash-pinned Python bağımlılıkları
- Cargo/Tauri kilit kontrolü
- backend regression testleri
- frontend ESLint, Vitest ve TypeScript kontrolleri
- Rust/Tauri unit testleri
- frontend static export
- managed backend staging
- NSIS installer oluşturma
- SBOM, SHA-256 ve release manifestleri
- Offline USB paketi
- kurulu runtime öz testi

## 4. Build çıktıları

Başarılı build sonrası `dist` klasöründe installer, bundle ve USB dağıtım paketleri oluşur.

## 5. İlk açılış

1. Gökdoğan'ı başlatın.
2. Haritanın açıldığını doğrulayın.
3. **Ayarlar → API Anahtarları** bölümünü açın.
4. İhtiyacınız olan sağlayıcı anahtarlarını girin.
5. **API SİSTEMİNİ TEST ET** ile doğrulayın.
6. **Kaynak Sağlığı / İstihbarat Merkezi** ekranından kaynak durumlarını kontrol edin.
7. Çalışma profilini `DENGELİ` ile başlayacak şekilde bırakın.

## 6. Güncelleme

- Yeni sürümü eski kaynak klasörünün üzerine çıkarmayın.
- Yeni Source ZIP'i ayrı klasöre çıkarın.
- Kullanıcı çalışma verileri `%LOCALAPPDATA%` altındaki uygulama veri alanında tutulur.
- API anahtarlarını GitHub/source klasörüne kopyalamayın.

## 7. Build hata dosyaları

- `start-here.log`
- `windows-desktop-build.log`
- `GOKDOGAN-DIAGNOSTIC.zip`

Sorun bildirirken API anahtarı, `.env`, özel URL veya kişisel veriyi issue'ya eklemeyin.
