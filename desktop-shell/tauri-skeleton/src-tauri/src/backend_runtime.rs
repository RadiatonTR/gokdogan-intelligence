use std::collections::BTreeMap;
use std::fmt::Write as _;
use std::fs;
use std::io::Read;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

use sha2::{Digest, Sha256};

const RESOURCE_DIR_NAME: &str = "backend-runtime";
const INSTALL_DIR_NAME: &str = "managed-backend";
const PREVIOUS_INSTALL_DIR_NAME: &str = "managed-backend-previous";
const BUNDLE_VERSION_FILE: &str = ".bundle-version";
const RUNTIME_INTEGRITY_MANIFEST_FILE: &str = ".runtime-integrity.json";
const PERSISTENT_NAMES: &[&str] = &[".env", "data"];
const RELEASE_ATTESTATION_RELATIVE_PATH: &[&str] = &["data", "release_attestation.json"];
const GENERATED_SECRET_BYTES: usize = 32;

struct ManagedBackendSecrets {
    admin_key: String,
}


#[derive(serde::Deserialize)]
struct RuntimeIntegrityManifest {
    manifest_version: u32,
    algorithm: String,
    bundle_version: String,
    file_count: usize,
    files: Vec<RuntimeIntegrityEntry>,
}

#[derive(serde::Deserialize)]
struct RuntimeIntegrityEntry {
    path: String,
    size: u64,
    sha256: String,
}

