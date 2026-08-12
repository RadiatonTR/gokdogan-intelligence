#!/usr/bin/env python3
"""Generate a lightweight CycloneDX component inventory without network access."""
from __future__ import annotations
import argparse, json, subprocess, sys, tomllib
from importlib import metadata as importlib_metadata
from pathlib import Path


def npm_components(lock_path: Path, scope: str):
    if not lock_path.exists(): return []
    data=json.loads(lock_path.read_text(encoding='utf-8'))
    out=[]
    for path, meta in (data.get('packages') or {}).items():
        if not path or not path.startswith('node_modules/'): continue
        name=meta.get('name') or path.removeprefix('node_modules/')
        version=meta.get('version')
        if name and version: out.append({'type':'library','name':name,'version':str(version),'group':scope,'purl':f'pkg:npm/{name}@{version}'})
    return out


def cargo_components(lock_path: Path):
    if not lock_path.exists(): return []
    data=tomllib.loads(lock_path.read_text(encoding='utf-8'))
    return [{'type':'library','name':p['name'],'version':str(p['version']),'group':'rust','purl':f"pkg:cargo/{p['name']}@{p['version']}"} for p in data.get('package',[]) if p.get('name') and p.get('version')]


def python_components(root: Path, python: str | None, site_packages: str | None = None):
    if site_packages:
        try:
            out=[]
            for dist in importlib_metadata.distributions(path=[site_packages]):
                name=dist.metadata.get("Name") or dist.name
                version=dist.version
                if name and version:
                    out.append({"type":"library","name":name,"version":version,"group":"python","purl":f"pkg:pypi/{name}@{version}"})
            if out:
                return out
        except Exception:
            pass
    if python:
        try:
            raw=subprocess.check_output([python,'-m','pip','list','--format=json'], text=True, stderr=subprocess.DEVNULL)
            return [{'type':'library','name':p['name'],'version':p['version'],'group':'python','purl':f"pkg:pypi/{p['name']}@{p['version']}"} for p in json.loads(raw)]
        except Exception: pass
    pyproject=root/'backend'/'pyproject.toml'
    if not pyproject.exists(): return []
    data=tomllib.loads(pyproject.read_text(encoding='utf-8'))
    out=[]
    for spec in data.get('project',{}).get('dependencies',[]):
        name=spec.split(';',1)[0].strip().split('[',1)[0]
        for sep in ('>=','<=','==','~=','>','<'):
            name=name.split(sep,1)[0]
        if name: out.append({'type':'library','name':name.strip(),'version':'declared','group':'python'})
    return out


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default=str(Path(__file__).resolve().parents[1])); ap.add_argument('--python'); ap.add_argument('--site-packages'); ap.add_argument('--output')
    a=ap.parse_args(); root=Path(a.root).resolve(); output=Path(a.output) if a.output else root/'SBOM-R24.cdx.json'
    comps=[]
    comps += python_components(root,a.python,a.site_packages)
    comps += npm_components(root/'frontend'/'package-lock.json','frontend')
    comps += npm_components(root/'backend'/'package-lock.json','backend-node')
    comps += npm_components(root/'desktop-shell'/'package-lock.json','desktop-shell')
    comps += cargo_components(root/'desktop-shell'/'tauri-skeleton'/'src-tauri'/'Cargo.lock')
    seen=set(); unique=[]
    for c in comps:
        k=(c.get('group'),c['name'],c.get('version'))
        if k in seen: continue
        seen.add(k); unique.append(c)
    release={}
    try:
        release=json.loads((root/'release-version.json').read_text(encoding='utf-8-sig'))
    except Exception:
        release={}
    technical_version=str(release.get('technical_base_version') or '0.10.3')
    technical_revision=str(release.get('technical_core_revision') or 'R24')
    distribution_slug=str(release.get('distribution_slug') or 'GOKDOGAN-INTELLIGENCE-v1.0.0')
    app_version=f"{technical_version}-{technical_revision}+{distribution_slug}"
    component={
        'type':'application',
        'name':str(release.get('product') or 'Gökdoğan Intelligence Desktop'),
        'version':app_version,
        'properties':[
            {'name':'gokdogan:distribution','value':str(release.get('distribution') or 'Gökdoğan Intelligence 1.0.0')},
            {'name':'gokdogan:technical-core-revision','value':technical_revision},
            {'name':'gokdogan:release-profile','value':str(release.get('release_profile') or 'public-authorized-osint')},
            {'name':'gokdogan:default-language','value':str(release.get('default_language') or 'tr')},
        ],
    }
    doc={'bomFormat':'CycloneDX','specVersion':'1.5','version':1,'metadata':{'component':component},'components':sorted(unique,key=lambda x:(x.get('group',''),x['name'].casefold(),x.get('version','')))}
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"SBOM: {output} ({len(unique)} components)")

if __name__=='__main__': main()
