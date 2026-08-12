# Gökdoğan Intelligence v1.0.0 yayın tetikleyicisi

Bu dosya ilk resmî `v1.0.0` Windows release workflow'unu tetiklemek için kullanılır.

## Deneme 3

Önceki iki GitHub-hosted Windows denemesinde yayın zincirinin kendisine ait iki CI ortam sorunu tespit edilip giderildi:

1. Windows konsol encoding'i UTF-8'e zorlandı.
2. Release testleri için `pytest` dahil backend geliştirme/test bağımlılıkları repo'nun kilitli `uv` ortamından kurulacak şekilde düzenlendi.

Bu denemede:

- `PYTHONUTF8=1`
- `PYTHONIOENCODING=utf-8`
- `astral-sh/setup-uv@v7`
- `uv sync --frozen --group dev`
- `uv run pytest ...`
- Node 24 tabanlı güncel GitHub Actions v7

kullanılır.

Yayın kapıları başarılı olduğunda GitHub Actions:

1. Windows release testlerini çalıştırır.
2. NSIS installer ve dağıtım paketlerini üretir.
3. SHA-256 bütünlük özetini oluşturur.
4. Build provenance attestation üretir.
5. `v1.0.0` Git tag'ini oluşturur.
6. GitHub Release'i açar.
7. Installer, Windows bundle, Offline USB ZIP, hash ve attestation dosyalarını Release'e yükler.
