#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const crypto = require('node:crypto');

const scriptDir = __dirname;
const tauriDir = path.resolve(scriptDir, '..');
const repoRoot = path.resolve(tauriDir, '..', '..');
const backendDir = path.join(repoRoot, 'backend');
const privacyCoreDir = path.join(repoRoot, 'privacy-core');
const requestedOutputDir = String(process.env.SHADOWBROKER_BACKEND_RUNTIME_OUTPUT || '').trim();
const outputDir = requestedOutputDir
  ? path.resolve(requestedOutputDir)
  : path.join(tauriDir, 'src-tauri', 'backend-runtime');
const outputRoot = path.parse(outputDir).root;
const outputSegments = path
  .relative(outputRoot, outputDir)
  .split(path.sep)
  .filter(Boolean);
if (
  path.basename(outputDir).toLowerCase() !== 'backend-runtime' ||
  outputDir === outputRoot ||
  outputSegments.length < 2
) {
  throw new Error(
    `Unsafe SHADOWBROKER_BACKEND_RUNTIME_OUTPUT; the resolved non-root path must end in backend-runtime: ${outputDir}`,
  );
}
const venvMarkerPath = path.join(backendDir, '.venv-dir');
const portablePythonDir = path.join(backendDir, '.desktop-python');
const portableBrowsersDir = path.join(backendDir, '.desktop-browsers');
const releaseAttestationPath = path.join(backendDir, 'data', 'release_attestation.json');
const stagedReleaseAttestationPath = path.join(outputDir, 'data', 'release_attestation.json');
const runtimeIntegrityManifestPath = path.join(outputDir, '.runtime-integrity.json');

// Only deterministic/public reference assets are staged from backend/data.
// Runtime secrets, databases, operator identity, person-targeted watchlists and
// sensitive/military curated tracking lists are deliberately excluded.
const runtimeSeedDataAllowlist = Object.freeze([
  'aisstream_spki_pins.json',
  'carrier_seed.json',
  'datacenters.json',
  'datacenters_geocoded.json',
  'kiwisdr_directory.json',
  'power_plants.json',
  'release_digests.json',
  'tor_bundle_digests.json',
  path.join('drishx', 'rf_model.pickle'),
]);

const excludedNames = new Set([
  '.env',
  '.pytest_cache',
  '.ruff_cache',
  '__pycache__',
  'backend.egg-info',
  'build',
  'data',
  'tests',
  'timemachine',
  'node_modules',
  'venv',
  '.venv',
  '.desktop-python',
  '.desktop-browsers',
]);

const excludedFiles = new Set([
  '.env.example',
  'ais_cache.json',
  'carrier_cache.json',
  'cctv.db',
  'dm_token_pepper.key',
  'pytest.ini',
]);

function selectedVenvDir() {
  try {
    const persisted = fs.readFileSync(venvMarkerPath, 'utf8').trim();
    if (persisted) return persisted;
  } catch {}
  return 'venv';
}

function pythonExecutableIn(root) {
  return process.platform === 'win32'
    ? path.join(root, 'python.exe')
    : path.join(root, 'bin', 'python3');
}

function portablePythonExecutable() {
  return pythonExecutableIn(portablePythonDir);
}

function legacyVenvExecutable() {
  const root = path.join(backendDir, selectedVenvDir());
  return process.platform === 'win32'
    ? path.join(root, 'Scripts', 'python.exe')
    : path.join(root, 'bin', 'python3');
}

function shouldCopy(srcPath) {
  const relativePath = path.relative(backendDir, srcPath);
  if (!relativePath) return true;

  const parts = relativePath.split(path.sep);
  return parts.every((part, index) => {
    const isLeaf = index === parts.length - 1;
    if (excludedNames.has(part)) return false;
    if (isLeaf && excludedFiles.has(part)) return false;
    if (/^test_.*\.py$/i.test(part)) return false;
    return true;
  });
}

