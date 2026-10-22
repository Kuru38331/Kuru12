"""Local-only roster/selection state for source-observed HSHO character routes."""
import copy
import json
import math
import os
from pathlib import Path
import tempfile
import threading

SELECTED = {'characteritem': 'visitor', 'characterhunteritem': 'warden'}
ARRAYS = {'survivorSlot': 'visitor', 'hunterSlot': 'warden'}
STRINGS = {'character', 'cosmetic_hat', 'cosmetic_cloth', 'cosmetic_back',
           'cosmetic_acc1', 'cosmetic_acc2', 'cosmetic_acc3', 'ritual_stand', 'ritual_ghost'}
OBJECTS = {'cosmetic_item', 'cosmetic_pose', 'cosmetic_emote', 'cosmetic_effect',
           'item', 'skill', 'level_data'}
ROLES = {'survivor', 'hunter', 'spectator'}


def bounded_json(value, depth=0):
    if depth > 6:
        raise ValueError('Loadout nesting exceeds supported limit')
    if isinstance(value, str):
        if len(value) > 512:
            raise ValueError('Loadout string too long')
    elif value is None or type(value) is bool:
        pass
    elif type(value) in (int, float):
        if type(value) is int and value.bit_length() > 53:
            raise ValueError('Loadout integer exceeds supported range')
        if not math.isfinite(value):
            raise ValueError('Nonfinite loadout number')
    elif isinstance(value, list):
        if len(value) > 64:
            raise ValueError('Loadout array too long')
        for child in value:
            bounded_json(child, depth+1)
    elif isinstance(value, dict):
        if len(value) > 48:
            raise ValueError('Loadout object too large')
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 80 or key.lower() in (
                    'ticket', 'session_token', 'authorization', 'password', 'token'):
                raise ValueError('Unsupported loadout key')
            bounded_json(child, depth+1)
    else:
        raise ValueError('Unsupported loadout value type')


class CharacterState:
    def __init__(self, profile, catalog, path=None, allow_special=False):
        self.lock = threading.RLock()
        self.profile = copy.deepcopy(profile)
        self.catalog = catalog
        skin_file = Path(__file__).with_name('skin-catalog.json')
        skin_data = json.loads(skin_file.read_text()) if skin_file.exists() else {'skins': []}
        self.skins = sorted({row['id'] for row in skin_data['skins']
                             if row['character'] in catalog and
                             catalog[row['character']]['selection_metadata_complete'] and
                             not catalog[row['character']]['special_asset']})
        self.allowed = {n: r for n, r in catalog.items()
                        if r['selection_metadata_complete'] and (allow_special or not r['special_asset'])}
        loadout_file = Path(__file__).with_name('loadout-catalog.json')
        self.loadouts = json.loads(loadout_file.read_text()) if loadout_file.exists() else {'perks': [], 'curseRelic': []}
        cosmetic_file = Path(__file__).with_name('item-skin-catalog.json')
        self.item_skins = json.loads(cosmetic_file.read_text())['cosmeticconsume'] if cosmetic_file.exists() else []
        self.path = Path(path) if path else None
        player = self.profile['data']['player']
        slots = player['characterSlot']
        if not slots.get('characteritem'):
            slots['characteritem'] = 'Survivor_Tim'
        if not slots.get('characterhunteritem'):
            slots['characterhunteritem'] = 'Hunter_Belle'
        if player.get('role') not in ROLES:
            player['role'] = 'hunter'  # Matches supplied role-reader fallback.
        if self.path and self.path.exists():
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            if saved.get('version') != 1:
                raise ValueError('Unsupported local character state version')
            self.update(saved['selection'], persist=False)

    def validate_character(self, name, faction):
        if not isinstance(name, str) or name not in self.allowed:
            raise ValueError('Unknown or unsupported character item ID')
        if self.allowed[name]['faction'] != faction:
            raise ValueError('Character does not match slot faction')

    def validate_row(self, row, faction):
        if not isinstance(row, dict) or not set(row) <= STRINGS | OBJECTS | {'perkPassive'}:
            raise ValueError('Unsupported character loadout fields')
        self.validate_character(row.get('character'), faction)
        for key, value in row.items():
            if key in STRINGS and not isinstance(value, str):
                raise ValueError('Loadout field must be a string')
            if key in OBJECTS and not isinstance(value, dict):
                raise ValueError('Loadout field must be an object')
            if key == 'perkPassive' and (not isinstance(value, list)
                    or not all(isinstance(v, str) for v in value)):
                raise ValueError('Passive perks must be a string array')
        bounded_json(row)

    def update(self, body, persist=True):
        if not isinstance(body, dict) or not set(body) <= {'slots', 'role'}:
            raise ValueError('Unsupported character edit body')
        if 'slots' not in body or not isinstance(body['slots'], dict):
            raise ValueError('Character slots object is required')
        incoming = body['slots']
        if not set(incoming) <= set(SELECTED) | set(ARRAYS):
            raise ValueError('Unsupported slot fields')
        for field, faction in SELECTED.items():
            if field in incoming:
                self.validate_character(incoming[field], faction)
        for field, faction in ARRAYS.items():
            if field not in incoming:
                continue
            rows = incoming[field]
            if not isinstance(rows, list) or len(rows) > len(self.allowed):
                raise ValueError('Invalid loadout list')
            seen = set()
            for row in rows:
                self.validate_row(row, faction)
                if row['character'] in seen:
                    raise ValueError('Duplicate character loadout')
                seen.add(row['character'])
        if 'role' in body and (not isinstance(body['role'], str) or body['role'] not in ROLES):
            raise ValueError('Unsupported player role')
        with self.lock:
            candidate = copy.deepcopy(self.profile)
            player = candidate['data']['player']
            player['characterSlot'].update(copy.deepcopy(incoming))
            if 'role' in body:
                player['role'] = body['role']
            selection = {'slots': player['characterSlot'], 'role': player['role']}
            # Never persist the profile's session token, ticket, identity or headers.
            if persist and self.path:
                fd, temp = tempfile.mkstemp(prefix='.character-', dir=self.path.parent)
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                        json.dump({'version': 1, 'selection': selection}, stream, allow_nan=False)
                    os.replace(temp, self.path)
                finally:
                    Path(temp).unlink(missing_ok=True)
            self.profile = candidate
            return self.response()

    def response(self):
        with self.lock:
            response = copy.deepcopy(self.profile)
            # Both paths are source-observed: login player getter and refresh getter.
            response['data']['characters'] = sorted(self.allowed)
            response['data']['skins'] = list(self.skins)
            response['data']['cosmeticconsume'] = list(self.item_skins)
            response['data']['perks'] = list(self.loadouts['perks'])
            # Login getter reads data.player.curseRelic; refresh reads data.curseRelic.
            response['data']['player']['curseRelic'] = copy.deepcopy(self.loadouts['curseRelic'])
            response['data']['curseRelic'] = copy.deepcopy(self.loadouts['curseRelic'])
            response['data']['characterSlot'] = copy.deepcopy(
                response['data']['player']['characterSlot'])
            return response

    def inventory(self):
        return {'status': 1, 'data': {'characters': sorted(self.allowed), 'skins': list(self.skins),
                                      'perks': list(self.loadouts['perks']), 'cosmeticconsume': list(self.item_skins)}}