fn safe_manifest_relative_path(value: &str) -> Result<PathBuf, String> {
    let path = Path::new(value);
    if path.is_absolute() || value.trim().is_empty() {
        return Err("managed_backend_integrity_invalid_path".to_string());
    }
    let mut result = PathBuf::new();
    for component in path.components() {
        match component {
            std::path::Component::Normal(part) => result.push(part),
            _ => return Err("managed_backend_integrity_invalid_path".to_string()),
        }
    }
    if result.as_os_str().is_empty() {
        return Err("managed_backend_integrity_invalid_path".to_string());
    }
    Ok(result)
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let mut file = fs::File::open(path)
        .map_err(|e| format!("managed_backend_integrity_open_failed:{e}"))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 1024 * 128];
    loop {
        let read = file
            .read(&mut buffer)
            .map_err(|e| format!("managed_backend_integrity_read_failed:{e}"))?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

fn verify_runtime_integrity(root: &Path) -> Result<(), String> {
    let manifest_path = root.join(RUNTIME_INTEGRITY_MANIFEST_FILE);
    let rendered = fs::read_to_string(&manifest_path)
        .map_err(|e| format!("managed_backend_integrity_manifest_missing:{e}"))?;
    let manifest: RuntimeIntegrityManifest = serde_json::from_str(&rendered)
        .map_err(|e| format!("managed_backend_integrity_manifest_invalid:{e}"))?;
    if manifest.manifest_version != 1 || !manifest.algorithm.eq_ignore_ascii_case("sha256") {
        return Err("managed_backend_integrity_manifest_unsupported".to_string());
    }
    if manifest.file_count != manifest.files.len() {
        return Err("managed_backend_integrity_file_count_mismatch".to_string());
    }
    let bundle_version = read_trimmed_file(&root.join(BUNDLE_VERSION_FILE))?;
    if manifest.bundle_version.trim() != bundle_version.trim() {
        return Err("managed_backend_integrity_bundle_version_mismatch".to_string());
    }
    for entry in &manifest.files {
        let relative = safe_manifest_relative_path(&entry.path)?;
        if relative == Path::new(RUNTIME_INTEGRITY_MANIFEST_FILE) {
            return Err("managed_backend_integrity_recursive_manifest".to_string());
        }
        let full_path = root.join(relative);
        let metadata = fs::metadata(&full_path)
            .map_err(|_| format!("managed_backend_integrity_missing_file:{}", entry.path))?;
        if !metadata.is_file() || metadata.len() != entry.size {
            return Err(format!("managed_backend_integrity_size_mismatch:{}", entry.path));
        }
        let actual = sha256_file(&full_path)?;
        if !actual.eq_ignore_ascii_case(entry.sha256.trim()) {
            return Err(format!("managed_backend_integrity_hash_mismatch:{}", entry.path));
        }
    }
    Ok(())
}

struct ManagedSecretSpec {
    key: &'static str,
    min_len: usize,
}

struct ManagedBoolDefaultSpec {
    key: &'static str,
    default_value: bool,
    preserve_non_default: bool,
}

pub struct ManagedBackendHandle {
    child: Option<Child>,
    base_url: String,
    admin_key: String,
}

impl ManagedBackendHandle {
    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    pub fn admin_key(&self) -> Option<&str> {
        if self.admin_key.is_empty() {
            None
        } else {
            Some(self.admin_key.as_str())
        }
    }
}

impl Drop for ManagedBackendHandle {
    fn drop(&mut self) {
        if let Some(child) = self.child.as_mut() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

pub fn safe_mode_requested() -> bool {
    std::env::args().any(|arg| arg.eq_ignore_ascii_case("--safe-mode"))
        || std::env::var("SB_DESKTOP_SAFE_MODE")
            .map(|value| matches!(value.trim().to_ascii_lowercase().as_str(), "1" | "true" | "yes" | "on"))
            .unwrap_or(false)
}

pub fn bundled_backend_root(resource_dir: &Path) -> Option<PathBuf> {
    let candidate = resource_dir.join(RESOURCE_DIR_NAME);
    if candidate.join("main.py").exists() {
        Some(candidate)
    } else {
        None
    }
}

pub async fn ensure_and_start_managed_backend(
    bundled_root: PathBuf,
    app_local_data_dir: PathBuf,
    desired_admin_key: Option<String>,
    vault_secrets: BTreeMap<String, String>,
    force_safe_mode: bool,
) -> Result<ManagedBackendHandle, String> {
    let runtime_root = install_bundled_backend(&bundled_root, &app_local_data_dir)?;
    start_managed_backend_runtime(runtime_root, desired_admin_key, vault_secrets, force_safe_mode).await
}

pub async fn restore_previous_and_start_managed_backend(
    app_local_data_dir: PathBuf,
    desired_admin_key: Option<String>,
    vault_secrets: BTreeMap<String, String>,
) -> Result<ManagedBackendHandle, String> {
    let runtime_root = restore_previous_runtime(&app_local_data_dir)?;
    start_managed_backend_runtime(runtime_root, desired_admin_key, vault_secrets, true).await
}

fn previous_runtime_root(app_local_data_dir: &Path) -> PathBuf {
    app_local_data_dir.join(PREVIOUS_INSTALL_DIR_NAME)
}

#[cfg(target_os = "windows")]
fn best_effort_stop_stale_managed_backend_processes(install_root: &Path) {
    use std::os::windows::process::CommandExt;

    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    let script = r#"
$ErrorActionPreference = 'SilentlyContinue'
$root = [Environment]::GetEnvironmentVariable('GOKDOGAN_MANAGED_BACKEND_ROOT')
if ([string]::IsNullOrWhiteSpace($root)) { exit 0 }
$root = [IO.Path]::GetFullPath($root).TrimEnd('\\')
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
    $pidValue = [int]$_.ProcessId
    if ($pidValue -le 0) { return }
    $exe = [string]$_.ExecutablePath
    $cmd = [string]$_.CommandLine
    $matchesRoot = $false
    if (-not [string]::IsNullOrWhiteSpace($exe)) {
        try { $matchesRoot = ([IO.Path]::GetFullPath($exe)).StartsWith($root, [StringComparison]::OrdinalIgnoreCase) } catch {}
    }
    if (-not $matchesRoot -and -not [string]::IsNullOrWhiteSpace($cmd)) {
        $matchesRoot = $cmd.IndexOf($root, [StringComparison]::OrdinalIgnoreCase) -ge 0
    }
    if ($matchesRoot) {
        Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
    }
}
"#;

    let _ = Command::new("powershell.exe")
        .args([
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ])
        .env("GOKDOGAN_MANAGED_BACKEND_ROOT", install_root)
        .creation_flags(CREATE_NO_WINDOW)
        .status();
    std::thread::sleep(Duration::from_millis(350));
}

#[cfg(not(target_os = "windows"))]
fn best_effort_stop_stale_managed_backend_processes(_install_root: &Path) {}

#[cfg(target_os = "windows")]
fn clear_readonly_attributes(path: &Path) {
    if let Ok(metadata) = fs::metadata(path) {
        let mut permissions = metadata.permissions();
        if permissions.readonly() {
            permissions.set_readonly(false);
            let _ = fs::set_permissions(path, permissions);
        }
        if metadata.is_dir() {
            if let Ok(entries) = fs::read_dir(path) {
                for entry in entries.flatten() {
                    clear_readonly_attributes(&entry.path());
                }
            }
        }
    }
}

#[cfg(not(target_os = "windows"))]
fn clear_readonly_attributes(_path: &Path) {}

fn remove_dir_all_with_retry(path: &Path, error_prefix: &str) -> Result<(), String> {
    if !path.exists() {
        return Ok(());
    }
    let mut last_error = None;
    for attempt in 0..8u64 {
        clear_readonly_attributes(path);
        match fs::remove_dir_all(path) {
            Ok(()) => return Ok(()),
            Err(error) => {
                last_error = Some(error);
                std::thread::sleep(Duration::from_millis(120 + attempt * 140));
            }
        }
    }
    Err(format!(
        "{error_prefix}:{}",
        last_error
            .map(|error| error.to_string())
            .unwrap_or_else(|| "unknown".to_string())
    ))
}

fn remove_file_with_retry(path: &Path, error_prefix: &str) -> Result<(), String> {
    if !path.exists() {
        return Ok(());
    }
    let mut last_error = None;
    for attempt in 0..8u64 {
        clear_readonly_attributes(path);
        match fs::remove_file(path) {
            Ok(()) => return Ok(()),
            Err(error) => {
                last_error = Some(error);
                std::thread::sleep(Duration::from_millis(120 + attempt * 140));
            }
        }
    }
    Err(format!(
        "{error_prefix}:{}",
        last_error
            .map(|error| error.to_string())
            .unwrap_or_else(|| "unknown".to_string())
    ))
}

fn snapshot_previous_runtime(install_root: &Path, previous_root: &Path) -> Result<(), String> {
    if !install_root.join("main.py").exists() {
        return Ok(());
    }
    if previous_root.exists() {
        remove_dir_all_with_retry(previous_root, "managed_backend_previous_remove_failed")?;
    }
    fs::create_dir_all(previous_root)
        .map_err(|e| format!("managed_backend_previous_dir_failed:{e}"))?;
    sync_runtime_tree(install_root, previous_root)?;
    sync_manifest_owned_data(install_root, previous_root)?;
    sync_release_attestation(install_root, previous_root)?;
    Ok(())
}

fn clear_runtime_tree(root: &Path) -> Result<(), String> {
    if !root.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(root).map_err(|e| format!("managed_backend_clear_read_failed:{e}"))? {
        let entry = entry.map_err(|e| format!("managed_backend_clear_entry_failed:{e}"))?;
        let file_name = entry.file_name();
        if PERSISTENT_NAMES.contains(&file_name.to_string_lossy().as_ref()) {
            continue;
        }
        let path = entry.path();
        let kind = entry.file_type().map_err(|e| format!("managed_backend_clear_type_failed:{e}"))?;
        if kind.is_dir() {
            let prefix = format!("managed_backend_clear_dir_failed:{}", path.display());
            remove_dir_all_with_retry(&path, &prefix)?;
        } else {
            let prefix = format!("managed_backend_clear_file_failed:{}", path.display());
            remove_file_with_retry(&path, &prefix)?;
        }
    }
    Ok(())
}

fn restore_previous_runtime(app_local_data_dir: &Path) -> Result<PathBuf, String> {
    let install_root = app_local_data_dir.join(INSTALL_DIR_NAME);
    let previous_root = previous_runtime_root(app_local_data_dir);
    if !previous_root.join("main.py").exists() {
        return Err("managed_backend_previous_runtime_missing".to_string());
    }
    verify_runtime_integrity(&previous_root)?;
    fs::create_dir_all(&install_root)
        .map_err(|e| format!("managed_backend_restore_dir_failed:{e}"))?;
    best_effort_stop_stale_managed_backend_processes(&install_root);
    clear_runtime_tree(&install_root)?;
    sync_runtime_tree(&previous_root, &install_root)?;
    sync_manifest_owned_data(&previous_root, &install_root)?;
    sync_release_attestation(&previous_root, &install_root)?;
    verify_runtime_integrity(&install_root)?;
    Ok(install_root)
}

async fn start_managed_backend_runtime(
    runtime_root: PathBuf,
    desired_admin_key: Option<String>,
    vault_secrets: BTreeMap<String, String>,
    force_safe_mode: bool,
) -> Result<ManagedBackendHandle, String> {
    let python_bin = resolve_python_bin(&runtime_root)?;
    let port = reserve_loopback_port()?;
    let base_url = format!("http://127.0.0.1:{port}");
    let data_dir = runtime_root.join("data");
    fs::create_dir_all(&data_dir).map_err(|e| format!("managed_backend_data_dir_failed:{e}"))?;
    let secrets = ensure_env_file(&runtime_root, desired_admin_key)?;

    let stdout_log = data_dir.join("backend_stdout.log");
    let stderr_log = data_dir.join("backend_stderr.log");
    let stdout = fs::OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&stdout_log)
        .map_err(|e| format!("managed_backend_stdout_log_failed:{e}"))?;
    let stderr = fs::OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&stderr_log)
        .map_err(|e| format!("managed_backend_stderr_log_failed:{e}"))?;

    let mut command = Command::new(&python_bin);
    command
        .current_dir(&runtime_root)
        .arg("-B")
        .arg("-m")
        .arg("uvicorn")
        .arg("main:app")
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(port.to_string())
        .arg("--timeout-keep-alive")
        .arg("120")
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("SB_DATA_DIR", data_dir.as_os_str())
        .env("SB_DESKTOP_MANAGED_RUNTIME", "true");

    if force_safe_mode || safe_mode_requested() {
        command
            .env("SB_DESKTOP_SAFE_MODE", "true")
            .env("SB_ALLOW_ACTIVE_RECON", "false")
            .env("SB_ALLOW_AGENT_SHELL", "false");
    }

    for (key, value) in vault_secrets {
        if backend_vault_secret_allowed(&key) {
            command.env(key, value);
        }
    }

    if let Some(privacy_core_lib) = bundled_privacy_core_lib(&runtime_root) {
        command.env("PRIVACY_CORE_LIB", privacy_core_lib.as_os_str());
    }
    if let Some(node_bin) = bundled_node_bin(&runtime_root) {
        command.env("SB_NODE_BIN", node_bin.as_os_str());
    }
    let playwright_browsers = runtime_root.join("playwright-browsers");
    if playwright_browsers.exists() {
        command.env("PLAYWRIGHT_BROWSERS_PATH", playwright_browsers.as_os_str());
    }

    let mut child = command
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .spawn()
        .map_err(|e| format!("managed_backend_spawn_failed:{e}"))?;

    wait_for_backend_ready(&base_url, &mut child).await?;

    Ok(ManagedBackendHandle {
        child: Some(child),
        base_url,
        admin_key: secrets.admin_key,
    })
}

