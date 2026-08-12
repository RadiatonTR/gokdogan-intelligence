# Windows Authenticode Kod İmzalama

Gökdoğan Intelligence Windows yayın workflow'u, kod imzalama sertifikası sağlanırsa installer'ı imzalamaya hazırdır. Sertifika veya parolası kaynak koduna, issue/PR metnine ya da sohbet kayıtlarına eklenmemelidir.

## Gerekli GitHub Actions Secrets

Repository → **Settings → Secrets and variables → Actions** altında aşağıdaki repository secret'ları tanımlanır:

- `GOKDOGAN_WINDOWS_CERT_PFX_B64`
- `GOKDOGAN_WINDOWS_CERT_PASSWORD`

`GOKDOGAN_WINDOWS_CERT_PFX_B64`, geçerli kod-imzalama PFX/P12 sertifikasının Base64 temsilidir. `GOKDOGAN_WINDOWS_CERT_PASSWORD`, aynı PFX dosyasının parolasıdır.

## Yerelde Base64 üretme

Sertifika dosyasını depoya kopyalamadan PowerShell'de:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes('C:\GUZEL\VE\OZEL\YOL\gokdogan-code-signing.pfx')) | Set-Clipboard
```

Base64 değerini doğrudan GitHub Actions secret alanına yapıştırın. PFX dosyasını Git repository'sine eklemeyin.

## Workflow davranışı

`.github/workflows/desktop-release.yml` iki secret da mevcutsa:

1. PFX'i geçici GitHub runner dizinine çözer.
2. Sertifikayı `Cert:\CurrentUser\My` deposuna geçici olarak içe aktarır.
3. Thumbprint'i builder'a `SHADOWBROKER_WINDOWS_CERT_THUMBPRINT` ile geçirir.
4. `SHADOWBROKER_REQUIRE_WINDOWS_SIGNATURE=1` ayarlayarak imzayı zorunlu hale getirir.
5. Yayın işinin sonunda sertifikayı runner sertifika deposundan temizler.

Secret'lar yoksa sertifika içe aktarma adımı atlanır ve mevcut workflow imzasız build üretmeye devam edebilir. Bu nedenle yayın öncesinde Authenticode durumunu ayrıca doğrulamak gerekir.

## Doğrulama

Yayın installer'ı indirildikten sonra PowerShell:

```powershell
Get-AuthenticodeSignature .\Gokdogan-Intelligence-v1.0.0-Setup.exe | Format-List Status,StatusMessage,SignerCertificate
```

Profesyonel yayın hedefinde beklenen `Status` değeri `Valid` olmalıdır. Ayrıca Release'teki SHA-256 manifesti ile installer hash'i doğrulanmalıdır.

## Güvenlik kuralları

- PFX/P12 dosyasını repoya commit etmeyin.
- Sertifika parolasını `.env`, workflow YAML veya README içine yazmayın.
- Secret değerlerini issue, PR veya loglarda paylaşmayın.
- Sertifika yenilendiğinde eski secret'ları güncelleyin.
- Bir sertifikanın sızdığından şüpheleniliyorsa sertifika sağlayıcısından iptal/revocation prosedürü uygulanmalıdır.