function ensureRuntimePrereqs() {
  if (!fs.existsSync(path.join(backendDir, 'main.py'))) {
    throw new Error(`Missing backend/main.py at ${backendDir}`);
  }
  const hasPortablePython = fs.existsSync(portablePythonExecutable());
  const hasLegacyVenv = fs.existsSync(legacyVenvExecutable());
  if (!hasPortablePython && !hasLegacyVenv) {
    throw new Error(
      'Missing backend Python runtime. For a self-contained desktop build, create backend/.desktop-python ' +
      '(the Windows one-click builder does this automatically). A legacy backend venv is accepted only as a fallback.',
    );
  }
  if (!fs.existsSync(path.join(backendDir, 'node_modules', 'ws'))) {
    throw new Error(
      `Missing backend/node_modules/ws at ${path.join(backendDir, 'node_modules', 'ws')}. ` +
      'Run npm ci in backend before packaging the desktop app.',
    );
  }
}

function privacyCoreArtifactName() {
  if (process.platform === 'win32') return 'privacy_core.dll';
  if (process.platform === 'darwin') return 'libprivacy_core.dylib';
  return 'libprivacy_core.so';
}

function privacyCoreArtifactPath() {
  return path.join(privacyCoreDir, 'target', 'release', privacyCoreArtifactName());
}

function ensurePrivacyCoreArtifact() {
  const artifact = privacyCoreArtifactPath();
  if (fs.existsSync(artifact)) return artifact;

  console.log('privacy-core release library missing; building it for desktop packaging...');
  const result = spawnSync(
    'cargo',
    ['build', '--release', '--locked', '--manifest-path', path.join(privacyCoreDir, 'Cargo.toml')],
    { cwd: repoRoot, env: process.env, stdio: 'inherit' },
  );
  if (result.error || result.status !== 0) {
    throw new Error(
      'Failed to build privacy-core release library. Install Rust/Cargo and rerun the desktop build.',
    );
  }
  if (!fs.existsSync(artifact)) {
    throw new Error(`privacy-core build completed but artifact is missing: ${artifact}`);
  }
  return artifact;
}

function stageBackendRuntime() {
  fs.rmSync(outputDir, { recursive: true, force: true });
  fs.cpSync(backendDir, outputDir, { recursive: true, filter: shouldCopy });
  stagePythonRuntime();
  stageNodeRuntime();
  stageNodeModules();
  stagePlaywrightBrowsers();
  stagePrivacyCoreArtifact();
  stageRuntimeSeedData();
  stageReleaseAttestation();
  stageStartScripts();
}


function countTreeFilesAndBytes(root) {
  let files = 0;
  let bytes = 0;
  if (!fs.existsSync(root)) return { files, bytes };
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const full = path.join(root, entry.name);
    if (entry.isDirectory()) {
      const nested = countTreeFilesAndBytes(full);
      files += nested.files;
      bytes += nested.bytes;
    } else if (entry.isFile()) {
      files += 1;
      bytes += fs.statSync(full).size;
    }
  }
  return { files, bytes };
}

function prunePythonBytecodeCaches(pythonRuntimeRoot) {
  let removedDirs = 0;
  let removedFiles = 0;
  let removedBytes = 0;

  function prune(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      const lower = entry.name.toLowerCase();
      if (entry.isDirectory()) {
        if (lower === '__pycache__') {
          const measured = countTreeFilesAndBytes(full);
          fs.rmSync(full, { recursive: true, force: true });
          removedDirs += 1;
          removedFiles += measured.files;
          removedBytes += measured.bytes;
          continue;
        }
        prune(full);
        continue;
      }
      if (entry.isFile() && (lower.endsWith('.pyc') || lower.endsWith('.pyo'))) {
        const size = fs.statSync(full).size;
        fs.rmSync(full, { force: true });
        removedFiles += 1;
        removedBytes += size;
      }
    }
  }

  prune(pythonRuntimeRoot);
  console.log(
    `Pruned Python bytecode caches: dirs=${removedDirs} files=${removedFiles} bytes=${removedBytes}`,
  );
}

