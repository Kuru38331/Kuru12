"""Local profile character selection from supplied asset evidence, not a shop unlock."""
import copy
import json
from pathlib import Path


def load_catalog(path=None):
    data = json.loads(Path(path or Path(__file__).with_name('character-catalog.json')).read_text())
    result = {}
    for row in data['characters']:
        if row['id'] in result:
            raise ValueError('Duplicate character item ID')
        result[row['id']] = row
    return result


def apply_selection(profile, catalog, visitor=None, warden=None, role=None, allow_special=False):
    selections = []
    for name, faction, field in [(visitor, 'visitor', 'characteritem'),
                                 (warden, 'warden', 'characterhunteritem')]:
        if name is None:
            continue
        row = catalog.get(name)
        if not row or not row.get('selection_metadata_complete'):
            raise ValueError('Character ID is unknown or its pawn binding is unresolved: '+str(name))
        if row['faction'] != faction:
            raise ValueError('Character faction does not match selected slot: '+name)
        if row.get('special_asset') and not allow_special:
            raise ValueError('Development/tutorial asset requires explicit special-asset option: '+name)
        selections.append((field, name))
    if role not in (None, 'survivor', 'hunter'):
        raise ValueError('Role must be survivor or hunter')
    result = copy.deepcopy(profile)
    player = result['data']['player']
    for field, name in selections:
        player['characterSlot'][field] = name
    if role is not None:
        player['role'] = role
    return result
