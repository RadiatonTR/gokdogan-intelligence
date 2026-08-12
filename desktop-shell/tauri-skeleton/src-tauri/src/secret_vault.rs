use std::collections::BTreeMap;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager, State};

use crate::local_custody::{read_or_migrate_json_file, write_protected_json_file};

const SCOPE: &str = "shadowbroker.desktop.secret-vault.v1";
const FILE_NAME: &str = "secret-vault.json";

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
struct SecretVault {
    version: u8,
    secrets: BTreeMap<String, String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct SecretVaultStatus {
    pub protected_by_local_custody: bool,
    pub keys: Vec<String>,
    pub count: usize,
}

fn vault_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_local_data_dir()
        .map_err(|e| format!("secret_vault_data_dir_failed:{e}"))?;
    Ok(dir.join(FILE_NAME))
}

fn validate_key(key: &str) -> Result<String, String> {
    let trimmed = key.trim();
    if trimmed.is_empty() || trimmed.len() > 128 {
        return Err("secret_vault_key_invalid".to_string());
    }
    if !trimmed
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || matches!(c, '_' | '-' | '.'))
    {
        return Err("secret_vault_key_invalid".to_string());
    }
    Ok(trimmed.to_ascii_uppercase())
}

fn load(app: &AppHandle) -> Result<SecretVault, String> {
    let path = vault_path(app)?;
    match read_or_migrate_json_file::<SecretVault>(&path, SCOPE)? {
        Some(outcome) => Ok(outcome.value),
        None => Ok(SecretVault {
            version: 1,
            secrets: BTreeMap::new(),
        }),
    }
}

fn save(app: &AppHandle, vault: &SecretVault) -> Result<(), String> {
    let path = vault_path(app)?;
    write_protected_json_file(&path, SCOPE, vault)
}

#[tauri::command]
pub fn desktop_secret_vault_status(app: AppHandle) -> Result<SecretVaultStatus, String> {
    let vault = load(&app)?;
    let custody = crate::local_custody::local_custody_status();
    let keys: Vec<String> = vault.secrets.keys().cloned().collect();
    Ok(SecretVaultStatus {
        protected_by_local_custody: custody.protected_at_rest,
        count: keys.len(),
        keys,
    })
}

#[tauri::command]
pub async fn desktop_secret_set(
    app: AppHandle,
    state: State<'_, crate::DesktopAppState>,
    key: String,
    value: String,
) -> Result<SecretVaultStatus, String> {
    let key = validate_key(&key)?;
    if value.is_empty() || value.len() > 16_384 {
        return Err("secret_vault_value_invalid".to_string());
    }
    let mut vault = load(&app)?;
    vault.version = 1;
    vault.secrets.insert(key.clone(), value.clone());
    save(&app, &vault)?;

    // Best-effort hot apply to the local backend. The native vault remains
    // authoritative, so a temporary backend outage never loses the secret.
    let mut updates = serde_json::Map::new();
    updates.insert(key.clone(), serde_json::Value::String(value.clone()));
    let payload = serde_json::Value::Object(updates);
    let _ = crate::http_client::call_backend_json(
        &state.backend_base_url,
        state.admin_key.as_deref(),
        "/api/settings/api-keys/runtime",
        reqwest::Method::PUT,
        Some(payload),
    )
    .await;

    desktop_secret_vault_status(app)
}

#[tauri::command]
pub async fn desktop_secret_set_many(
    app: AppHandle,
    state: State<'_, crate::DesktopAppState>,
    values: BTreeMap<String, String>,
) -> Result<SecretVaultStatus, String> {
    if values.is_empty() {
        return Err("secret_vault_values_empty".to_string());
    }
    let mut clean = BTreeMap::new();
    for (raw_key, raw_value) in values {
        let key = validate_key(&raw_key)?;
        let value = raw_value.trim().to_string();
        if value.is_empty() || value.len() > 16_384 {
            return Err(format!("secret_vault_value_invalid:{key}"));
        }
        clean.insert(key, value);
    }

    // One read + one protected write prevents partial onboarding state and also
    // avoids repeated Windows replace operations for multi-key setup.
    let mut vault = load(&app)?;
    vault.version = 1;
    for (key, value) in &clean {
        vault.secrets.insert(key.clone(), value.clone());
    }
    save(&app, &vault)?;

    let payload = serde_json::Value::Object(
        clean
            .into_iter()
            .map(|(key, value)| (key, serde_json::Value::String(value)))
            .collect(),
    );
    let _ = crate::http_client::call_backend_json(
        &state.backend_base_url,
        state.admin_key.as_deref(),
        "/api/settings/api-keys/runtime",
        reqwest::Method::PUT,
        Some(payload),
    )
    .await;

    desktop_secret_vault_status(app)
}

#[tauri::command]
pub fn desktop_secret_delete(app: AppHandle, key: String) -> Result<SecretVaultStatus, String> {
    let key = validate_key(&key)?;
    let mut vault = load(&app)?;
    vault.secrets.remove(&key);
    save(&app, &vault)?;
    desktop_secret_vault_status(app)
}

pub fn load_all_for_backend(app: &AppHandle) -> Result<BTreeMap<String, String>, String> {
    Ok(load(app)?.secrets)
}
