mod backend_runtime;
mod bridge;
mod companion;
mod companion_server;
mod gate_crypto;
mod handlers;
mod http_client;
mod local_custody;
pub mod policy;
mod secret_vault;
mod tray;

use bridge::{clear_native_audit_report, get_native_audit_report, invoke_local_control};
use companion::{companion_disable, companion_enable, companion_open_browser, companion_status};
use policy::SharedAuditRing;
use secret_vault::{desktop_secret_delete, desktop_secret_set, desktop_secret_set_many, desktop_secret_vault_status};
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};
use url::Url;

pub struct DesktopAppState {
    pub backend_base_url: String,
    pub admin_key: Option<String>,
    pub audit_ring: SharedAuditRing,
    pub owns_managed_backend: bool,
    pub effective_safe_mode: bool,
    pub recovered_previous_runtime: bool,
}

/// Retained tray icon handle. Stored in Tauri managed state to keep the handle
/// alive for the app's lifetime — dropping it may cause the OS to unregister
/// the tray icon.
#[allow(dead_code)]
pub struct TrayHandle(tauri::tray::TrayIcon);

/// Retained app-level loopback server handle. Stored in Tauri managed state
/// so the server lives for the app's lifetime. Dropping it gracefully shuts
/// the server down (see `CompanionServerHandle::Drop`).
///
/// Wrapped in a `Mutex` to satisfy Tauri's managed-state `Send + Sync` bound:
/// the underlying handle contains a `tokio::sync::oneshot::Sender` which is
/// `Send` but not `Sync`. The mutex is never contended — the handle is only
/// touched on shutdown via `Drop`.
#[allow(dead_code)]
pub struct AppServerHandle(std::sync::Mutex<companion_server::CompanionServerHandle>);

/// Retained managed backend process handle for packaged builds. Stored in
/// managed state so the child process lives for the app's lifetime and is
/// terminated on shutdown via `Drop`.
#[allow(dead_code)]
pub struct ManagedBackendState(std::sync::Mutex<backend_runtime::ManagedBackendHandle>);

/// Retained native gate-crypto runtime. This lets the packaged native window
/// import opaque gate MLS state into the Tauri boundary and decrypt there,
/// rather than handing ordinary gate reads back to backend HTTP decrypt routes.
#[allow(dead_code)]
pub struct NativeGateCryptoState(std::sync::Mutex<gate_crypto::GateCryptoRuntime>);