fn install_bundled_backend(
    bundled_root: &Path,
    app_local_data_dir: &Path,
) -> Result<PathBuf, String> {
    verify_runtime_integrity(bundled_root)?;
    let install_root = app_local_data_dir.join(INSTALL_DIR_NAME);
    let bundled_version = read_trimmed_file(&bundled_root.join(BUNDLE_VERSION_FILE))?;
    let installed_version = read_trimmed_file_optional(&install_root.join(BUNDLE_VERSION_FILE));
    let bundled_manifest = fs::read(bundled_root.join(RUNTIME_INTEGRITY_MANIFEST_FILE))
        .map_err(|e| format!("managed_backend_integrity_manifest_missing:{e}"))?;
    let installed_manifest = fs::read(install_root.join(RUNTIME_INTEGRITY_MANIFEST_FILE)).ok();
    let manifest_changed = installed_manifest.as_deref() != Some(bundled_manifest.as_slice());
    let should_sync = !install_root.join("main.py").exists()
        || installed_version.as_deref() != Some(bundled_version.as_str())
        || manifest_changed;

    if should_sync {
        fs::create_dir_all(&install_root)
            .map_err(|e| format!("managed_backend_install_dir_failed:{e}"))?;
        if install_root.join("main.py").exists() && installed_version.is_some() {
            let previous_root = previous_runtime_root(app_local_data_dir);
            if verify_runtime_integrity(&install_root).is_ok() {
                snapshot_previous_runtime(&install_root, &previous_root)?;
            } else if previous_root.exists() {
                remove_dir_all_with_retry(&previous_root, "managed_backend_previous_remove_failed")?;
            }
        }
        // A previous desktop session can leave its bundled Python child alive
        // after the visible window is closed (for example via tray/forced
        // shutdown). Stop only processes whose executable/command line points
        // inside this managed runtime, then retry Windows file removal while
        // keeping .env and analyst data intact.
        best_effort_stop_stale_managed_backend_processes(&install_root);
        clear_runtime_tree(&install_root)?;
        sync_runtime_tree(bundled_root, &install_root)?;
        sync_manifest_owned_data(bundled_root, &install_root)?;
        fs::write(
            install_root.join(BUNDLE_VERSION_FILE),
            format!("{bundled_version}\n"),
        )
        .map_err(|e| format!("managed_backend_version_write_failed:{e}"))?;
    }

    fs::create_dir_all(install_root.join("data"))
        .map_err(|e| format!("managed_backend_data_preserve_dir_failed:{e}"))?;
    sync_release_attestation(bundled_root, &install_root)?;
    verify_runtime_integrity(&install_root)?;
    Ok(install_root)
}

