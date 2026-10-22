"""Optional local Aisha speed effect; restore previous exact loose assets."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent
REL=Path('HSHO/Content/Game/Blueprints/Ability/Characters/Buff')
NAMES=('GE_Buff_AishaAP.uasset','GE_Buff_AishaAP.uexp')
STATE='.hsho-aisha-speed-test'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def change(game, remove=False, bundle=None):
    game=Path(game).resolve();bundle=Path(bundle) if bundle else ROOT/'aisha-speed'
    manifest=json.loads((bundle/'manifest.json').read_text())
    state=game/STATE;targets=[game/REL/n for n in NAMES]
    if any(not p.resolve().is_relative_to(game) for p in targets+[state]):
        raise ValueError('Target outside game folder')
    if remove:
        saved=json.loads((state/'state.json').read_text())
        if any(not p.is_file() or digest(p)!=h for p,h in zip(targets,saved['installed'])):
            raise ValueError('Aisha effect changed; nothing removed')
        if saved['previous']:
            if any(digest(state/n)!=h for n,h in zip(NAMES,saved['previous'])):
                raise ValueError('Backup checksum mismatch')
            for n,p in zip(NAMES,targets):shutil.copyfile(state/n,p)
        else:
            for p in targets:p.unlink()
        shutil.rmtree(state)
        return 'Restored the exact Aisha effect used before this speed test.'
    if digest(game/'HSHO/Binaries/Win64/HSHO-Win64-Shipping.exe')!=manifest['shipping']:
        raise ValueError('Game build mismatch')
    installed=manifest['installed']
    if state.exists():
        saved=json.loads((state/'state.json').read_text())
        if saved['installed'] in [installed]+[v['installed'] for v in manifest.get('variants',[])] and all(p.is_file() and digest(p)==h for p,h in zip(targets,saved['installed'])):
            return 'Aisha speed test is already installed.'
        if saved['installed'] in manifest.get('upgrade_from',[]) and all(p.is_file() and digest(p)==h for p,h in zip(targets,saved['installed'])):
            sources=[bundle/'override'/REL/n for n in NAMES]
            if [digest(p) for p in sources]!=installed:raise ValueError('Bundle checksum mismatch')
            # Keep the original pre-install backup and state for Restore.
            before=[p.read_bytes() for p in targets]
            state_before=(state/'state.json').read_bytes()
            try:
                for src,dst in zip(sources,targets):shutil.copyfile(src,dst)
                saved['installed']=installed
                (state/'state.json').write_text(json.dumps(saved))
            except Exception:
                for p,data in zip(targets,before):p.write_bytes(data)
                (state/'state.json').write_bytes(state_before)
                raise
            return 'Aisha updated: MoveSpeed x3 for 15s; cooldown unchanged.'
        raise ValueError('Existing Aisha speed state differs; nothing overwritten')
    previous=[digest(p) for p in targets] if all(p.is_file() for p in targets) else None
    if any(p.exists() for p in targets) and previous not in manifest['accepted_previous']:
        raise ValueError('Unknown Aisha effect override; nothing overwritten')
    variant=next((v for v in manifest.get('variants',[]) if v['previous']==previous),None)
    installed=variant['installed'] if variant else manifest['installed']
    folder=variant['folder'] if variant else 'override'
    duration=variant['duration'] if variant else manifest['duration']
    sources=[bundle/folder/REL/n for n in NAMES]
    if [digest(p) for p in sources]!=installed:raise ValueError('Bundle checksum mismatch')
    state.mkdir();attempted=[]
    try:
        if previous:
            for n,p in zip(NAMES,targets):shutil.copyfile(p,state/n)
        targets[0].parent.mkdir(parents=True,exist_ok=True)
        for src,dst in zip(sources,targets):
            attempted.append(dst);shutil.copyfile(src,dst)
        (state/'state.json').write_text(json.dumps({'previous':previous,'installed':installed}))
    except Exception:
        for p in attempted:
            if previous:shutil.copyfile(state/p.name,p)
            else:p.unlink(missing_ok=True)
        shutil.rmtree(state);raise
    return f'Aisha buff: MoveSpeed modifier x3 for {duration:g}s; cooldown unchanged. Test in game.'