// Initialization script installed into every page load of the main webview.
//
// SECURITY MODEL:
// Authoritative policy enforcement (capability mismatch, session profile
// warn/deny) lives in Rust — see policy.rs and bridge.rs. The JS-side
// preflight checks here are defense in depth only; even if bypassed via
// direct Tauri IPC, the Rust side enforces the same semantics and records
// every invocation in its AuditRing.
//
// AUDIT MODEL:
// Rust AuditRing is the authoritative audit trail for ALL invocations
// (including direct IPC bypasses). The Rust audit is accessible via Tauri
// commands: get_native_audit_report / clear_native_audit_report. The
// JS-side audit shadow below mirrors wrapper-path invocations and provides
// the synchronous getNativeControlAuditReport() interface that the
// existing frontend consumers (MeshTerminal, useMeshChat) depend on.
//
// DELIVERY MODEL (post-P6D-R):
// The script is delivered via `WebviewWindowBuilder::initialization_script`
// so it runs on every page load of the native window, regardless of the
// URL being served (static frontendDist in dev or the loopback app server
// in packaged mode). It is NOT served to the browser companion — the
// companion loads from the same loopback server but in a plain browser
// webview, which does not inject this script. That boundary preserves the
// "native window only" trust model for `__SHADOWBROKER_DESKTOP__`.
const DESKTOP_INIT_SCRIPT: &str = r#"
(function() {
  if (typeof window === 'undefined') return;
  if (window.__SHADOWBROKER_DESKTOP__) return; // idempotent on navigation

  var _auditLog = [];
  var _totalRecorded = 0;
  var MAX_AUDIT = 100;

  function _nativeInvoke(command, args) {
    var tauri = window.__TAURI__;
    var invoke = tauri && tauri.core && tauri.core.invoke;
    if (typeof invoke !== 'function') {
      return Promise.reject(new Error('native_tauri_api_unavailable'));
    }
    return invoke(command, args || {});
  }

  // --- Capability resolution (defense-in-depth, mirrors policy.rs) ---
  var _capMap = {
    'wormhole.status': 'wormhole_runtime',
    'wormhole.connect': 'wormhole_runtime',
    'wormhole.disconnect': 'wormhole_runtime',
    'wormhole.restart': 'wormhole_runtime',
    'wormhole.gate.enter': 'wormhole_gate_persona',
    'wormhole.gate.leave': 'wormhole_gate_persona',
    'wormhole.gate.personas.get': 'wormhole_gate_persona',
    'wormhole.gate.persona.create': 'wormhole_gate_persona',
    'wormhole.gate.persona.activate': 'wormhole_gate_persona',
    'wormhole.gate.persona.clear': 'wormhole_gate_persona',
    'wormhole.gate.key.get': 'wormhole_gate_key',
    'wormhole.gate.key.rotate': 'wormhole_gate_key',
    'wormhole.gate.state.resync': 'wormhole_gate_key',
    'wormhole.gate.proof': 'wormhole_gate_content',
    'wormhole.gate.message.compose': 'wormhole_gate_content',
    'wormhole.gate.message.post': 'wormhole_gate_content',
    'wormhole.gate.message.decrypt': 'wormhole_gate_content',
    'wormhole.gate.messages.decrypt': 'wormhole_gate_content',
    'settings.wormhole.get': 'settings',
    'settings.wormhole.set': 'settings',
    'settings.privacy.get': 'settings',
    'settings.privacy.set': 'settings',
    'settings.api_keys.get': 'settings',
    'settings.news.get': 'settings',
    'settings.news.set': 'settings',
    'settings.news.reset': 'settings',
    'system.update': 'settings'
  };

  // --- Profile → capabilities (defense-in-depth, mirrors policy.rs) ---
  var _profileCaps = {
    'full_app': ['wormhole_gate_persona','wormhole_gate_key','wormhole_gate_content','wormhole_runtime','settings'],
    'gate_observe': ['wormhole_gate_content'],
    'gate_operator': ['wormhole_gate_persona','wormhole_gate_key','wormhole_gate_content'],
    'wormhole_runtime': ['wormhole_runtime'],
    'settings_only': ['settings']
  };

  var _gateCommands = [
    'wormhole.gate.enter','wormhole.gate.leave',
    'wormhole.gate.personas.get','wormhole.gate.persona.create',
    'wormhole.gate.persona.activate','wormhole.gate.persona.clear',
    'wormhole.gate.key.get','wormhole.gate.key.rotate',
    'wormhole.gate.state.resync',
    'wormhole.gate.proof','wormhole.gate.message.compose',
    'wormhole.gate.message.post','wormhole.gate.message.decrypt'
  ];

  function _extractTargetRef(command, payload) {
    if (!payload || typeof payload !== 'object') return undefined;
    var gid = payload.gate_id;
    if (typeof gid !== 'string' || !gid) return undefined;
    return _gateCommands.indexOf(command) !== -1 ? gid : undefined;
  }

  function _recordAudit(entry) {
    _totalRecorded += 1;
    entry.recordedAt = Date.now();
    _auditLog.push(entry);
    if (_auditLog.length > MAX_AUDIT) {
      _auditLog.splice(0, _auditLog.length - MAX_AUDIT);
    }
  }

  window.__SHADOWBROKER_DESKTOP__ = {
    invokeLocalControl: function(command, payload, meta) {
      var expectedCap = _capMap[command];
      if (!expectedCap) {
        return Promise.reject('unsupported_control_command:' + command);
      }
      var m = meta || {};
      var profile = m.sessionProfileHint;
      var profileCaps = profile && _profileCaps[profile] ? _profileCaps[profile] : [];
      var profileAllows = !profile || profileCaps.length === 0 || profileCaps.indexOf(expectedCap) !== -1;
      var enforced = Boolean(m.enforceProfileHint && profile);
      var targetRef = _extractTargetRef(command, payload);
      var auditBase = {
        command: command,
        expectedCapability: expectedCap,
        declaredCapability: m.capability,
        sessionProfileHint: m.sessionProfileHint,
        enforceProfileHint: m.enforceProfileHint,
        profileAllows: profileAllows,
        allowedCapabilitiesConfigured: false,
        enforced: enforced
      };
      if (targetRef) auditBase.targetRef = targetRef;
      if (profile) auditBase.sessionProfile = profile;

      if (m.capability && m.capability !== expectedCap) {
        _recordAudit(Object.assign({}, auditBase, { outcome: 'capability_mismatch' }));
        return Promise.reject(
          'native_control_capability_mismatch:' + m.capability + ':' + expectedCap
        );
      }

      if (!profileAllows) {
        var profileOutcome = enforced ? 'profile_denied' : 'profile_warn';
        _recordAudit(Object.assign({}, auditBase, { outcome: profileOutcome }));
        if (enforced) {
          return Promise.reject(
            'native_control_profile_mismatch:' + profile + ':' + expectedCap
          );
        }
        console.warn('native_control_profile_mismatch:' + profile + ':' + expectedCap, {
          command: command, sessionProfileHint: m.sessionProfileHint
        });
      }

      if (profileAllows) {
        _recordAudit(Object.assign({}, auditBase, { outcome: 'allowed' }));
      }

      return _nativeInvoke('invoke_local_control', {
        command: command,
        payload: payload || null,
        meta: m.capability || m.sessionProfileHint || m.enforceProfileHint
          ? {
              capability: m.capability || null,
              sessionProfileHint: m.sessionProfileHint || null,
              enforceProfileHint: Boolean(m.enforceProfileHint)
            }
          : null
      });
    },
    getNativeControlAuditReport: function(limit) {
      var n = Math.max(1, limit || 25);
      var recent = _auditLog.slice(-n).reverse();
      var byOutcome = {};
      var lastDenied;
      var lastProfileMismatch;
      _auditLog.forEach(function(e) {
        byOutcome[e.outcome] = (byOutcome[e.outcome] || 0) + 1;
        if (e.outcome === 'profile_warn' || e.outcome === 'profile_denied') lastProfileMismatch = e;
        if (e.outcome === 'profile_denied' || e.outcome === 'capability_denied') lastDenied = e;
      });
      return {
        totalEvents: _auditLog.length,
        totalRecorded: _totalRecorded,
        recent: recent,
        byOutcome: byOutcome,
        lastProfileMismatch: lastProfileMismatch,
        lastDenied: lastDenied
      };
    },
    clearNativeControlAuditReport: function() {
      _auditLog.splice(0, _auditLog.length);
      _totalRecorded = 0;
      if (window.__TAURI__ && window.__TAURI__.core) {
        void _nativeInvoke('clear_native_audit_report', {}).catch(function() {});
      }
    },
    getSecretVaultStatus: function() {
      return _nativeInvoke('desktop_secret_vault_status', {});
    },
    setSecret: function(key, value) {
      return _nativeInvoke('desktop_secret_set', { key: key, value: value });
    },
    setSecrets: function(values) {
      return _nativeInvoke('desktop_secret_set_many', { values: values || {} });
    },
    deleteSecret: function(key) {
      return _nativeInvoke('desktop_secret_delete', { key: key });
    },
    runSelfTest: function() {
      return _nativeInvoke('desktop_self_test', {});
    },
    notify: function(title, body) {
      return _nativeInvoke('desktop_notify', { title: title, body: body });
    },
    getBackendStatus: function() {
      return _nativeInvoke('desktop_backend_status', {});
    },
    openExternal: function(url) {
      return _nativeInvoke('desktop_open_external', { url: String(url || '') });
    },
    getLocalCustodyStatus: function() {
      return _nativeInvoke('desktop_local_custody_status', {});
    }
  };

  // Packaged desktop resilience: ordinary frontend code uses relative /api/*
  // requests. If the loopback proxy is unavailable or returns a gateway error,
  // retry directly against the managed backend discovered from the Rust side.
  // This stays native-window-only because this initialization script is never
  // injected into browser companion sessions.
  var _nativeFetch = typeof window.fetch === 'function' ? window.fetch.bind(window) : null;
  var _cachedBackendBase = '';
  function _apiPathFromInput(input) {
    try {
      var raw = typeof input === 'string' ? input : (input && input.url ? String(input.url) : '');
      if (!raw) return '';
      if (raw.indexOf('/api/') === 0) return raw;
      var parsed = new URL(raw, window.location.href);
      if (parsed.origin === window.location.origin && parsed.pathname.indexOf('/api/') === 0) {
        return parsed.pathname + parsed.search;
      }
    } catch (_) {}
    return '';
  }
  function _directBackendFetch(path, input, init) {
    return (_cachedBackendBase
      ? Promise.resolve({ backend_base_url: _cachedBackendBase, healthy: true })
      : _nativeInvoke('desktop_backend_status', {}))
      .then(function(status) {
        var base = String(status && status.backend_base_url || '').replace(/\/$/, '');
        if (!base || base.indexOf('http://127.0.0.1:') !== 0) {
          throw new Error('native_backend_endpoint_unavailable');
        }
        _cachedBackendBase = base;
        var target = base + path;
        if (typeof Request !== 'undefined' && input instanceof Request) {
          var cloned = input.clone();
          return _nativeFetch(new Request(target, cloned), init);
        }
        return _nativeFetch(target, init);
      });
  }
  if (_nativeFetch) {
    window.fetch = function(input, init) {
      var path = _apiPathFromInput(input);
      if (!path) return _nativeFetch(input, init);
      var retryInput = input;
      if (typeof Request !== 'undefined' && input instanceof Request) {
        try { retryInput = input.clone(); } catch (_) {}
      }
      return _nativeFetch(input, init).then(function(response) {
        if (response && response.status !== 502 && response.status !== 503 && response.status !== 504) {
          return response;
        }
        return _directBackendFetch(path, retryInput, init).catch(function() { return response; });
      }).catch(function(originalError) {
        return _directBackendFetch(path, retryInput, init).catch(function() { throw originalError; });
      });
    };
  }

  // Tauri WebViews do not reliably implement browser target=_blank semantics.
  // Route all ordinary http(s) external links through the OS default browser.
  function _openExternalUrl(raw) {
    try {
      var parsed = new URL(String(raw || ''), window.location.href);
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return false;
      if (parsed.origin === window.location.origin) return false;
      void _nativeInvoke('desktop_open_external', { url: parsed.href }).catch(function(err) {
        console.warn('Harici bağlantı yerel tarayıcıda açılamadı', err);
        // Native komut geçici olarak kullanılamazsa WebView'i dış siteye
        // yönlendirmek yerine tarayıcının özgün yeni-pencere davranışını dene.
        try {
          if (_browserWindowOpen) _browserWindowOpen(parsed.href, '_blank', 'noopener,noreferrer');
        } catch (_) {}
      });
      return true;
    } catch (_) { return false; }
  }
  document.addEventListener('click', function(event) {
    var node = event.target;
    var anchor = node && node.closest ? node.closest('a[href]') : null;
    if (!anchor) return;
    if (_openExternalUrl(anchor.href)) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);
  var _browserWindowOpen = window.open ? window.open.bind(window) : null;
  window.open = function(url, target, features) {
    if ((!target || target === '_blank') && _openExternalUrl(url)) return null;
    return _browserWindowOpen ? _browserWindowOpen(url, target, features) : null;
  };
})();
"#;

#[derive(Clone, serde::Serialize)]
struct DesktopUpdateContext {
    mode: &'static str,
    platform: &'static str,
    is_packaged_build: bool,
    backend_mode: &'static str,
    owns_local_backend: bool,
    safe_mode: bool,
    updater_enabled: bool,
    recovered_previous_runtime: bool,
    runtime_integrity_enforced: bool,
}

#[tauri::command]
fn desktop_update_context(state: tauri::State<'_, DesktopAppState>) -> DesktopUpdateContext {
    let is_packaged_build = !cfg!(debug_assertions);
    DesktopUpdateContext {
        mode: if is_packaged_build { "packaged" } else { "dev" },
        platform: match std::env::consts::OS {
            "windows" => "windows",
            "macos" => "macos",
            "linux" => "linux",
            _ => "unknown",
        },
        is_packaged_build,
        backend_mode: if state.owns_managed_backend {
            "managed"
        } else {
            "external"
        },
        owns_local_backend: state.owns_managed_backend,
        safe_mode: state.effective_safe_mode,
        updater_enabled: option_env!("SHADOWBROKER_TAURI_UPDATER_ENABLED") == Some("1"),
        recovered_previous_runtime: state.recovered_previous_runtime,
        runtime_integrity_enforced: true,
    }
}

#[derive(Clone, serde::Serialize)]
struct DesktopBackendStatus {
    backend_base_url: String,
    healthy: bool,
    owns_local_backend: bool,
    safe_mode: bool,
}

#[tauri::command]
async fn desktop_backend_status(
    state: tauri::State<'_, DesktopAppState>,
) -> Result<DesktopBackendStatus, String> {
    let healthy = http_client::call_backend_json(
        &state.backend_base_url,
        state.admin_key.as_deref(),
        "/api/health",
        reqwest::Method::GET,
        None,
    )
    .await
    .is_ok();
    Ok(DesktopBackendStatus {
        backend_base_url: state.backend_base_url.clone(),
        healthy,
        owns_local_backend: state.owns_managed_backend,
        safe_mode: state.effective_safe_mode,
    })
}

#[tauri::command]
fn desktop_open_external(url: String) -> Result<(), String> {
    let parsed = Url::parse(url.trim()).map_err(|e| format!("external_url_invalid:{e}"))?;
    match parsed.scheme() {
        "http" | "https" => {}
        _ => return Err("external_url_scheme_not_allowed".to_string()),
    }
    open::that(parsed.as_str()).map_err(|e| format!("external_open_failed:{e}"))
}

#[tauri::command]
fn desktop_local_custody_status() -> local_custody::LocalCustodyStatus {
    local_custody::local_custody_status()
}


#[derive(serde::Serialize)]
struct DesktopRuntimeStateRecord<'a> {
    product: &'static str,
    version: &'static str,
    revision: &'static str,
    status: &'a str,
    updated_at_epoch: u64,
    backend_mode: &'a str,
    safe_mode: bool,
    recovered_previous_runtime: bool,
    runtime_integrity_enforced: bool,
    self_test_ok: Option<bool>,
}

