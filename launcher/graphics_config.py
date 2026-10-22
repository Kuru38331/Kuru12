"""Manage only Launcher-owned Engine.ini entries; preserve other edits."""
import json
from pathlib import Path
import re
import uuid
from low_spec import atomic, sha


def decode(raw):
    if raw.startswith(b'\xff\xfe'):return raw[2:].decode('utf-16-le'),'utf-16-le',b'\xff\xfe'
    if raw.startswith(b'\xfe\xff'):return raw[2:].decode('utf-16-be'),'utf-16-be',b'\xfe\xff'
    if raw.startswith(b'\xef\xbb\xbf'):return raw[3:].decode('utf-8',errors='surrogateescape'),'utf-8',b'\xef\xbb\xbf'
    return raw.decode('utf-8',errors='surrogateescape'),'utf-8',b''


def values(text):
    found={};section=''
    for line in text.splitlines():
        s=line.strip()
        if s.startswith('[') and s.endswith(']'):section=s.lower()
        elif section=='[systemsettings]' and '=' in s and not s.startswith((';','#')):
            key,value=s.split('=',1);found[key.strip().lower()]=value.strip()
    return found


def remove_owned(raw, original, settings, kind):
    text,encoding,bom=decode(raw)
    begin='; HSHO BEGIN '+kind;end='; HSHO END '+kind
    pattern=r'(?:\r?\n)?'+re.escape(begin)+r'\r?\n(.*?)'+re.escape(end)+r'(?:\r?\n)?'
    count=0
    for match in list(re.finditer(pattern,text,flags=re.S))[::-1]:
        if match[1].replace('\r\n','\n').strip('\n') != settings.replace('\r\n','\n').strip('\n'):
            continue
        prefix,suffix=text[:match.start()],text[match.end():]
        separator='\r\n' if prefix and suffix and not prefix.endswith(('\r','\n')) and not suffix.startswith(('\r','\n')) else ''
        text=prefix+separator+suffix;count+=1
    if not count:
        text=''.join(line for line in text.splitlines(keepends=True) if line.strip() not in (begin,end))
    if not count:
        # Legacy releases appended a fixed block without an end marker.
        candidates=[settings,settings.replace('\r\n','\n')]
        for block in candidates:
            if block in text:
                text=text.replace(block,'',1);count=1;break
    if not count:
        # UE can rewrite comments/spacing. Remove only the last owned value
        # when it still matches the value we set; keep conflicting edits.
        wanted=values(settings);baseline=values(decode(original)[0]) if original is not None else {}
        lines=text.splitlines(keepends=True);section='';matches={}
        for i,line in enumerate(lines):
            s=line.strip()
            if s.startswith('[') and s.endswith(']'):section=s.lower()
            elif section=='[systemsettings]' and '=' in s and not s.startswith((';','#')):
                key,value=s.split('=',1);key=key.strip().lower()
                if key in wanted:matches[key]=(i,value.strip())
        restored={}
        for key,(i,value) in matches.items():
            if value==wanted[key]:
                lines[i]=''
                if key in baseline:restored[key]=baseline[key]
        text=''.join(lines)
        remaining=values(text)
        restored={k:v for k,v in restored.items() if k not in remaining}
        if restored:text+='\r\n[SystemSettings]\r\n'+''.join(k+'='+v+'\r\n' for k,v in restored.items())
    return bom+text.encode(encoding,errors='surrogateescape')


def manage(config,kind,settings,enabled):
    config=Path(config);target=config/'Engine.ini'
    stem='Engine.ini.hsho-'+kind
    state=config/(stem+'.json');backup=config/(stem+'.bak')
    config.mkdir(parents=True,exist_ok=True)
    raw=target.read_bytes() if target.exists() else b''
    saved=None
    if state.exists():
        try:saved=json.loads(state.read_text())
        except (ValueError,UnicodeError):pass
    if state.exists() or backup.exists():
        original=backup.read_bytes() if backup.exists() else None
        intact=(isinstance(saved,dict) and original is not None and sha(original)==saved.get('original'))
        exact=intact and sha(raw)==saved.get('installed')
        if exact:
            raw=original
        else:
            # Keep evidence and backups even if the old metadata is damaged.
            archive=config/('backup-graphics-recovery-'+uuid.uuid4().hex)
            archive.mkdir()
            for p in [target,state,backup]:
                if p.exists():(archive/p.name).write_bytes(p.read_bytes())
            raw=remove_owned(raw,original if intact else None,settings,kind)
        if target.exists() or raw:atomic(target,raw)
        if exact and not saved.get('existed',True) and not raw:target.unlink(missing_ok=True)
        state.unlink(missing_ok=True);backup.unlink(missing_ok=True)
    if not enabled:return 'Launcher graphics entries removed; other settings kept.'
    existed=target.exists();original=target.read_bytes() if existed else b''
    text,encoding,bom=decode(original)
    body=settings.strip('\r\n')
    block='\r\n; HSHO BEGIN '+kind+'\r\n'+body+'\r\n; HSHO END '+kind+'\r\n'
    modified=original+block.encode(encoding,errors='surrogateescape')
    backup.write_bytes(original)
    try:
        atomic(target,modified)
        atomic(state,json.dumps({'version':3,'existed':existed,'original':sha(original),'installed':sha(modified)}).encode())
    except Exception:
        if existed:atomic(target,original)
        else:target.unlink(missing_ok=True)
        backup.unlink(missing_ok=True);state.unlink(missing_ok=True)
        raise
    return 'Launcher graphics settings applied.'