fn sync_runtime_tree(src: &Path, dst: &Path) -> Result<(), String> {
    for entry in fs::read_dir(src).map_err(|e| format!("managed_backend_read_dir_failed:{e}"))? {
        let entry = entry.map_err(|e| format!("managed_backend_dir_entry_failed:{e}"))?;
        let file_name = entry.file_name();
        let file_name_str = file_name.to_string_lossy();
        if PERSISTENT_NAMES.contains(&file_name_str.as_ref()) {
            continue;
        }

        let src_path = entry.path();
        let dst_path = dst.join(&file_name);
        let file_type = entry
            .file_type()
            .map_err(|e| format!("managed_backend_file_type_failed:{e}"))?;

        if file_type.is_dir() {
            fs::create_dir_all(&dst_path)
                .map_err(|e| format!("managed_backend_mkdir_failed:{e}"))?;
            sync_runtime_tree(&src_path, &dst_path)?;
        } else {
            if let Some(parent) = dst_path.parent() {
                fs::create_dir_all(parent)
                    .map_err(|e| format!("managed_backend_parent_dir_failed:{e}"))?;
            }
            fs::copy(&src_path, &dst_path)
                .map_err(|e| format!("managed_backend_copy_failed:{e}"))?;
        }
    }
    Ok(())
}

/// Copy only bundle-owned files under `data/` as declared by the integrity
/// manifest. Runtime/user data (API key store, logs, databases, caches) stays
/// untouched. This fixes upgrades where `data/` must remain persistent while
/// deterministic runtime assets such as AIS SPKI pins still need to be staged.
fn sync_manifest_owned_data(src_root: &Path, dst_root: &Path) -> Result<(), String> {
    let manifest_path = src_root.join(RUNTIME_INTEGRITY_MANIFEST_FILE);
    let rendered = fs::read_to_string(&manifest_path)
        .map_err(|e| format!("managed_backend_integrity_manifest_missing:{e}"))?;
    let manifest: RuntimeIntegrityManifest = serde_json::from_str(&rendered)
        .map_err(|e| format!("managed_backend_integrity_manifest_invalid:{e}"))?;

    for entry in &manifest.files {
        let relative = safe_manifest_relative_path(&entry.path)?;
        let mut components = relative.components();
        let is_data = matches!(
            components.next(),
            Some(std::path::Component::Normal(part)) if part == std::ffi::OsStr::new("data")
        );
        if !is_data {
            continue;
        }
        let src_path = src_root.join(&relative);
        if !src_path.is_file() {
            return Err(format!("managed_backend_integrity_missing_file:{}", entry.path));
        }
        let dst_path = dst_root.join(&relative);
        if let Some(parent) = dst_path.parent() {
            fs::create_dir_all(parent)
                .map_err(|e| format!("managed_backend_seed_data_dir_failed:{e}"))?;
        }
        fs::copy(&src_path, &dst_path)
            .map_err(|e| format!("managed_backend_seed_data_copy_failed:{}:{e}", entry.path))?;
    }
    Ok(())
}

fn sync_release_attestation(bundled_root: &Path, install_root: &Path) -> Result<(), String> {
    let bundled_path = release_attestation_path(bundled_root);
    let installed_path = release_attestation_path(install_root);
    if !bundled_path.exists() {
        return Ok(());
    }
    if let Some(parent) = installed_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("managed_backend_attestation_dir_failed:{e}"))?;
    }
    fs::copy(&bundled_path, &installed_path)
        .map_err(|e| format!("managed_backend_attestation_copy_failed:{e}"))?;
    Ok(())
}


fn backend_vault_secret_allowed(key: &str) -> bool {
    matches!(
        key,
        "OPENCTI_TOKEN"
            | "OPENCTI_URL"
            | "OPENCTI_CONNECTOR_ID"
            | "FRED_API_KEY"
            | "RELIEFWEB_APPNAME"
            | "OPENSKY_CLIENT_ID"
            | "OPENSKY_CLIENT_SECRET"
            | "AIS_API_KEY"
            | "AISSTREAM_API_KEY"
            | "AISHUB_USERNAME"
            | "GFW_API_TOKEN"
            | "FIRMS_MAP_KEY"
            | "AIRFRAMES_API_KEY"
            | "SHODAN_API_KEY"
            | "FINNHUB_API_KEY"
            | "SENTINEL_CLIENT_ID"
            | "SENTINEL_CLIENT_SECRET"
            | "LTA_ACCOUNT_KEY"
            | "OPENAQ_API_KEY"
            | "WINDY_API_KEY"
            | "TOMTOM_API_KEY"
            | "GOKDOGAN_PUBLIC_CAMERA_CATALOG_URLS"
            | "GOKDOGAN_PUBLIC_CAMERA_CATALOG_HOSTS"
            | "GOKDOGAN_PUBLIC_CAMERA_MEDIA_HOSTS"
            | "ALERTS_IN_UA_TOKEN"
            | "NUFORC_MAPBOX_TOKEN"
            | "ABUSEIPDB_API_KEY"
            | "EIA_API_KEY"
            | "BLS_API_KEY"
    )
}