fn write_desktop_runtime_state(
    data_dir: &std::path::Path,
    status: &str,
    owns_managed_backend: bool,
    safe_mode: bool,
    recovered_previous_runtime: bool,
    self_test_ok: Option<bool>,
) {
    let updated_at_epoch = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let record = DesktopRuntimeStateRecord {
        product: "Gokdogan Intelligence Desktop",
        version: env!("CARGO_PKG_VERSION"),
        revision: "R24",
        status,
        updated_at_epoch,
        backend_mode: if owns_managed_backend { "managed" } else { "external" },
        safe_mode,
        recovered_previous_runtime,
        runtime_integrity_enforced: true,
        self_test_ok,
    };
    if let Ok(rendered) = serde_json::to_string_pretty(&record) {
        let _ = std::fs::create_dir_all(data_dir);
        let _ = std::fs::write(
            data_dir.join("desktop-runtime-state.json"),
            format!("{rendered}\n"),
        );
    }
}

#[derive(Clone, serde::Serialize)]
struct DesktopSelfTestResult {
    ok: bool,
    backend_health: bool,
    intelligence_core: bool,
    database_integrity: bool,
    api_key_system: bool,
    backend_mode: &'static str,
    safe_mode: bool,
    recovered_previous_runtime: bool,
    runtime_integrity_enforced: bool,
    failures: Vec<String>,
}

