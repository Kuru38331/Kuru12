"""Private per-account local selection saves, outside the shared launcher package."""
import os
from pathlib import Path
import re


def state_path(local_id, appdata=None):
    if not isinstance(local_id,str) or not re.fullmatch(r'local-[0-9a-f]{24}',local_id):
        raise ValueError('Invalid local profile key')
    parent=Path(appdata if appdata is not None else os.environ['LOCALAPPDATA'])
    folder=parent/'HSHO-Launcher'/'profiles'/local_id
    folder.mkdir(parents=True,exist_ok=True)
    return folder/'local-character-state.json'


def import_selection(data, local_id, appdata=None):
    import json
    import tempfile
    from core import import_profile
    if not isinstance(data,dict):raise ValueError('Invalid saved selection')
    encoded=json.dumps(data).encode()
    if len(encoded)>65536:raise ValueError('Saved selection too large')
    target=state_path(local_id,appdata)
    with tempfile.TemporaryDirectory() as directory:
        source=Path(directory)/'selection.json';source.write_bytes(encoded)
        import_profile(source,target)
    return target