function prunePythonRuntimeTestArtifacts(pythonRuntimeRoot) {
  const sitePackageRoots = [];
  function discover(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const full = path.join(dir, entry.name);
      if (entry.name.toLowerCase() === 'site-packages') {
        sitePackageRoots.push(full);
        continue;
      }
      discover(full);
    }
  }
  discover(pythonRuntimeRoot);

  let removedDirs = 0;
  let removedFiles = 0;
  let removedBytes = 0;
  function prune(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const full = path.join(dir, entry.name);
      const lower = entry.name.toLowerCase();
      if (lower === 'tests' || lower === 'test') {
        const measured = countTreeFilesAndBytes(full);
        fs.rmSync(full, { recursive: true, force: true });
        removedDirs += 1;
        removedFiles += measured.files;
        removedBytes += measured.bytes;
        continue;
      }
      prune(full);
    }
  }
  for (const sitePackages of sitePackageRoots) prune(sitePackages);
  console.log(
    `Pruned Python package test-only artifacts: dirs=${removedDirs} files=${removedFiles} bytes=${removedBytes}`,
  );
}

function stagePythonRuntime() {
  const portableExe = portablePythonExecutable();
  if (fs.existsSync(portableExe)) {
    const dest = path.join(outputDir, 'python-runtime');
    console.log(`Staging relocatable desktop Python runtime from ${portablePythonDir}`);
    fs.cpSync(portablePythonDir, dest, { recursive: true });
    prunePythonRuntimeTestArtifacts(dest);
    prunePythonBytecodeCaches(dest);
    return;
  }

  // Backwards-compatible fallback. This is suitable for development builds,
  // but Windows release builders should use .desktop-python so the installed
  // application does not depend on a machine-wide Python installation.
  const venvName = selectedVenvDir();
  const venvRoot = path.join(backendDir, venvName);
  const dest = path.join(outputDir, venvName);
  console.warn(
    `Portable Python runtime not found; staging legacy venv '${venvName}'. ` +
    'Use WINDOWS-DESKTOP-ONE-CLICK.ps1 for a self-contained Windows package.',
  );
  fs.cpSync(venvRoot, dest, { recursive: true });
  prunePythonRuntimeTestArtifacts(dest);
  prunePythonBytecodeCaches(dest);
  fs.writeFileSync(path.join(outputDir, '.venv-dir'), `${venvName}\n`, 'utf8');
}

function stageNodeRuntime() {
  const destDir = path.join(outputDir, 'node-runtime');
  fs.mkdirSync(destDir, { recursive: true });
  const source = process.execPath;
  const name = process.platform === 'win32' ? 'node.exe' : 'node';
  const dest = path.join(destDir, name);
  fs.copyFileSync(source, dest);
  if (process.platform !== 'win32') {
    try { fs.chmodSync(dest, 0o755); } catch {}
  }
}

function stageNodeModules() {
  const src = path.join(backendDir, 'node_modules', 'ws');
  const dst = path.join(outputDir, 'node_modules', 'ws');
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.cpSync(src, dst, { recursive: true });
}

function stagePlaywrightBrowsers() {
  if (!fs.existsSync(portableBrowsersDir)) {
    console.warn(
      'No backend/.desktop-browsers directory found. Browser-backed data sources will be unavailable ' +
      'until Playwright Chromium is installed. The Windows one-click builder includes it by default.',
    );
    return;
  }
  const dst = path.join(outputDir, 'playwright-browsers');
  console.log('Staging Playwright browser runtime...');
  fs.cpSync(portableBrowsersDir, dst, { recursive: true });
}

function stageStartScripts() {
  const scripts = ['start.bat', 'start.sh'];
  for (const name of scripts) {
    const src = path.join(repoRoot, name);
    if (!fs.existsSync(src)) {
      console.warn(`backend-runtime staged without ${name} (not at repo root)`);
      continue;
    }
    const dst = path.join(outputDir, name);
    fs.copyFileSync(src, dst);
    if (name.endsWith('.sh') && process.platform !== 'win32') {
      try { fs.chmodSync(dst, 0o755); } catch {}
    }
  }
}

