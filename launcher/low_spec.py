"""Reversible UE4 Engine.ini settings for low VRAM. Never touches game textures."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

SETTINGS = '''
; HSHO Local Launcher low-spec profile
[SystemSettings]
r.TextureStreaming=1
r.Streaming.PoolSize=384
r.Streaming.LimitPoolSizeToVRAM=1
r.Streaming.MipBias=2
r.MaxAnisotropy=2
r.ScreenPercentage=75
r.ViewDistanceScale=0.6
r.ShadowQuality=0
r.PostProcessAAQuality=0
r.MotionBlurQuality=0
r.BloomQuality=0
r.DepthOfFieldQuality=0
r.AmbientOcclusionLevels=0
foliage.DensityScale=0.35
grass.DensityScale=0.35
t.MaxFPS=30
'''


def paths(config):
    config=Path(config)
    return config/'Engine.ini', config/'Engine.ini.hsho-low-spec.json', config/'Engine.ini.hsho-low-spec.bak'


def sha(data):return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    fd,temp=tempfile.mkstemp(prefix='.hsho-low-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data)
        os.replace(temp,path)
    finally:
        Path(temp).unlink(missing_ok=True)


def apply(config):
    from graphics_config import manage
    return manage(config,'low-spec',SETTINGS.replace('\n','\r\n'),True)


def restore(config):
    from graphics_config import manage
    return manage(config,'low-spec',SETTINGS.replace('\n','\r\n'),False)


def default_config():
    return Path(os.environ['LOCALAPPDATA'])/'HSHO/Saved/Config/WindowsNoEditor'
