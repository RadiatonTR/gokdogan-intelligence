#!/usr/bin/env node
const fs=require('node:fs'), os=require('node:os'), path=require('node:path'), cp=require('node:child_process');
const evaluator=path.resolve(__dirname,'evaluate-npm-audits.cjs');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'sb-audit-policy-'));
try {
  const payload={metadata:{vulnerabilities:{info:0,low:0,moderate:1,high:0,critical:0}},vulnerabilities:{example:{severity:'moderate',range:'<2.0.0',fixAvailable:true,via:[{title:'synthetic advisory',url:'https://example.invalid/advisory'}]}}};
  fs.writeFileSync(path.join(tmp,'npm-audit-example.json'),JSON.stringify(payload));
  const r=cp.spawnSync(process.execPath,[evaluator,tmp],{encoding:'utf8'});
  if(r.status!==2 || !/moderate production dependency vulnerabilities/.test(r.stderr) || !/example:severity=moderate/.test(r.stderr)) {
    console.error('unexpected moderate gate behavior'); console.error(r.stdout); console.error(r.stderr); process.exit(1);
  }
  console.log('npm audit policy regression OK; moderate findings are detailed and release-blocking');
} finally { fs.rmSync(tmp,{recursive:true,force:true}); }
