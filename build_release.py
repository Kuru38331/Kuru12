"""Run on GitHub Windows runner; zip clean distributable and emit checksums."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,zipfile
root=Path(__file__).parent
source=root/'launcher'
version=json.loads((source/'version.json').read_text())['version']
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--contents-directory','.','--name','Kuru12','--noconsole','--hidden-import','argparse','--hidden-import','winreg',str(source/'launcher.py')],check=True,cwd=root)
out=root/'dist/Kuru12'
# Python sources/data are kept beside executable so existing patch paths match.
for p in source.rglob('*'):
 if p.is_file():
  dest=out/p.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
files={str(p.relative_to(out)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
with zipfile.ZipFile(root/'Kuru12-Launcher.zip','w',zipfile.ZIP_DEFLATED) as z:
 for name in files:z.write(out/name,name)
manifest={'version':version,'asset':'Kuru12-Launcher.zip','sha256':hashlib.sha256((root/'Kuru12-Launcher.zip').read_bytes()).hexdigest(),'files':files}
(root/'update-manifest.json').write_text(json.dumps(manifest,indent=2))
print('Release',version,'files',len(files))
