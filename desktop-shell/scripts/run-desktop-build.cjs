#!/usr/bin/env node

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const repoRoot = path.resolve(root, '..');
const reportsDir = path.join(repoRoot, 'build-reports');
const innerBuildLog = path.join(reportsDir, 'desktop-build-inner.log');

fs.mkdirSync(reportsDir, { recursive: true });
const logStream = fs.createWriteStream(innerBuildLog, { flags: 'w' });

const forwardedArgs = process.argv
  .slice(2)
  .map((arg) => (process.platform === 'win32' && arg === '--clean' ? '-Clean' : arg));

const buildScript = process.platform === 'win32'
  ? path.join(root, 'tauri-skeleton', 'build.ps1')
  : path.join(root, 'tauri-skeleton', 'build.sh');

const command = process.platform === 'win32' ? 'powershell' : 'bash';
const args = process.platform === 'win32'
  ? ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', buildScript, ...forwardedArgs]
  : [buildScript, ...forwardedArgs];

logStream.write(`command=${command} ${args.join(' ')}\n`);
logStream.write(`cwd=${root}\n`);
logStream.write(`started_utc=${new Date().toISOString()}\n\n`);

const child = spawn(command, args, {
  cwd: root,
  stdio: ['inherit', 'pipe', 'pipe'],
});

child.stdout.on('data', (chunk) => {
  process.stdout.write(chunk);
  logStream.write(chunk);
});

child.stderr.on('data', (chunk) => {
  process.stderr.write(chunk);
  logStream.write(chunk);
});

child.on('error', (error) => {
  const message = `\nspawn_error=${error.stack || error.message || String(error)}\n`;
  process.stderr.write(message);
  logStream.end(message, () => process.exit(1));
});

child.on('exit', (code, signal) => {
  const exitCode = code ?? 1;
  const footer = `\nfinished_utc=${new Date().toISOString()}\nexit_code=${exitCode}\nsignal=${signal || ''}\n`;
  logStream.end(footer, () => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(exitCode);
  });
});
