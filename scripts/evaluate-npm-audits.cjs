#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');

const dir = path.resolve(process.argv[2] || 'build-reports');
const allowHigh = process.env.SB_ALLOW_HIGH_AUDIT === '1';
const allowUnavailable = process.env.SB_ALLOW_AUDIT_UNAVAILABLE === '1';
if (!fs.existsSync(dir)) {
  console.error('npm audit gate FAILED: build-reports directory is missing.');
  process.exit(allowUnavailable ? 0 : 3);
}

function decodeAuditReport(file) {
  const buf = fs.readFileSync(file);
  if (buf.length >= 2 && buf[0] === 0xff && buf[1] === 0xfe) {
    return buf.subarray(2).toString('utf16le');
  }
  if (buf.length >= 2 && buf[0] === 0xfe && buf[1] === 0xff) {
    const body = Buffer.from(buf.subarray(2));
    for (let i = 0; i + 1 < body.length; i += 2) {
      const a = body[i]; body[i] = body[i + 1]; body[i + 1] = a;
    }
    return body.toString('utf16le');
  }
  let text = buf.toString('utf8');
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  // Some Windows PowerShell 5.1 redirections have no BOM but are obvious UTF-16LE.
  if (text.includes('\u0000')) {
    const utf16 = buf.toString('utf16le');
    if (utf16.trim().startsWith('{') || utf16.trim().startsWith('[')) text = utf16;
  }
  return text;
}

const totals = { info: 0, low: 0, moderate: 0, high: 0, critical: 0 };
const files = fs.readdirSync(dir).filter((name) => /^npm-audit-.*\.json$/i.test(name));
const unreadable = [];
const unavailable = [];
const findingDetails = [];
for (const name of files) {
  try {
    const raw = decodeAuditReport(path.join(dir, name));
    const parsed = JSON.parse(raw);
    const vulns = parsed?.metadata?.vulnerabilities;
    if (!vulns || typeof vulns !== 'object') {
      unavailable.push(name);
      continue;
    }
    for (const key of Object.keys(totals)) totals[key] += Number(vulns[key] || 0);
    for (const [pkgName, detail] of Object.entries(parsed?.vulnerabilities || {})) {
      if (!['moderate', 'high', 'critical'].includes(detail?.severity)) continue;
      const via = Array.isArray(detail.via) ? detail.via.map((v) => typeof v === 'string' ? v : (v?.url || v?.title || v?.source || 'advisory')).join(', ') : '';
      const fix = detail.fixAvailable === true ? 'available' : (detail.fixAvailable && typeof detail.fixAvailable === 'object' ? JSON.stringify(detail.fixAvailable) : 'none');
      findingDetails.push(`${name}:${pkgName}:severity=${detail.severity}:range=${detail.range || '?'}:fix=${fix}:via=${via}`);
    }
  } catch (error) {
    unreadable.push(`${name}:${error.message}`);
  }
}

console.log(`npm audit gate: reports=${files.length} info=${totals.info} low=${totals.low} moderate=${totals.moderate} high=${totals.high} critical=${totals.critical}`);
if (unreadable.length) console.error(`npm audit gate: unreadable reports: ${unreadable.join('; ')}`);
if (unavailable.length) console.error(`npm audit gate: audit service unavailable/invalid report: ${unavailable.join(', ')}`);
if (findingDetails.length) { console.error('npm audit gate: moderate/high/critical package details:'); for (const item of findingDetails) console.error(` - ${item}`); }
if ((files.length === 0 || unreadable.length || unavailable.length) && !allowUnavailable) {
  console.error('npm audit gate FAILED: release security audit could not be completed. Set SB_ALLOW_AUDIT_UNAVAILABLE=1 only for a documented offline build.');
  process.exit(3);
}
if (totals.critical > 0) {
  console.error('npm audit gate FAILED: critical production dependency vulnerabilities exist.');
  process.exit(2);
}
if (totals.moderate > 0) {
  console.error('npm audit gate FAILED: moderate production dependency vulnerabilities exist. R24 requires a warning-free production audit.');
  process.exit(2);
}
if (totals.high > 0 && !allowHigh) {
  console.error('npm audit gate FAILED: high-severity production dependency vulnerabilities exist. Review and update dependencies; SB_ALLOW_HIGH_AUDIT=1 is an explicit emergency override only.');
  process.exit(2);
}
if (totals.high > 0) {
  console.warn('npm audit gate OVERRIDE: high-severity findings were explicitly allowed by SB_ALLOW_HIGH_AUDIT=1.');
}