fn bundled_privacy_core_lib(runtime_root: &Path) -> Option<PathBuf> {
    let file_name = if cfg!(target_os = "windows") {
        "privacy_core.dll"
    } else if cfg!(target_os = "macos") {
        "libprivacy_core.dylib"
    } else {
        "libprivacy_core.so"
    };
    let candidate = runtime_root.join(file_name);
    candidate.exists().then_some(candidate)
}

fn release_attestation_path(root: &Path) -> PathBuf {
    RELEASE_ATTESTATION_RELATIVE_PATH
        .iter()
        .fold(root.to_path_buf(), |acc, part| acc.join(part))
}

fn ensure_env_file(
    runtime_root: &Path,
    desired_admin_key: Option<String>,
) -> Result<ManagedBackendSecrets, String> {
    let env_path = runtime_root.join(".env");
    if env_path.exists() {
        return seed_managed_env(&env_path, desired_admin_key);
    }
    let example_path = runtime_root.join(".env.example");
    if example_path.exists() {
        fs::copy(&example_path, &env_path)
            .map_err(|e| format!("managed_backend_env_copy_failed:{e}"))?;
    } else {
        fs::write(&env_path, b"").map_err(|e| format!("managed_backend_env_create_failed:{e}"))?;
    }
    seed_managed_env(&env_path, desired_admin_key)
}

fn seed_managed_env(
    env_path: &Path,
    desired_admin_key: Option<String>,
) -> Result<ManagedBackendSecrets, String> {
    let mut lines: Vec<String> = fs::read_to_string(env_path)
        .unwrap_or_default()
        .lines()
        .map(str::to_owned)
        .collect();
    let mut modified = false;
    let mut resolved_admin_key = String::new();

    for spec in managed_secret_specs() {
        let override_value = if spec.key == "ADMIN_KEY" {
            desired_admin_key.as_deref()
        } else {
            None
        };
        let mut found = false;

        for line in &mut lines {
            if let Some(current) = parse_env_value(line, spec.key) {
                found = true;
                if let Some(forced) = override_value {
                    if current != forced {
                        *line = format!("{}={}", spec.key, forced);
                        modified = true;
                    }
                    if spec.key == "ADMIN_KEY" {
                        resolved_admin_key = forced.to_string();
                    }
                } else if is_invalid_secret_value(current, spec.min_len) {
                    let generated = generate_secret()?;
                    *line = format!("{}={}", spec.key, generated);
                    modified = true;
                    if spec.key == "ADMIN_KEY" {
                        resolved_admin_key = generated;
                    }
                } else if spec.key == "ADMIN_KEY" {
                    resolved_admin_key = current.to_string();
                }
                break;
            }
        }

        if !found {
            let value = if let Some(forced) = override_value {
                forced.to_string()
            } else {
                generate_secret()?
            };
            if !lines.is_empty() && !lines.last().is_some_and(|line| line.is_empty()) {
                lines.push(String::new());
            }
            lines.push(format!("{}={}", spec.key, value));
            modified = true;
            if spec.key == "ADMIN_KEY" {
                resolved_admin_key = value;
            }
        }
    }

    for spec in managed_bool_default_specs() {
        let mut found = false;

        for line in &mut lines {
            if let Some(current) = parse_env_value(line, spec.key) {
                found = true;
                match parse_env_boolish(current) {
                    Some(parsed) if spec.preserve_non_default || parsed == spec.default_value => {}
                    _ => {
                        *line = format!("{}={}", spec.key, render_env_bool(spec.default_value));
                        modified = true;
                    }
                }
                break;
            }
        }

        if !found {
            if !lines.is_empty() && !lines.last().is_some_and(|line| line.is_empty()) {
                lines.push(String::new());
            }
            lines.push(format!(
                "{}={}",
                spec.key,
                render_env_bool(spec.default_value)
            ));
            modified = true;
        }
    }

    if modified {
        let mut rendered = lines.join("\n");
        if !rendered.ends_with('\n') {
            rendered.push('\n');
        }
        fs::write(env_path, rendered)
            .map_err(|e| format!("managed_backend_env_seed_failed:{e}"))?;
    }

    Ok(ManagedBackendSecrets {
        admin_key: resolved_admin_key,
    })
}

fn managed_secret_specs() -> Vec<ManagedSecretSpec> {
    let mut specs = vec![
        ManagedSecretSpec {
            key: "ADMIN_KEY",
            min_len: 32,
        },
        ManagedSecretSpec {
            key: "MESH_PEER_PUSH_SECRET",
            min_len: 16,
        },
        ManagedSecretSpec {
            key: "MESH_DM_TOKEN_PEPPER",
            min_len: 16,
        },
    ];

    if !cfg!(target_os = "windows") {
        specs.push(ManagedSecretSpec {
            key: "MESH_SECURE_STORAGE_SECRET",
            min_len: 16,
        });
    }

    specs
}

fn managed_bool_default_specs() -> Vec<ManagedBoolDefaultSpec> {
    vec![
        // Gökdoğan desktop is a live OSINT workstation. Fresh managed installs
        // enable passive/public live feeds by default; operators can still opt
        // out explicitly in their managed environment.
        ManagedBoolDefaultSpec {
            key: "GOKDOGAN_LIVE_DATA",
            default_value: true,
            preserve_non_default: true,
        },
        ManagedBoolDefaultSpec {
            key: "FINANCIAL_ENABLED",
            default_value: true,
            preserve_non_default: true,
        },
        ManagedBoolDefaultSpec {
            key: "MESH_MQTT_ENABLED",
            default_value: true,
            preserve_non_default: true,
        },
        ManagedBoolDefaultSpec {
            key: "MESH_BLOCK_LEGACY_NODE_ID_COMPAT",
            default_value: true,
            preserve_non_default: false,
        },
        ManagedBoolDefaultSpec {
            key: "MESH_BLOCK_LEGACY_AGENT_ID_LOOKUP",
            default_value: true,
            preserve_non_default: true,
        },
        // High-privilege workstation capabilities are explicit opt-ins in
        // managed desktop installs. A user can intentionally change these
        // values in the managed .env, but they are never silently enabled.
        ManagedBoolDefaultSpec {
            key: "SB_ALLOW_ACTIVE_RECON",
            default_value: false,
            preserve_non_default: true,
        },
        ManagedBoolDefaultSpec {
            key: "SB_ALLOW_AGENT_SHELL",
            default_value: false,
            preserve_non_default: true,
        },
        // Privacy/DEX primitives under InfoNet are experimental scaffolding.
        // Managed desktop builds keep them disabled even if an older runtime
        // environment had opted in; operators can use source/dev mode for labs.
        ManagedBoolDefaultSpec {
            key: "SB_ENABLE_EXPERIMENTAL_PRIVACY",
            default_value: false,
            preserve_non_default: false,
        },
    ]
}

