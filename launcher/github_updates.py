"""Repository-pinned release updates; stage first, verify, then replace after exit."""
import hashlib,json,os,re,subprocess,sys,tempfile,zipfile
from pathlib import Path,PurePosixPath
import urllib.request

REPOSITORY='Kuru38331/Kuru12'
LIMIT=100*1024*1024

def version(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d+(?:\.\d+){2,3}',value):raise ValueError('Invalid release version')
    return tuple(map(int,value.split('.')))

def download(url,limit):
    request=urllib.request.Request(url,headers={'User-Agent':'Kuru12-Launcher','Accept':'application/vnd.github+json' if 'api.github.com' in url else 'application/octet-stream'})
    with urllib.request.urlopen(request,timeout=20) as response:
        data=response.read(limit+1)
    if len(data)>limit:raise ValueError('Update exceeds limit')
    return data

def release_manifest(current,fetch=download):
    data=json.loads(fetch('https://api.github.com/repos/'+REPOSITORY+'/releases/latest',1024*1024))
    if data.get('draft') or data.get('prerelease'):return None
    tag=data['tag_name'];remote=tag.removeprefix('v')
    if version(remote)<=version(current):return None
    asset=next(a for a in data['assets'] if a['name']=='update-manifest.json')
    url=asset['browser_download_url'];prefix='https://github.com/'+REPOSITORY+'/releases/download/'+tag+'/'
    if url!=prefix+'update-manifest.json':raise ValueError('Unexpected update source')
    manifest=json.loads(fetch(url,2*1024*1024))
    if manifest['version']!=remote or manifest['asset']!='Kuru12-Launcher.zip':raise ValueError('Release metadata mismatch')
    if not re.fullmatch('[0-9a-f]{64}',manifest['sha256']):raise ValueError('Invalid checksum')
    return manifest,prefix+manifest['asset']

def stage(manifest,archive,folder):
    if hashlib.sha256(archive).hexdigest()!=manifest['sha256']:raise ValueError('Update checksum mismatch')
    import io
    expected=manifest['files'];seen=set();folder=Path(folder)
    protected={'profiles','runtime','backup','server-console.log','launcher-settings.json','local-character-state.json','observations.jsonl'}
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        if sum(i.file_size for i in z.infolist())>300*1024*1024:raise ValueError('Expanded update exceeds limit')
        for info in z.infolist():
            name=info.filename;p=PurePosixPath(name)
            if info.is_dir():continue
            if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or name in seen or any(v.lower() in protected or v.lower().startswith('backup-') for v in p.parts):raise ValueError('Unsafe update path')
            if name not in expected:raise ValueError('Unexpected update file')
            raw=z.read(info)
            if hashlib.sha256(raw).hexdigest()!=expected[name]:raise ValueError('Update file checksum mismatch')
            seen.add(name)
            dest=folder.joinpath(*p.parts);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
    if seen!=set(expected):raise ValueError('Incomplete update')
    return folder

def install_after_exit(root,manifest,staged):
    # Helper lives outside target. Back up every replaced file before mutation.
    root=Path(root).resolve();staged=Path(staged).resolve()
    def quote(s):return "'"+str(s).replace("'","''")+"'"
    names=','.join(quote(n) for n in manifest['files'])
    exe=root/'Kuru12.exe';restart=exe if exe.exists() else root/'Open-HSHO.cmd'
    script=f'''$ErrorActionPreference='Stop'
$target={quote(root)}
$stage={quote(staged)}
$names=@({names})
Wait-Process -Id {os.getpid()} -Timeout 30 -ErrorAction SilentlyContinue
if(Get-Process -Id {os.getpid()} -ErrorAction SilentlyContinue) {{throw 'Launcher still running; no files changed'}}
$backup=Join-Path $target ('backup-release-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $backup | Out-Null
foreach($n in $names) {{ $p=Join-Path $target $n; if(Test-Path -LiteralPath $p) {{$b=Join-Path $backup $n; New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($b)) -Force | Out-Null; Copy-Item -LiteralPath $p -Destination $b}} }}
try {{ foreach($n in $names) {{$p=Join-Path $target $n; New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($p)) -Force | Out-Null; Copy-Item -LiteralPath (Join-Path $stage $n) -Destination $p -Force}} }}
catch {{foreach($n in $names) {{$p=Join-Path $target $n;$b=Join-Path $backup $n;if(Test-Path -LiteralPath $b) {{Copy-Item -LiteralPath $b -Destination $p -Force}} else {{Remove-Item -LiteralPath $p -ErrorAction SilentlyContinue}}}}; Write-Host 'Update failed; previous files restored.'; Read-Host 'Press Enter'; exit 1}}
Start-Process -FilePath {quote(restart)} -WorkingDirectory $target
'''
    helper=staged.parent/'apply-update.ps1';helper.write_text(script,encoding='utf-8-sig')
    subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(helper)],creationflags=getattr(subprocess,'CREATE_NEW_CONSOLE',0))

def check_and_stage(root):
    current=json.loads((Path(root)/'version.json').read_text())['version']
    release=release_manifest(current)
    if release is None:return None
    manifest,url=release
    folder=Path(tempfile.mkdtemp(prefix='kuru12-update-'))/'files'
    stage(manifest,download(url,LIMIT),folder)
    return manifest,folder