async fn perform_desktop_self_test(
    backend_base_url: &str,
    admin_key: Option<&str>,
    owns_managed_backend: bool,
    safe_mode: bool,
    recovered_previous_runtime: bool,
) -> DesktopSelfTestResult {
    let mut failures = Vec::new();
    let backend_health = match http_client::call_backend_json(
        backend_base_url,
        admin_key,
        "/api/health",
        reqwest::Method::GET,
        None,
    )
    .await
    {
        Ok(_) => true,
        Err(error) => {
            failures.push(format!("backend_health:{error}"));
            false
        }
    };
    let intelligence_core = match http_client::call_backend_json(
        backend_base_url,
        admin_key,
        "/api/intelligence/status",
        reqwest::Method::GET,
        None,
    )
    .await
    {
        Ok(_) => true,
        Err(error) => {
            failures.push(format!("intelligence_core:{error}"));
            false
        }
    };
    let database_integrity = match http_client::call_backend_json(
        backend_base_url,
        admin_key,
        "/api/intelligence/integrity",
        reqwest::Method::GET,
        None,
    )
    .await
    {
        Ok(value) => value.get("ok").and_then(|v| v.as_bool()).unwrap_or(false),
        Err(error) => {
            failures.push(format!("database_integrity:{error}"));
            false
        }
    };
    if !database_integrity && !failures.iter().any(|x| x.starts_with("database_integrity:")) {
        failures.push("database_integrity:failed".to_string());
    }
    let api_key_system = match http_client::call_backend_json(
        backend_base_url,
        admin_key,
        "/api/settings/api-keys/diagnostics",
        reqwest::Method::GET,
        None,
    )
    .await
    {
        Ok(value) => value.get("ok").and_then(|v| v.as_bool()).unwrap_or(false),
        Err(error) => {
            failures.push(format!("api_key_system:{error}"));
            false
        }
    };
    if !api_key_system && !failures.iter().any(|x| x.starts_with("api_key_system:")) {
        failures.push("api_key_system:local_store_or_runtime_unavailable".to_string());
    }
    DesktopSelfTestResult {
        ok: backend_health && intelligence_core && database_integrity && api_key_system,
        backend_health,
        intelligence_core,
        database_integrity,
        api_key_system,
        backend_mode: if owns_managed_backend { "managed" } else { "external" },
        safe_mode,
        recovered_previous_runtime,
        runtime_integrity_enforced: true,
        failures,
    }
}

