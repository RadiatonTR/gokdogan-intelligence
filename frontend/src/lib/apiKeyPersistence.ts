export type ApiKeySaveResult = {
  ok: boolean;
  mode: 'native-batch' | 'native-individual' | 'backend-persistent' | 'none';
  hotApplied: boolean;
  verifiedKeys?: string[];
  warning?: string;
};

async function verifyBackendConfigured(values: Record<string, string>): Promise<string[]> {
  const res = await fetch('/api/settings/api-keys', { cache: 'no-store' });
  const data: unknown = await res.json().catch(() => []);
  if (!res.ok || !Array.isArray(data)) {
    throw new Error('API anahtarı kaydedildi ancak backend doğrulaması alınamadı.');
  }
  const rows = data.filter(
    (row): row is { env_key: unknown; is_set?: unknown } =>
      typeof row === 'object' && row !== null && 'env_key' in row,
  );
  const byEnv = new Map<string, boolean>(
    rows.map((row) => [String(row.env_key).toUpperCase(), Boolean(row.is_set)]),
  );
  const missing = Object.keys(values).filter((key) => !byEnv.get(key.toUpperCase()));
  if (missing.length) {
    throw new Error(`Backend anahtarı etkin görmüyor: ${missing.join(', ')}`);
  }
  return Object.keys(values).sort();
}

async function backendSave(values: Record<string, string>, runtimeOnly: boolean) {
  const res = await fetch(runtimeOnly ? '/api/settings/api-keys/runtime' : '/api/settings/api-keys', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(values),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data?.ok === false) {
    throw new Error(data?.detail || `API anahtarı ${runtimeOnly ? 'etkinleştirilemedi' : 'kaydedilemedi'}.`);
  }
  return data;
}

/**
 * Save provider credentials with layered desktop resilience.
 *
 * 1. Native batch vault (DPAPI/local custody).
 * 2. Native individual writes if an older runtime exposes only setSecret.
 * 3. Local-backend persistent store as a final compatibility path.
 *
 * Native-vault saves are hot-applied to the running backend via a runtime-only
 * endpoint so they work immediately without duplicating secrets into plaintext
 * backend files.
 */
export async function saveApiKeysResilient(values: Record<string, string>): Promise<ApiKeySaveResult> {
  const clean = Object.fromEntries(
    Object.entries(values)
      .map(([key, value]) => [String(key).trim().toUpperCase(), String(value).trim()] as const)
      .filter(([key, value]) => Boolean(key && value)),
  );
  if (!Object.keys(clean).length) throw new Error('Önce en az bir API anahtarı girin.');

  const native = typeof window !== 'undefined' ? window.__SHADOWBROKER_DESKTOP__ : undefined;
  let nativeError = '';
  if (native?.setSecrets) {
    try {
      await native.setSecrets(clean);
      try {
        await backendSave(clean, true);
        const verifiedKeys = await verifyBackendConfigured(clean);
        return { ok: true, mode: 'native-batch', hotApplied: true, verifiedKeys };
      } catch (error) {
        const hotApplyMessage = error instanceof Error ? error.message : 'Çalışma zamanı etkinleştirmesi başarısız oldu.';
        try {
          await backendSave(clean, false);
          const verifiedKeys = await verifyBackendConfigured(clean);
          return {
            ok: true,
            mode: 'backend-persistent',
            hotApplied: true,
            verifiedKeys,
            warning: `Windows güvenli kasasına kaydedildi; çalışma zamanı yolu geçici olarak başarısız olduğu için yerel backend deposu da kullanıldı (${hotApplyMessage}).`,
          };
        } catch (fallbackError) {
          const fallbackMessage = fallbackError instanceof Error ? fallbackError.message : String(fallbackError || '');
          throw new Error(`Anahtar Windows kasasına kaydedildi ancak backend etkinleştirmesi doğrulanamadı: ${hotApplyMessage}${fallbackMessage ? ` · ${fallbackMessage}` : ''}`);
        }
      }
    } catch (error) {
      nativeError = error instanceof Error ? error.message : String(error || 'native_batch_failed');
    }
  }

  if (native?.setSecret) {
    try {
      for (const [key, value] of Object.entries(clean)) {
        await native.setSecret(key, value);
      }
      try {
        await backendSave(clean, true);
        const verifiedKeys = await verifyBackendConfigured(clean);
        return { ok: true, mode: 'native-individual', hotApplied: true, verifiedKeys };
      } catch (error) {
        const hotApplyMessage = error instanceof Error ? error.message : 'Çalışma zamanı etkinleştirmesi başarısız oldu.';
        try {
          await backendSave(clean, false);
          const verifiedKeys = await verifyBackendConfigured(clean);
          return {
            ok: true,
            mode: 'backend-persistent',
            hotApplied: true,
            verifiedKeys,
            warning: `Windows güvenli kasasına tek tek kaydedildi; çalışma zamanı yolu geçici olarak başarısız olduğu için yerel backend deposu da kullanıldı (${hotApplyMessage}).`,
          };
        } catch (fallbackError) {
          const fallbackMessage = fallbackError instanceof Error ? fallbackError.message : String(fallbackError || '');
          throw new Error(`Anahtar Windows kasasına kaydedildi ancak backend etkinleştirmesi doğrulanamadı: ${hotApplyMessage}${fallbackMessage ? ` · ${fallbackMessage}` : ''}`);
        }
      }
    } catch (error) {
      nativeError = error instanceof Error ? error.message : String(error || nativeError || 'native_individual_failed');
    }
  }

  // Compatibility/failsafe for browser mode or a native ACL mismatch.  This is
  // loopback-only and accepted by the backend's local-operator guard.
  try {
    await backendSave(clean, false);
    const verifiedKeys = await verifyBackendConfigured(clean);
    return {
      ok: true,
      mode: 'backend-persistent',
      hotApplied: true,
      verifiedKeys,
      warning: nativeError
        ? `Windows güvenli kasası kullanılamadı (${nativeError}); anahtarlar yerel Gökdoğan veri motorunda kaydedildi.`
        : undefined,
    };
  } catch (backendError) {
    const backendMessage = backendError instanceof Error ? backendError.message : String(backendError || '');
    throw new Error(nativeError ? `${nativeError} · ${backendMessage}` : backendMessage || 'API anahtarları kaydedilemedi.');
  }
}