fn parse_env_value<'a>(line: &'a str, key: &str) -> Option<&'a str> {
    let trimmed = line.trim_start();
    if trimmed.is_empty() || trimmed.starts_with('#') {
        return None;
    }
    let normalized = trimmed.strip_prefix("export ").unwrap_or(trimmed);
    let (line_key, raw_value) = normalized.split_once('=')?;
    if line_key.trim() != key {
        return None;
    }
    Some(raw_value.trim().trim_matches('"').trim_matches('\'').trim())
}

fn parse_env_boolish(value: &str) -> Option<bool> {
    match value.trim().to_ascii_lowercase().as_str() {
        "1" | "true" | "yes" | "on" => Some(true),
        "0" | "false" | "no" | "off" => Some(false),
        _ => None,
    }
}

fn render_env_bool(value: bool) -> &'static str {
    if value {
        "true"
    } else {
        "false"
    }
}

fn is_invalid_secret_value(value: &str, min_len: usize) -> bool {
    let raw = value.trim();
    let lowered = raw.to_ascii_lowercase();
    raw.is_empty() || lowered == "change-me" || lowered == "changeme" || raw.len() < min_len
}

fn generate_secret() -> Result<String, String> {
    let mut bytes = [0u8; GENERATED_SECRET_BYTES];
    getrandom::getrandom(&mut bytes)
        .map_err(|e| format!("managed_backend_secret_rng_failed:{e}"))?;
    let mut out = String::with_capacity(GENERATED_SECRET_BYTES * 2);
    for byte in bytes {
        let _ = write!(&mut out, "{byte:02x}");
    }
    Ok(out)
}

fn reserve_loopback_port() -> Result<u16, String> {
    let listener = TcpListener::bind("127.0.0.1:0")
        .map_err(|e| format!("managed_backend_port_bind_failed:{e}"))?;
    let port = listener
        .local_addr()
        .map_err(|e| format!("managed_backend_port_addr_failed:{e}"))?
        .port();
    drop(listener);
    Ok(port)
}

fn resolve_python_bin(runtime_root: &Path) -> Result<PathBuf, String> {
    // Release desktop packages prefer a relocatable Python distribution
    // staged under python-runtime/. This avoids depending on a machine-wide
    // Python installation after the MSI/NSIS package is installed.
    let portable = if cfg!(target_os = "windows") {
        runtime_root.join("python-runtime").join("python.exe")
    } else {
        runtime_root.join("python-runtime").join("bin").join("python3")
    };
    if portable.exists() {
        return Ok(portable);
    }

    let selected_venv = read_trimmed_file_optional(&runtime_root.join(".venv-dir"))
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "venv".to_string());

    let mut candidate_roots = vec![runtime_root.join(&selected_venv)];
    if selected_venv != "venv" {
        candidate_roots.push(runtime_root.join("venv"));
    }

    let candidates = if cfg!(target_os = "windows") {
        candidate_roots
            .into_iter()
            .map(|root| root.join("Scripts").join("python.exe"))
            .collect::<Vec<_>>()
    } else {
        candidate_roots
            .into_iter()
            .flat_map(|root| {
                [
                    root.join("bin").join("python3"),
                    root.join("bin").join("python"),
                ]
            })
            .collect::<Vec<_>>()
    };

    for candidate in candidates {
        if candidate.exists() {
            return Ok(candidate);
        }
    }
    Err("managed_backend_python_missing".to_string())
}

fn bundled_node_bin(runtime_root: &Path) -> Option<PathBuf> {
    let candidate = if cfg!(target_os = "windows") {
        runtime_root.join("node-runtime").join("node.exe")
    } else {
        runtime_root.join("node-runtime").join("node")
    };
    candidate.exists().then_some(candidate)
}

async fn wait_for_backend_ready(base_url: &str, child: &mut Child) -> Result<(), String> {
    let client = reqwest::Client::new();
    let deadline = Instant::now() + Duration::from_secs(45);
    let health_url = format!("{base_url}/api/health");

    while Instant::now() < deadline {
        if let Some(status) = child
            .try_wait()
            .map_err(|e| format!("managed_backend_wait_failed:{e}"))?
        {
            return Err(format!("managed_backend_exited_early:{status}"));
        }

        if let Ok(response) = client.get(&health_url).send().await {
            if response.status().is_success() {
                return Ok(());
            }
        }

        tokio::time::sleep(Duration::from_millis(500)).await;
    }

    let _ = child.kill();
    let _ = child.wait();
    Err("managed_backend_health_timeout".to_string())
}

fn read_trimmed_file(path: &Path) -> Result<String, String> {
    fs::read_to_string(path)
        .map(|s| s.trim().to_string())
        .map_err(|e| format!("managed_backend_version_read_failed:{e}"))
}

fn read_trimmed_file_optional(path: &Path) -> Option<String> {
    fs::read_to_string(path).ok().map(|s| s.trim().to_string())
}