#[tauri::command]
async fn desktop_self_test(
    state: tauri::State<'_, DesktopAppState>,
) -> Result<DesktopSelfTestResult, String> {
    Ok(perform_desktop_self_test(
        &state.backend_base_url,
        state.admin_key.as_deref(),
        state.owns_managed_backend,
        state.effective_safe_mode,
        state.recovered_previous_runtime,
    )
    .await)
}

fn sanitize_notification_text(title: &str, body: &str) -> (String, String) {
    let candidate_title: String = title.chars().take(120).collect();
    let safe_title = if candidate_title.trim().is_empty() {
        "Gokdogan".to_string()
    } else {
        candidate_title.trim().to_string()
    };
    let safe_body: String = body.chars().take(800).collect::<String>().trim().to_string();
    (safe_title, safe_body)
}

#[tauri::command]
fn desktop_notify(app: tauri::AppHandle, title: String, body: String) -> Result<(), String> {
    use tauri_plugin_notification::NotificationExt;
    let (safe_title, safe_body) = sanitize_notification_text(&title, &body);
    app.notification()
        .builder()
        .title(safe_title)
        .body(safe_body)
        .show()
        .map_err(|error| format!("desktop_notification_failed:{error}"))?;
    Ok(())
}

#[cfg(test)]
mod r7_desktop_tests {
    use super::sanitize_notification_text;

    #[test]
    fn notification_text_is_bounded_and_trimmed() {
        let title = format!("  {}  ", "T".repeat(200));
        let body = format!("  {}  ", "B".repeat(1000));
        let (safe_title, safe_body) = sanitize_notification_text(&title, &body);
        assert!(safe_title.chars().count() <= 120);
        assert!(safe_body.chars().count() <= 800);
        assert_eq!(safe_title.trim(), safe_title);
        assert_eq!(safe_body.trim(), safe_body);
    }

    #[test]
    fn empty_notification_title_uses_product_name() {
        let (title, body) = sanitize_notification_text("   ", "  hello  ");
        assert_eq!(title, "Gokdogan");
        assert_eq!(body, "hello");
    }
}


