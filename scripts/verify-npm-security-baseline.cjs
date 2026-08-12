#!/usr/bin/env node
'use strict';
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const sourceOnly = process.argv.includes('--source');
const pkgPath = path.join(root, 'frontend', 'package.json');
const lockPath = path.join(root, 'frontend', 'package-lock.json');
const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
const lock = JSON.parse(fs.readFileSync(lockPath, 'utf8'));
const failures = [];
const fail = (m) => failures.push(m);
const expected = {
  next: '16.2.11',
  nanoid: '3.3.17',
  postcss: '8.5.24',
  sharp: '0.35.3',
};
if (pkg.version !== '1.0.0') fail(`frontend_version:${pkg.version}`);
if (pkg.dependencies?.next !== expected.next) fail(`package_json_next:${pkg.dependencies?.next}`);
for (const name of ['nanoid','postcss','sharp']) {
  if (pkg.overrides?.[name] !== expected[name]) fail(`package_json_override_${name}:${pkg.overrides?.[name]}`);
}
if (lock.version !== '1.0.0' || lock.packages?.['']?.version !== '1.0.0') fail('lock_root_version_not_r24');
if (lock.packages?.['']?.dependencies?.next !== expected.next) fail('lock_root_next_spec_not_r24');
if (!sourceOnly) {
  for (const [name, version] of Object.entries(expected)) {
    const meta = lock.packages?.[`node_modules/${name}`];
    if (!meta) fail(`locked_package_missing:${name}`);
    else if (meta.version !== version) fail(`locked_package_version:${name}:${meta.version}:expected:${version}`);
  }
  for (const [key, meta] of Object.entries(lock.packages || {})) {
    if (!key || !meta?.version) continue;
    const name = key.slice(key.lastIndexOf('node_modules/') + 'node_modules/'.length);
    if (name === 'nanoid' && meta.version !== expected.nanoid) fail(`nested_nanoid_not_overridden:${key}:${meta.version}`);
    if (name === 'postcss' && meta.version !== expected.postcss) fail(`nested_postcss_not_overridden:${key}:${meta.version}`);
    if (name === 'sharp' && meta.version !== expected.sharp) fail(`nested_sharp_not_overridden:${key}:${meta.version}`);
  }
}
if (failures.length) {
  console.error(`npm R24 security baseline FAILED (${sourceOnly ? 'source' : 'locked'})`);
  for (const f of failures) console.error(` - ${f}`);
  process.exit(1);
}
console.log(`npm R24 security baseline OK (${sourceOnly ? 'source pins' : 'locked safe versions'}): next=${expected.next} nanoid=${expected.nanoid} postcss=${expected.postcss} sharp=${expected.sharp}`);
