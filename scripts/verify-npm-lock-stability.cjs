#!/usr/bin/env node
'use strict';
const fs = require('fs');
const path = require('path');

function die(msg) { console.error(`npm lock stability FAILED: ${msg}`); process.exit(1); }
if (process.argv.length !== 4) die('usage: verify-npm-lock-stability.cjs <before-lock> <after-lock>');
const beforePath = path.resolve(process.argv[2]);
const afterPath = path.resolve(process.argv[3]);
const before = JSON.parse(fs.readFileSync(beforePath, 'utf8'));
const after = JSON.parse(fs.readFileSync(afterPath, 'utf8'));

function versionMap(lock) {
  const out = new Map();
  for (const [pkgPath, meta] of Object.entries(lock.packages || {})) {
    if (!pkgPath || !meta || typeof meta !== 'object') continue;
    if (typeof meta.version === 'string') out.set(pkgPath, meta.version);
  }
  return out;
}
const a = versionMap(before), b = versionMap(after);
const errors = [];
for (const [pkg, ver] of a) {
  if (!b.has(pkg)) errors.push(`removed:${pkg}@${ver}`);
  else if (b.get(pkg) !== ver) errors.push(`version_changed:${pkg}:${ver}->${b.get(pkg)}`);
}
for (const [pkg, ver] of b) if (!a.has(pkg)) errors.push(`added:${pkg}@${ver}`);
if (before.lockfileVersion !== after.lockfileVersion) errors.push(`lockfileVersion:${before.lockfileVersion}->${after.lockfileVersion}`);
if (errors.length) {
  console.error('npm lock metadata refresh attempted to change the dependency graph. Refusing automatic repair.');
  for (const e of errors.slice(0, 50)) console.error(` - ${e}`);
  if (errors.length > 50) console.error(` - ... ${errors.length - 50} more`);
  process.exit(1);
}
console.log(`npm lock stability OK; ${a.size} package-path versions unchanged`);