#[cfg(test)]
mod tests {
    use super::*;


    fn write_test_integrity_manifest(root: &Path) {
        let mut files = Vec::new();
        fn walk(root: &Path, current: &Path, files: &mut Vec<serde_json::Value>) {
            let mut entries: Vec<_> = fs::read_dir(current).unwrap().map(|e| e.unwrap()).collect();
            entries.sort_by_key(|e| e.file_name());
            for entry in entries {
                let path = entry.path();
                let rel = path.strip_prefix(root).unwrap();
                if rel == Path::new(RUNTIME_INTEGRITY_MANIFEST_FILE) {
                    continue;
                }
                if entry.file_type().unwrap().is_dir() {
                    walk(root, &path, files);
                } else {
                    files.push(serde_json::json!({
                        "path": rel.to_string_lossy().replace('\\', "/"),
                        "size": fs::metadata(&path).unwrap().len(),
                        "sha256": sha256_file(&path).unwrap(),
                    }));
                }
            }
        }
        walk(root, root, &mut files);
        let bundle_version = fs::read_to_string(root.join(BUNDLE_VERSION_FILE)).unwrap().trim().to_string();
        let manifest = serde_json::json!({
            "manifest_version": 1,
            "algorithm": "sha256",
            "bundle_version": bundle_version,
            "file_count": files.len(),
            "files": files,
        });
        fs::write(
            root.join(RUNTIME_INTEGRITY_MANIFEST_FILE),
            format!("{}\n", serde_json::to_string_pretty(&manifest).unwrap()),
        )
        .unwrap();
    }

