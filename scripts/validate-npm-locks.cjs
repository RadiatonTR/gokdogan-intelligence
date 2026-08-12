#!/usr/bin/env node
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const root = path.resolve(__dirname, '..');
const specs = [
  ['backend', path.join(root, 'backend', 'package.json'), path.join(root, 'backend', 'package-lock.json')],
  ['frontend', path.join(root, 'frontend', 'package.json'), path.join(root, 'frontend', 'package-lock.json')],
  ['desktop-shell', path.join(root, 'desktop-shell', 'package.json'), path.join(root, 'desktop-shell', 'package-lock.json')],
];
const failures = [];
const sourcePreRefresh = process.argv.includes('--source-pre-refresh');
const resolvedIntegrity = new Map();
function fail(msg) { failures.push(msg); }
function readJson(p) { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { fail(`json:${path.relative(root,p)}:${e.message}`); return {}; } }
function validateSri(sri, where) {
  if (typeof sri !== 'string' || !sri.includes('-')) { fail(`integrity_missing:${where}`); return; }
  const [alg, b64] = sri.split('-', 2);
  if (!['sha512','sha384','sha256','sha1'].includes(alg)) { fail(`integrity_alg:${where}:${alg}`); return; }
  try {
    const buf = Buffer.from(b64, 'base64');
    const expected = {sha512:64, sha384:48, sha256:32, sha1:20}[alg];
    if (buf.length !== expected) fail(`integrity_length:${where}:${buf.length}`);
  } catch (e) { fail(`integrity_base64:${where}:${e.message}`); }
}
for (const [name, pkgPath, lockPath] of specs) {
  const pkg = readJson(pkgPath); const lock = readJson(lockPath);
  if (lock.lockfileVersion !== 3) fail(`lockfile_version:${name}:${lock.lockfileVersion}`);
  if (pkg.version !== lock.version || pkg.version !== lock.packages?.['']?.version) fail(`root_version_mismatch:${name}`);
  for (const [key, meta] of Object.entries(lock.packages || {})) {
    if (!key || !meta || typeof meta !== 'object') continue;
    const where = `${name}:${key}`;
    if (meta.resolved && !String(meta.resolved).startsWith('https://registry.npmjs.org/')) {
      // Local/file/git dependencies are allowed; only reject insecure registry URLs.
      if (String(meta.resolved).startsWith('http://registry.npmjs.org/')) fail(`insecure_registry:${where}`);
    }
    if (meta.integrity) validateSri(meta.integrity, where);
    if (meta.resolved && meta.integrity) {
      const prev = resolvedIntegrity.get(meta.resolved);
      if (prev && prev !== meta.integrity) fail(`resolved_integrity_conflict:${meta.resolved}`);
      else resolvedIntegrity.set(meta.resolved, meta.integrity);
    }
  }
}

// R18 integrity regression contracts: earlier desktop packages shipped one-character-corrupted SRIs for
// tr46@6.0.0. Keep this exact upstream tarball SRI pinned so npm ci cannot regress
// to the deterministic EINTEGRITY failure again.
const frontendLock = readJson(path.join(root, 'frontend', 'package-lock.json'));
const tr46 = frontendLock.packages?.['node_modules/tr46'];
const expectedTr46 = 'sha512-bLVMLPtstlZ4iMQHpFHTR7GAGj2jxi8Dg0s2h2MafAE4uSWF98FC/3MomU51iQAMf8/qDUbKWf5GxuvvVcXEhw==';
if (!tr46 || tr46.version !== '6.0.0' || tr46.integrity !== expectedTr46) fail('tr46_6_0_0_integrity_regression');
const semver631 = frontendLock.packages?.['node_modules/semver'];
const expectedSemver631 = 'sha512-BR7VvDCVHO+q2xBEWskxS6DJE1qRnb7DxzUrogb71CWoSficBxYsiAGd+Kl0mmq/MprG9yArRkyrQxTO6XjMzA==';
if (!semver631 || semver631.version !== '6.3.1' || semver631.integrity !== expectedSemver631) fail('semver_6_3_1_integrity_regression');

// R18 production dependency security baseline. These exact patch versions clear
// the four high-severity packages reported by the Windows production audit.
if (!sourcePreRefresh) {
  for (const [pkgName, expectedVersion] of Object.entries({next:'16.2.11', nanoid:'3.3.17', postcss:'8.5.24', sharp:'0.35.3'})) {
    const meta = frontendLock.packages?.[`node_modules/${pkgName}`];
    if (!meta || meta.version !== expectedVersion) fail(`r17_security_baseline:${pkgName}:${meta?.version || '<missing>'}:expected:${expectedVersion}`);
  }
}

if (failures.length) {
  console.error('npm lock validation FAILED');
  for (const f of failures) console.error(` - ${f}`);
  process.exit(1);
}
const digest = crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'frontend','package-lock.json'))).digest('hex');
console.log(`npm lock validation OK; frontend-lock-sha256=${digest}`);
