#!/usr/bin/env node
'use strict';
const fs = require('fs');
const path = require('path');
const [beforeArg, afterArg] = process.argv.slice(2);
if (!beforeArg || !afterArg) {
  console.error('usage: verify-npm-security-delta.cjs <before-lock> <after-lock>');
  process.exit(2);
}
const before = JSON.parse(fs.readFileSync(path.resolve(beforeArg), 'utf8'));
const after = JSON.parse(fs.readFileSync(path.resolve(afterArg), 'utf8'));
function packageName(key) {
  if (!key) return '';
  const marker = 'node_modules/';
  const i = key.lastIndexOf(marker);
  return i < 0 ? key : key.slice(i + marker.length);
}
function allowed(name) {
  return name === '' || name === 'next' || name === '@next/env' || name.startsWith('@next/swc-') ||
    name === 'nanoid' || name === 'postcss' || name === 'sharp' || name === '@img/colour' ||
    name.startsWith('@img/sharp-') || name.startsWith('@img/sharp-libvips-') ||
    name === '@emnapi/runtime' || name === 'semver';
}
const b = new Map(Object.entries(before.packages || {}).map(([k,v]) => [k, v?.version || null]));
const a = new Map(Object.entries(after.packages || {}).map(([k,v]) => [k, v?.version || null]));
const keys = new Set([...b.keys(), ...a.keys()]);
const forbidden = [];
const changes = [];
for (const key of [...keys].sort()) {
  const bv = b.get(key) ?? null;
  const av = a.get(key) ?? null;
  if (bv === av) continue;
  const name = packageName(key);
  changes.push(`${key || '<root>'}:${bv || '<missing>'}->${av || '<missing>'}`);
  if (!allowed(name)) forbidden.push(`${key || '<root>'}:${name}:${bv || '<missing>'}->${av || '<missing>'}`);
}
if (forbidden.length) {
  console.error('npm R24 security delta FAILED: package versions outside the approved security patch set changed.');
  for (const x of forbidden.slice(0, 50)) console.error(` - ${x}`);
  process.exit(1);
}
console.log(`npm R24 security delta OK; approved package-path version changes=${changes.length}`);
for (const x of changes.slice(0, 40)) console.log(` - ${x}`);
if (changes.length > 40) console.log(` - ... ${changes.length - 40} more approved changes`);