    #[test]
    fn bundled_backend_root_requires_main_py() {
        let temp = std::env::temp_dir().join(format!(
            "sb_backend_root_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let resource_dir = temp.join("resources");
        let backend_dir = resource_dir.join(RESOURCE_DIR_NAME);
        fs::create_dir_all(&backend_dir).unwrap();

        assert!(bundled_backend_root(&resource_dir).is_none());

        fs::write(backend_dir.join("main.py"), "print('ok')").unwrap();
        assert_eq!(
            bundled_backend_root(&resource_dir),
            Some(backend_dir.clone())
        );

        let _ = fs::remove_dir_all(temp);
    }

    #[test]
    fn sync_runtime_tree_preserves_env_and_data() {
        let temp = std::env::temp_dir().join(format!(
            "sb_backend_sync_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let src = temp.join("src");
        let dst = temp.join("dst");
        fs::create_dir_all(src.join("config")).unwrap();
        fs::create_dir_all(dst.join("data")).unwrap();
        fs::write(src.join("main.py"), "print('new')").unwrap();
        fs::write(src.join(".env.example"), "ADMIN_KEY=").unwrap();
        fs::write(dst.join(".env"), "preserve_me").unwrap();
        fs::write(dst.join("data").join("keep.txt"), "keep").unwrap();

        sync_runtime_tree(&src, &dst).unwrap();

        assert_eq!(fs::read_to_string(dst.join(".env")).unwrap(), "preserve_me");
        assert_eq!(
            fs::read_to_string(dst.join("data").join("keep.txt")).unwrap(),
            "keep"
        );
        assert_eq!(
            fs::read_to_string(dst.join("main.py")).unwrap(),
            "print('new')"
        );

        let _ = fs::remove_dir_all(temp);
    }

    #[test]
    fn previous_runtime_snapshot_and_restore_preserve_user_state() {
        let temp = std::env::temp_dir().join(format!(
            "sb_backend_rollback_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let app_data = temp.join("app-data");
        let install = app_data.join(INSTALL_DIR_NAME);
        let previous = previous_runtime_root(&app_data);
        fs::create_dir_all(install.join("data")).unwrap();
        fs::write(install.join("main.py"), "print('old')").unwrap();
        fs::write(install.join(BUNDLE_VERSION_FILE), "0.9.86-R7\n").unwrap();
        write_test_integrity_manifest(&install);
        fs::write(install.join(".env"), "ADMIN_KEY=keep-me").unwrap();
        fs::write(install.join("data").join("keep.txt"), "analyst-data").unwrap();

        snapshot_previous_runtime(&install, &previous).unwrap();
        clear_runtime_tree(&install).unwrap();
        fs::write(install.join("main.py"), "print('broken-new')").unwrap();
        fs::write(install.join(BUNDLE_VERSION_FILE), "0.9.87-R8\n").unwrap();

        let restored = restore_previous_runtime(&app_data).unwrap();
        assert_eq!(restored, install);
        assert_eq!(fs::read_to_string(install.join("main.py")).unwrap(), "print('old')");
        assert_eq!(
            fs::read_to_string(install.join(BUNDLE_VERSION_FILE)).unwrap().trim(),
            "0.9.86-R7"
        );
        assert_eq!(fs::read_to_string(install.join(".env")).unwrap(), "ADMIN_KEY=keep-me");
        assert_eq!(
            fs::read_to_string(install.join("data").join("keep.txt")).unwrap(),
            "analyst-data"
        );

        let _ = fs::remove_dir_all(temp);
    }

    #[test]
    fn sync_release_attestation_updates_only_attestation_file() {
        let temp = std::env::temp_dir().join(format!(
            "sb_backend_attestation_sync_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let src = temp.join("src");
        let dst = temp.join("dst");
        fs::create_dir_all(src.join("data")).unwrap();
        fs::create_dir_all(dst.join("data")).unwrap();
        fs::write(release_attestation_path(&src), "{\"commit\":\"new\"}\n").unwrap();
        fs::write(release_attestation_path(&dst), "{\"commit\":\"old\"}\n").unwrap();
        fs::write(dst.join("data").join("keep.txt"), "keep").unwrap();

        sync_release_attestation(&src, &dst).unwrap();

        assert_eq!(
            fs::read_to_string(release_attestation_path(&dst)).unwrap(),
            "{\"commit\":\"new\"}\n"
        );
        assert_eq!(
            fs::read_to_string(dst.join("data").join("keep.txt")).unwrap(),
            "keep"
        );

        let _ = fs::remove_dir_all(temp);
    }

    #[test]
    fn ensure_env_file_generates_required_managed_secrets() {
        let temp = std::env::temp_dir().join(format!(
            "sb_backend_env_seed_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&temp).unwrap();
        fs::write(temp.join(".env.example"), "AIS_API_KEY=\n").unwrap();

        let secrets = ensure_env_file(&temp, None).unwrap();
        let env_text = fs::read_to_string(temp.join(".env")).unwrap();
        let env_lines: Vec<&str> = env_text.lines().collect();

        assert!(secrets.admin_key.len() >= 32);
        assert!(
            env_lines
                .iter()
                .find_map(|line| parse_env_value(line, "ADMIN_KEY"))
                .unwrap()
                .len()
                >= 32
        );
        assert!(
            env_lines
                .iter()
                .find_map(|line| parse_env_value(line, "MESH_PEER_PUSH_SECRET"))
                .unwrap()
                .len()
                >= 16
        );
        assert!(
            env_lines
                .iter()
                .find_map(|line| parse_env_value(line, "MESH_DM_TOKEN_PEPPER"))
                .unwrap()
                .len()
                >= 16
        );
        assert_eq!(
            env_lines
                .iter()
                .find_map(|line| parse_env_value(line, "MESH_BLOCK_LEGACY_NODE_ID_COMPAT"))
                .unwrap(),
            "true"
        );
        assert_eq!(
            env_lines
                .iter()
                .find_map(|line| parse_env_value(line, "MESH_BLOCK_LEGACY_AGENT_ID_LOOKUP"))
                .unwrap(),
            "true"
        );
        assert_eq!(
            env_lines
                .iter()
                .find_map(|line| parse_env_value(line, "SB_ALLOW_ACTIVE_RECON"))
                .unwrap(),
            "false"
        );
        assert_eq!(
            env_lines
                .iter()
                .find_map(|line| parse_env_value(line, "SB_ALLOW_AGENT_SHELL"))
                .unwrap(),
            "false"
        );
        if cfg!(target_os = "windows") {
            assert!(env_lines
                .iter()
                .find_map(|line| parse_env_value(line, "MESH_SECURE_STORAGE_SECRET"))
                .is_none());
        } else {
            assert!(
                env_lines
                    .iter()
                    .find_map(|line| parse_env_value(line, "MESH_SECURE_STORAGE_SECRET"))
                    .unwrap()
                    .len()
                    >= 16
            );
        }

        let _ = fs::remove_dir_all(temp);
    }

    #[test]
    fn ensure_env_file_replaces_invalid_values_and_preserves_valid_ones() {
        let temp = std::env::temp_dir().join(format!(
            "sb_backend_env_backfill_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&temp).unwrap();
        fs::write(
            temp.join(".env"),
            "ADMIN_KEY=short\nMESH_PEER_PUSH_SECRET=change-me\nMESH_DM_TOKEN_PEPPER=valid-pepper-value-1234\nMESH_BLOCK_LEGACY_NODE_ID_COMPAT=false\nMESH_BLOCK_LEGACY_AGENT_ID_LOOKUP=\n",
        )
        .unwrap();

        let secrets = ensure_env_file(
            &temp,
            Some("desktop-admin-key-0123456789abcdef".to_string()),
        )
        .unwrap();
        let env_text = fs::read_to_string(temp.join(".env")).unwrap();
        let env_lines: Vec<&str> = env_text.lines().collect();

        assert_eq!(secrets.admin_key, "desktop-admin-key-0123456789abcdef");
        assert_eq!(
            env_lines
                .iter()
                .find_map(|line| parse_env_value(line, "ADMIN_KEY"))
                .unwrap(),
            "desktop-admin-key-0123456789abcdef"
        );
        assert_ne!(
            env_lines
                .iter()
                .find_map(|line| parse_env_value(line, "MESH_PEER_PUSH_SECRET"))
                .unwrap(),
            "change-me"
        );
        assert_eq!(
            env_lines
                .iter()
                .find_map(|line| parse_env_value(line, "MESH_DM_TOKEN_PEPPER"))
                .unwrap(),
            "valid-pepper-value-1234"
        );
        assert_eq!(
            env_lines
                .iter()
                .find_map(|line| parse_env_value(line, "MESH_BLOCK_LEGACY_NODE_ID_COMPAT"))
                .unwrap(),
            "true"
        );
        assert_eq!(
            env_lines
                .iter()
                .find_map(|line| parse_env_value(line, "MESH_BLOCK_LEGACY_AGENT_ID_LOOKUP"))
                .unwrap(),
            "true"
        );

        let _ = fs::remove_dir_all(temp);
    }

    #[test]
    fn runtime_integrity_detects_tampering_and_path_escape() {
        let temp = std::env::temp_dir().join(format!(
            "sb_backend_integrity_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&temp).unwrap();
        fs::write(temp.join("main.py"), "print('ok')").unwrap();
        fs::write(temp.join(BUNDLE_VERSION_FILE), "0.10.3\n").unwrap();
        write_test_integrity_manifest(&temp);
        assert!(verify_runtime_integrity(&temp).is_ok());

        fs::write(temp.join("main.py"), "print('tampered')").unwrap();
        let err = verify_runtime_integrity(&temp).unwrap_err();
        assert!(err.contains("integrity_"));

        assert!(safe_manifest_relative_path("../escape.py").is_err());
        assert!(safe_manifest_relative_path("/absolute.py").is_err());
        assert!(safe_manifest_relative_path("safe/path.py").is_ok());

        let _ = fs::remove_dir_all(temp);
    }

}
