#!/usr/bin/env node
'use strict';
const fs = require('fs');
const path = require('path');

function die(msg) { console.error(`npm integrity refresh FAILED: ${msg}`); process.exit(1); }
const lockArg = process.argv[2];
if (!lockArg) die('usage: refresh-npm-lock-integrities.cjs <package-lock.json>');
const lockPath = path.resolve(lockArg);
const lock = JSON.parse(fs.readFileSync(lockPath, 'utf8'));
if (lock.lockfileVersion !== 3) die(`unsupported lockfileVersion ${lock.lockfileVersion}`);

function packageNameFromPath(pkgPath) {
  const marker = 'node_modules/';
  const i = pkgPath.lastIndexOf(marker);
  if (i < 0) return null;
  return pkgPath.slice(i + marker.length);
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
async function fetchMeta(name, version) {
  const encoded = encodeURIComponent(name);
  const url = `https://registry.npmjs.org/${encoded}/${encodeURIComponent(version)}`;
  let last;
  for (let attempt = 1; attempt <= 4; attempt++) {
    try {
      const res = await fetch(url, {
        headers: { 'accept': 'application/json', 'user-agent': 'shadowbroker-r16-lock-integrity-refresh/1' },
        redirect: 'follow',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const meta = await res.json();
      if (!meta?.dist?.integrity) throw new Error('registry metadata missing dist.integrity');
      if (!String(meta.dist.integrity).startsWith('sha512-')) throw new Error(`unexpected integrity algorithm: ${meta.dist.integrity}`);
      return { integrity: meta.dist.integrity, tarball: meta.dist.tarball || null };
    } catch (e) {
      last = e;
      if (attempt < 4) await sleep(750 * attempt);
    }
  }
  throw new Error(`${name}@${version}: ${last?.message || last}`);
}

const groups = new Map();
for (const [pkgPath, meta] of Object.entries(lock.packages || {})) {
  if (!pkgPath || !meta || typeof meta !== 'object') continue;
  if (!meta.version || !meta.resolved || !String(meta.resolved).startsWith('https://registry.npmjs.org/')) continue;
  const name = packageNameFromPath(pkgPath);
  if (!name) continue;
  const key = `${name}@${meta.version}`;
  if (!groups.has(key)) groups.set(key, { name, version: meta.version, entries: [] });
  groups.get(key).entries.push({ pkgPath, meta });
}

const jobs = [...groups.values()];
let cursor = 0, repaired = 0, checked = 0;
const errors = [];
const concurrency = Math.min(16, Math.max(4, Number(process.env.SB_NPM_METADATA_CONCURRENCY || 12)));
async function worker() {
  while (true) {
    const idx = cursor++;
    if (idx >= jobs.length) return;
    const job = jobs[idx];
    try {
      const canonical = await fetchMeta(job.name, job.version);
      checked++;
      for (const { meta } of job.entries) {
        if (meta.integrity !== canonical.integrity) {
          meta.integrity = canonical.integrity;
          repaired++;
        }
        if (canonical.tarball && String(canonical.tarball).startsWith('https://registry.npmjs.org/')) {
          meta.resolved = canonical.tarball;
        }
      }
      if (checked % 50 === 0) console.log(`npm integrity metadata checked: ${checked}/${jobs.length}`);
    } catch (e) { errors.push(String(e.message || e)); }
  }
}
(async () => {
  await Promise.all(Array.from({ length: concurrency }, worker));
  if (errors.length) {
    console.error(`Unable to verify ${errors.length} registry package versions:`);
    for (const e of errors.slice(0, 20)) console.error(` - ${e}`);
    if (errors.length > 20) console.error(` - ... ${errors.length - 20} more`);
    process.exit(1);
  }
  fs.writeFileSync(lockPath, JSON.stringify(lock, null, 2) + '\n');
  console.log(`npm integrity refresh OK; registry packages=${jobs.length}, entries_repaired=${repaired}`);
})().catch(e => die(e.stack || e.message || String(e)));
