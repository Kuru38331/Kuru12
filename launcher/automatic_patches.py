"""Apply the bundled release; no downloading or changes to unknown patches."""
import json
from pathlib import Path
import shutil
import tempfile
from core import ROOT, install, digest


def update_mewmew(game):
    game=Path(game)
    bundle=ROOT/'mewmew'
    state=game/'.hsho-mewmew-test'
    if not state.exists():
        return install(game,bundle=bundle,state_name=state.name)
    saved=json.loads((state/'state.json').read_text())
    current=json.loads((bundle/'patches.json').read_text())
    if [(r['path'],r['installed']) for r in saved['files']]==[(r['path'],r['installed']) for r in current['files']]:
        return install(game,bundle=bundle,state_name=state.name)
    previous_versions=[json.loads(p.read_text()) for p in
                       [bundle/'previous-patches.json',bundle/'earlier-patches.json'] if p.exists()]
    signature=[(r['path'],r['installed']) for r in saved['files']]
    if not any(signature==[(r['path'],r['installed']) for r in version['files']] for version in previous_versions):
        raise ValueError('Unknown Mewmew release; no patch overwritten')
    if digest(game/'HSHO/Binaries/Win64/HSHO-Win64-Shipping.exe') != current['shipping']:
        raise ValueError('Game build mismatch')
    for old,new in zip(saved['files'],current['files']):
        if old['path']!=new['path'] or digest(game/old['path'])!=old['installed'] or digest(bundle/'patches'/new['path'])!=new['installed']:
            raise ValueError('Mewmew checksum mismatch; no patch overwritten')
    with tempfile.TemporaryDirectory() as directory:
        rollback=Path(directory)
        shutil.copytree(state,rollback/'state')
        for i,row in enumerate(saved['files']):shutil.copyfile(game/row['path'],rollback/str(i))
        try:
            for i,(old,new) in enumerate(zip(saved['files'],current['files'])):
                if old['adopted'] and old['installed']!=new['installed']:
                    shutil.copyfile(game/old['path'],state/str(i))
                    old['adopted']=False;old['previous']=old['installed']
                shutil.copyfile(bundle/'patches'/new['path'],game/new['path'])
                old['installed']=new['installed']
            (state/'state.json').write_text(json.dumps(saved,indent=2))
        except Exception:
            for i,row in enumerate(saved['files']):shutil.copyfile(rollback/str(i),game/row['path'])
            shutil.rmtree(state);shutil.copytree(rollback/'state',state)
            raise


def apply_all(game):
    install(game)
    update_mewmew(game)
    install(game,bundle=ROOT/'perks',state_name='.hsho-perks-test')
    install(game,bundle=ROOT/'curse-relic',state_name='.hsho-curse-relic-test')
    from aisha_speed import change
    change(game)