function stagePrivacyCoreArtifact() {
  const artifact = ensurePrivacyCoreArtifact();
  const stagedPath = path.join(outputDir, path.basename(artifact));
  fs.copyFileSync(artifact, stagedPath);
}

function stageRuntimeSeedData() {
  const sourceDataDir = path.join(backendDir, 'data');
  const targetDataDir = path.join(outputDir, 'data');
  fs.mkdirSync(targetDataDir, { recursive: true });
  let copied = 0;
  for (const relativePath of runtimeSeedDataAllowlist) {
    const source = path.join(sourceDataDir, relativePath);
    if (!fs.existsSync(source) || !fs.statSync(source).isFile()) continue;
    const target = path.join(targetDataDir, relativePath);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(source, target);
    copied += 1;
  }
  console.log(`backend-runtime public seed data staged: ${copied}/${runtimeSeedDataAllowlist.length}`);
}

function stageReleaseAttestation() {
  if (!fs.existsSync(releaseAttestationPath)) {
    console.warn(`backend-runtime staged without release attestation: ${releaseAttestationPath}`);
    return;
  }
  fs.mkdirSync(path.dirname(stagedReleaseAttestationPath), { recursive: true });
  fs.copyFileSync(releaseAttestationPath, stagedReleaseAttestationPath);
}

function writeBundleVersion() {
  const versionPath = path.join(outputDir, '.bundle-version');
  const pkg = JSON.parse(fs.readFileSync(path.join(repoRoot, 'desktop-shell', 'package.json'), 'utf8'));
  fs.writeFileSync(versionPath, `${pkg.version || '0.0.0'}\n`, 'utf8');
}


function sha256File(filePath) {
  const hash = crypto.createHash('sha256');
  hash.update(fs.readFileSync(filePath));
  return hash.digest('hex');
}

function collectRuntimeFiles(root, relative = '') {
  const entries = [];
  const directory = path.join(root, relative);
  for (const entry of fs.readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const rel = relative ? path.join(relative, entry.name) : entry.name;
    if (rel === path.basename(runtimeIntegrityManifestPath)) continue;
    const relParts = rel.split(path.sep);
    const lowerName = entry.name.toLowerCase();
    if (relParts.some((part) => part.toLowerCase() === '__pycache__')) continue;
    if (lowerName.endsWith('.pyc') || lowerName.endsWith('.pyo')) continue;
    const full = path.join(root, rel);
    if (entry.isDirectory()) {
      entries.push(...collectRuntimeFiles(root, rel));
    } else if (entry.isFile()) {
      const stat = fs.statSync(full);
      entries.push({
        path: rel.split(path.sep).join('/'),
        size: stat.size,
        sha256: sha256File(full),
      });
    }
  }
  return entries;
}

function writeRuntimeIntegrityManifest() {
  const files = collectRuntimeFiles(outputDir);
  const manifest = {
    manifest_version: 1,
    algorithm: 'sha256',
    bundle_version: fs.readFileSync(path.join(outputDir, '.bundle-version'), 'utf8').trim(),
    generated_at: new Date().toISOString(),
    file_count: files.length,
    files,
  };
  fs.writeFileSync(runtimeIntegrityManifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
  console.log(`backend-runtime integrity manifest written: ${files.length} files`);
}

function fileCount(root) {
  let count = 0;
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const fullPath = path.join(root, entry.name);
    if (entry.isDirectory()) count += fileCount(fullPath);
    else count += 1;
  }
  return count;
}

ensureRuntimePrereqs();
stageBackendRuntime();
writeBundleVersion();
writeRuntimeIntegrityManifest();
console.log(`backend-runtime staged: ${fileCount(outputDir)} files`);
