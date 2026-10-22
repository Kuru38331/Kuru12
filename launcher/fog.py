"""Optional engine fog settings layered above the reversible low-spec config."""
import json
from pathlib import Path
from low_spec import atomic, sha

SETTINGS='\r\n; HSHO optional fog off\r\n[SystemSettings]\r\nr.Fog=0\r\nr.VolumetricFog=0\r\n'


def paths(config):
    config=Path(config)
    return config/'Engine.ini',config/'Engine.ini.hsho-fog.json',config/'Engine.ini.hsho-fog.bak'


def apply(config):
    from graphics_config import manage
    return manage(config,'fog',SETTINGS,True)


def restore(config):
    from graphics_config import manage
    return manage(config,'fog',SETTINGS,False)


def configure(config, low_enabled, fog_disabled):
    from low_spec import apply as low_apply, restore as low_restore, paths as low_paths
    restore(config)
    if low_enabled:low_apply(config)
    elif low_paths(config)[1].exists():low_restore(config)
    if fog_disabled:apply(config)