fn main() {
    let command_self_test = std::env::args().any(|arg| arg.eq_ignore_ascii_case("--self-test"));
    let explicit_backend_url = std::env::var("SHADOWBROKER_BACKEND_URL").ok();
    let admin_key = std::env::var("SHADOWBROKER_ADMIN_KEY").ok();

    // Frontend URL detection:
    // - If SHADOWBROKER_FRONTEND_URL is explicitly set → honor it (dev mode
    //   or custom setup; the built-in loopback app server is skipped)
    // - Else → default to http://127.0.0.1:3000 for dev; in packaged mode
    //   we'll start the loopback app server in setup below and override this.
    let frontend_url_explicit = std::env::var("SHADOWBROKER_FRONTEND_URL").ok();
    let default_frontend_url = frontend_url_explicit
        .clone()
        .unwrap_or_else(|| "http://127.0.0.1:3000".to_string());

    tauri::Builder::default()
        // Single-instance must be registered before the other plugins so a
        // second launch cannot race the managed backend or loopback server.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(NativeGateCryptoState(std::sync::Mutex::new(
            gate_crypto::GateCryptoRuntime::default(),
        )))
        .manage(companion::new_companion_state(
            default_frontend_url.clone(),
            frontend_url_explicit.is_some(),
        ))
        .invoke_handler(tauri::generate_handler![
            desktop_update_context,
            desktop_backend_status,
            desktop_open_external,
            desktop_local_custody_status,
            desktop_self_test,
            desktop_notify,
            desktop_secret_vault_status,
            desktop_secret_set,
            desktop_secret_set_many,
            desktop_secret_delete,
            invoke_local_control,
            get_native_audit_report,
            clear_native_audit_report,
            companion_status,
            companion_enable,
            companion_disable,
            companion_open_browser,
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                tray::handle_close_requested(window, api);
            }
        })
        .setup(move |app| {
            // ---- Packaged startup splash ----
            // Show immediate feedback while the bundled Python backend and
            // loopback app server are starting. Dev mode keeps the normal
            // browser/dev-server workflow without a splash.
            let startup_splash = if !cfg!(debug_assertions) {
                WebviewWindowBuilder::new(
                    app,
                    "startup-splash",
                    WebviewUrl::App("desktop-splash.html".into()),
                )
                .title("Gokdogan Intelligence Desktop")
                .inner_size(520.0, 340.0)
                .resizable(false)
                .decorations(false)
                .build()
                .ok()
            } else {
                None
            };

            // ---- Tray setup (existing behavior, unchanged) ----
            match tray::setup_tray(app.handle()) {
                Ok(tray_icon) => {
                    app.manage(TrayHandle(tray_icon));
                }
                Err(e) => {
                    eprintln!(
                        "tray setup failed (app will run without tray, close will quit normally): {e}"
                    );
                }
            }

            let resource_dir = app.path().resource_dir().ok();
            let app_local_data_dir = app
                .path()
                .app_local_data_dir()
                .or_else(|_| app.path().app_data_dir())
                .ok();

            if let Some(cache_root) = app_local_data_dir
                .as_ref()
                .map(|dir| dir.join("gate-state-cache"))
            {
                if let Ok(mut runtime) = app
                    .state::<NativeGateCryptoState>()
                    .0
                    .lock()
                {
                    runtime.set_cache_root(cache_root);
                }
            }

            // ---- Resolve bundled frontend + backend assets (packaged mode indicators) ----
            //
            // Packaged desktop now owns a bundled local backend runtime as
            // well as the static frontend export. In packaged mode, when the
            // user has NOT explicitly set SHADOWBROKER_BACKEND_URL, the app:
            //   1. installs/refreshes the bundled backend into app-local
            //      writable storage
            //   2. launches it as a managed child process on loopback
            //   3. points the loopback app server and native bridge at that
            //      managed backend
            //
            // Dev/custom setups can still override the backend explicitly.
            let www_root: Option<std::path::PathBuf> = resource_dir
                .as_ref()
                .map(|d| d.join("companion-www"))
                .filter(|p| p.join("index.html").exists());
            let bundled_backend_root = resource_dir
                .as_ref()
                .and_then(|d| backend_runtime::bundled_backend_root(d));

            if let Some(root) = www_root.as_ref() {
                let companion_state_lock =
                    app.state::<companion::SharedCompanionState>();
                if let Ok(mut cs) = companion_state_lock.lock() {
                    cs.set_www_root(root.clone());
                };
            }

            let audit_ring = policy::new_shared_audit_ring(100);
            let packaged_frontend_present = www_root.is_some();
            let requested_safe_mode = backend_runtime::safe_mode_requested();
            let (resolved_backend_base_url, owns_managed_backend, resolved_admin_key, effective_safe_mode, recovered_previous_runtime) =
                if let Some(url) = explicit_backend_url.as_ref() {
                    (url.clone(), false, admin_key.clone(), requested_safe_mode, false)
                } else if let Some(bundled_root) = bundled_backend_root {
                    let app_local_data_dir = app_local_data_dir
                        .clone()
                        .ok_or_else(|| "managed_backend_app_data_dir_failed:no_app_data_dir".to_string())?;
                    let vault_secrets = secret_vault::load_all_for_backend(app.handle()).unwrap_or_default();
                    let primary = tauri::async_runtime::block_on(
                        backend_runtime::ensure_and_start_managed_backend(
                            bundled_root.clone(),
                            app_local_data_dir.clone(),
                            admin_key.clone(),
                            vault_secrets.clone(),
                            requested_safe_mode,
                        ),
                    );
                    let (handle, recovered_safe_mode, recovered_previous_runtime) = match primary {
                        Ok(handle) => (handle, requested_safe_mode, false),
                        Err(primary_error) if !requested_safe_mode => {
                            eprintln!(
                                "managed backend normal startup failed ({primary_error}); retrying once in automatic Safe Mode"
                            );
                            match tauri::async_runtime::block_on(
                                backend_runtime::ensure_and_start_managed_backend(
                                    bundled_root.clone(),
                                    app_local_data_dir.clone(),
                                    admin_key.clone(),
                                    vault_secrets.clone(),
                                    true,
                                ),
                            ) {
                                Ok(handle) => (handle, true, false),
                                Err(safe_error) => {
                                    eprintln!(
                                        "managed backend Safe Mode startup failed ({safe_error}); attempting last-known-good runtime rollback"
                                    );
                                    match tauri::async_runtime::block_on(
                                        backend_runtime::restore_previous_and_start_managed_backend(
                                            app_local_data_dir.clone(),
                                            admin_key.clone(),
                                            vault_secrets.clone(),
                                        ),
                                    ) {
                                        Ok(handle) => (handle, true, true),
                                        Err(rollback_error) => {
                                            return Err(format!(
                                                "Gokdogan başlatılamıyor: the bundled local backend failed in normal and Safe Mode, and the previous runtime could not be recovered.\n\n\
                                                 Normal startup: {primary_error}\n\
                                                 Safe Mode retry: {safe_error}\n\
                                                 Previous runtime rollback: {rollback_error}"
                                            ).into());
                                        }
                                    }
                                }
                            }
                        }
                        Err(safe_error) => {
                            eprintln!(
                                "managed backend explicit Safe Mode startup failed ({safe_error}); attempting last-known-good runtime rollback"
                            );
                            match tauri::async_runtime::block_on(
                                backend_runtime::restore_previous_and_start_managed_backend(
                                    app_local_data_dir.clone(),
                                    admin_key.clone(),
                                    vault_secrets.clone(),
                                ),
                            ) {
                                Ok(handle) => (handle, true, true),
                                Err(rollback_error) => {
                                    return Err(format!(
                                        "Gokdogan başlatılamıyor: Safe Mode and previous runtime recovery both failed.\n\n\
                                         Safe Mode startup: {safe_error}\n\
                                         Previous runtime rollback: {rollback_error}"
                                    ).into());
                                }
                            }
                        }
                    };
                    let base_url = handle.base_url().to_string();
                    let resolved_admin_key = handle.admin_key().map(str::to_string);
                    app.manage(ManagedBackendState(std::sync::Mutex::new(handle)));
                    (base_url, true, resolved_admin_key, recovered_safe_mode, recovered_previous_runtime)
                } else if packaged_frontend_present {
                    return Err(
                        "Gokdogan başlatılamıyor: this packaged build is missing the bundled backend runtime."
                            .into(),
                    );
                } else {
                    ("http://127.0.0.1:8000".to_string(), false, admin_key.clone(), requested_safe_mode, false)
                };

            app.manage(DesktopAppState {
                backend_base_url: resolved_backend_base_url.clone(),
                admin_key: resolved_admin_key.clone(),
                audit_ring,
                owns_managed_backend,
                effective_safe_mode,
                recovered_previous_runtime,
            });
            if let Some(data_dir) = app_local_data_dir.as_ref() {
                write_desktop_runtime_state(
                    data_dir,
                    "backend_ready",
                    owns_managed_backend,
                    effective_safe_mode,
                    recovered_previous_runtime,
                    None,
                );
            }

            if command_self_test {
                let report = tauri::async_runtime::block_on(perform_desktop_self_test(
                    &resolved_backend_base_url,
                    resolved_admin_key.as_deref(),
                    owns_managed_backend,
                    effective_safe_mode,
                    recovered_previous_runtime,
                ));
                if let Some(data_dir) = app_local_data_dir.as_ref() {
                    let report_path = data_dir.join("desktop-self-test.json");
                    if let Ok(rendered) = serde_json::to_string_pretty(&report) {
                        let _ = std::fs::write(&report_path, format!("{rendered}\n"));
                    }
                    write_desktop_runtime_state(
                        data_dir,
                        if report.ok { "self_test_passed" } else { "self_test_failed" },
                        owns_managed_backend,
                        effective_safe_mode,
                        recovered_previous_runtime,
                        Some(report.ok),
                    );
                }
                if !report.ok {
                    return Err(format!(
                        "Gokdogan masaüstü öz sınaması başarısız: {}",
                        report.failures.join(", ")
                    ).into());
                }
                if let Some(splash) = startup_splash {
                    let _ = splash.close();
                }
                app.handle().exit(0);
                return Ok(());
            }

            // ---- Start app-level loopback server (packaged mode only) ----
            //
            // The loopback server has two jobs post-P6D-R:
            //   1. Act as the HTTP origin for the packaged Tauri main window
            //      so ordinary non-privileged /api/* fetches have a real,
            //      same-origin path to the backend.
            //   2. Serve the optional browser companion opener.
            //
            // It is NOT started when the user explicitly overrides the
            // frontend URL — in that case the user owns the frontend
            // environment (dev server, remote mirror, etc.).
            let packaged_server_url: Option<String> = if www_root.is_some()
                && frontend_url_explicit.is_none()
            {
                let root = www_root.clone().unwrap();
                let backend = resolved_backend_base_url.clone();
                // Synchronously start the server in the Tauri async runtime
                // so we have the bound URL before creating the webview. The
                // server task is spawned inside and continues running for
                // the app's lifetime (owned by AppServerHandle below).
                match tauri::async_runtime::block_on(async move {
                    companion_server::start_companion_server(root, backend).await
                }) {
                    Ok(server) => {
                        let url_string = server.url();
                        // Defense in depth: refuse anything that isn't loopback.
                        if !companion::is_loopback_origin(&url_string) {
                            eprintln!(
                                "loopback app server bound to non-loopback origin '{url_string}' — refusing to use it"
                            );
                            None
                        } else {
                            // Register the URL with companion state so the
                            // browser companion opener hands out the same URL.
                            {
                                let companion_state_lock = app
                                    .state::<companion::SharedCompanionState>();
                                if let Ok(mut cs) = companion_state_lock.lock() {
                                    cs.set_app_server_url(url_string.clone());
                                };
                            }
                            // Keep the handle alive for the app's lifetime.
                            app.manage(AppServerHandle(std::sync::Mutex::new(server)));
                            Some(url_string)
                        }
                    }
                    Err(e) => {
                        // In packaged mode the loopback server is required —
                        // without it, the webview has no same-origin /api/*
                        // path and the app is non-functional. Fail honestly
                        // rather than presenting a silently broken UI.
                        return Err(format!(
                            "Gokdogan başlatılamıyor: the packaged loopback server failed to bind.\n\n\
                             This usually means another process is using all available loopback ports, \
                             or a firewall is blocking localhost listeners.\n\n\
                             Technical detail: {e}"
                        ).into());
                    }
                }
            } else {
                None
            };

            // ---- Create the main window ----
            //
            // We create the main window programmatically (rather than via
            // tauri.conf.json's app.windows) so we can:
            //   (a) Point it at the loopback app server URL in packaged mode
            //       — giving the webview same-origin /api/* access.
            //   (b) Attach an initialization_script that runs BEFORE any page
            //       JavaScript on every page load (including full reloads),
            //       so the __SHADOWBROKER_DESKTOP__ native control bridge is
            //       always present in the native window but never leaks into
            //       browser companion sessions.
            //
            // URL resolution order:
            //   1. Packaged mode with loopback app server → server URL
            //   2. Explicit SHADOWBROKER_FRONTEND_URL → that URL
            //      (packaged + explicit override, or custom dev setup)
            //   3. Fall through to WebviewUrl::default() → resolves to
            //      build.devUrl (dev) or build.frontendDist (release) from
            //      tauri.conf.json
            fn parse_or_default(url: &str, label: &str) -> WebviewUrl {
                match Url::parse(url) {
                    Ok(parsed) => WebviewUrl::External(parsed),
                    Err(e) => {
                        eprintln!(
                            "failed to parse {label} URL '{url}' ({e}) — falling back to default webview URL"
                        );
                        WebviewUrl::default()
                    }
                }
            }
            let main_url: WebviewUrl =
                if let Some(url) = packaged_server_url.as_deref() {
                    parse_or_default(url, "loopback server")
                } else if let Some(url) = frontend_url_explicit.as_deref() {
                    parse_or_default(url, "explicit frontend override")
                } else {
                    WebviewUrl::default()
                };

            WebviewWindowBuilder::new(app, "main", main_url)
                .title("Gokdogan Intelligence Desktop")
                .inner_size(1600.0, 1000.0)
                .min_inner_size(1100.0, 700.0)
                .resizable(true)
                .initialization_script(DESKTOP_INIT_SCRIPT)
                .build()?;

            if let Some(splash) = startup_splash {
                let _ = splash.close();
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Gokdogan Tauri kabugu olusturulamadi")
        .run(|app, event| {
            // macOS dock-icon reopen: restore/focus the main window when
            // the user clicks the dock icon while the app is hidden in the
            // background. On Windows/Linux this event is not emitted, so
            // the existing tray restore path is the only restore mechanism.
            #[cfg(target_os = "macos")]
            if let tauri::RunEvent::Reopen { .. } = event {
                tray::show_main_window(app);
            }
            // All other events use default handling.
            let _ = (app, event);
        });
}
