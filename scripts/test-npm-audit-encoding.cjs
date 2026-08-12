#!/usr/bin/env node
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const cp = require('node:child_process');

const evaluator = path.resolve(__dirname, 'evaluate-npm-audits.cjs');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'sb-audit-encoding-'));
const payload = JSON.stringify({ metadata: { vulnerabilities: { info: 0, low: 0, moderate: 0, high: 0, critical: 0 } } });

try {
  fs.writeFileSync(path.join(tmp, 'npm-audit-utf8.json'), payload, 'utf8');
  const utf16Body = Buffer.from(payload, 'utf16le');
  fs.writeFileSync(path.join(tmp, 'npm-audit-utf16le.json'), Buffer.concat([Buffer.from([0xff, 0xfe]), utf16Body]));
  const bomUtf8 = Buffer.concat([Buffer.from([0xef,0xbb,0xbf]), Buffer.from(payload, 'utf8')]);
  fs.writeFileSync(path.join(tmp, 'npm-audit-utf8bom.json'), bomUtf8);
  const r = cp.spawnSync(process.execPath, [evaluator, tmp], { encoding: 'utf8' });
  if (r.status !== 0) {
    console.error(r.stdout || ''); console.error(r.stderr || '');
    process.exit(r.status || 1);
  }
  if (!/reports=3/.test(r.stdout) || !/moderate=0/.test(r.stdout)) {
    console.error(`unexpected evaluator output: ${r.stdout}`);
    process.exit(2);
  }
  console.log('npm audit encoding regression OK; UTF-8/BOM/UTF-16LE supported');
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}
