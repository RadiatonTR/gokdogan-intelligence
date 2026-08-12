# Troubleshooting

## The application does not start

1. Make sure another Gökdoğan instance is not already running in the system tray.
2. Review `start-here.log` and `windows-desktop-build.log`.
3. If `GOKDOGAN-DIAGNOSTIC.zip` was generated, verify that it contains no secret values before sharing it with the developer.
4. Verify that Microsoft Edge WebView2 Runtime is installed.

## `managed_backend_*` errors

Managed-backend errors can occur when:

- an older process is still locking files,
- a runtime file is missing or corrupted,
- antivirus/security permissions block the runtime directory.

Do not extract a new version over an old source directory.

## API key is not being saved

1. Save the key again under **Ayarlar → API Anahtarları**.
2. Run **API SİSTEMİNİ TEST ET**.
3. Check the provider status in the Intelligence Center.
4. Verify that the key is active with the provider.
5. Check quota and plan restrictions.

## `ANAHTAR EKSİK` (Key missing)

Not every missing key is critical. Some providers are optional enrichment sources. If a layer has a keyless public/fallback source, the application may continue operating without that key.

## Temporary AIS / vessel warning

AISStream may take time to connect or can be temporarily unavailable. Check source health. If cache or other maritime sources are configured, Gökdoğan may use them as fallbacks.

## External link does not open

- Verify that the Windows default browser is correctly configured.
- Restart the application.
- Confirm that the source URL is actually an `http/https` URL.

## Camera source does not open

A public camera URL may have been removed, moved, changed to require a session, or become regionally unavailable. Gökdoğan does not bypass access restrictions.

## The map is very slow

- Disable unused layers.
- Use the `DENGELİ` (Balanced) operating profile.
- Prefer a regional zoom over an extremely dense global view.
- Close other resource-heavy applications.

## Source returns 404/500/SSL errors

A third-party endpoint may have changed or may be temporarily unavailable. Source-health reporting should distinguish this from an application crash. Check the provider's official endpoint/documentation.
