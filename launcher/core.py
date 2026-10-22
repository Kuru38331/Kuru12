"""Reversible local game patch installation; no remote identity validation."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
STATE = '.hsho-unified-launcher'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def install(game, bundle=ROOT, state_name=STATE):
    game, bundle = Path(game).resolve(), Path(bundle).resolve()
    manifest = json.loads((bundle/'patches.json').read_text())
    if digest(game/'HSHO/Binaries/Win64/HSHO-Win64-Shipping.exe') != manifest['shipping']:
        raise ValueError('Game build does not match this package')
    state = game/state_name
    if state.exists():
        saved = json.loads((state/'state.json').read_text())
        for row in saved['files']:
            if digest(game/row['path']) != row['installed']:
                raise ValueError('Installed patch changed; no files overwritten')
        if [(r['path'],r['installed']) for r in saved['files']] != [(r['path'],r['installed']) for r in manifest['files']]:
            raise ValueError('Different patch version installed; restore it first')
        return 'Installed patches already match.'
    plan = []
    for row in manifest['files']:
        target, source = game/row['path'], bundle/'patches'/row['path']
        if not target.resolve().is_relative_to(game):
            raise ValueError('Target outside game folder')
        if digest(source) != row['installed']:
            raise ValueError('Package checksum mismatch')
        existing = digest(target) if target.exists() else None
        if existing is not None and existing not in (row['installed'],row['original']):
            raise ValueError('Unknown existing override: '+row['path'])
        plan.append(dict(row, adopted=existing==row['installed'], previous=existing))
    state.mkdir()
    attempted = []
    try:
        for i,row in enumerate(plan):
            if row['adopted']:
                continue
            target=game/row['path']
            if row['previous']:
                shutil.copyfile(target,state/str(i))
            target.parent.mkdir(parents=True,exist_ok=True)
            attempted.append((i,row))
            shutil.copyfile(bundle/'patches'/row['path'],target)
        (state/'state.json').write_text(json.dumps({'files':plan},indent=2))
    except Exception:
        for i,row in reversed(attempted):
            target=game/row['path']
            if row['previous']:
                shutil.copyfile(state/str(i),target)
            else:
                target.unlink(missing_ok=True)
        shutil.rmtree(state)
        raise
    return 'Local login, icons and selection fix are ready.'


def remove(game, state_name=STATE):
    game=Path(game).resolve();state=game/state_name
    saved=json.loads((state/'state.json').read_text())
    for i,row in enumerate(saved['files']):
        target=game/row['path']
        if not target.resolve().is_relative_to(game) or digest(target)!=row['installed']:
            raise ValueError('Patch changed; nothing removed')
        if not row['adopted'] and row['previous'] and digest(state/str(i))!=row['previous']:
            raise ValueError('Backup checksum mismatch')
    for i,row in enumerate(saved['files']):
        if row['adopted']:
            continue
        target=game/row['path']
        if row['previous']:
            shutil.copyfile(state/str(i),target)
        else:
            target.unlink()
    shutil.rmtree(state)
    return 'Launcher-installed patches restored; earlier installed patches kept.'


def import_profile(source, target):
    # Import selection only; never copy account/session or arbitrary profile files.
    import sys
    sys.path.insert(0,str(ROOT/'server'))
    from character_state import CharacterState
    from character_selection import load_catalog
    source,target=Path(source),Path(target)
    if target.exists():
        raise ValueError('This launcher already has a saved selection; not overwritten')
    profile=json.loads((ROOT/'server/experimental-profile.json').read_text())['response']
    CharacterState(profile,load_catalog(ROOT/'server/character-catalog.json'),source)
    data=json.loads(source.read_text())
    target.write_text(json.dumps({'version':1,'selection':data['selection']}))
