"""Read the display name cached for Steam's active local account only."""
from pathlib import Path
import re


def parse_vdf(text):
    text=re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*',lambda m: '' if m[0].startswith('//') else m[0],text)
    tokens=re.findall(r'"((?:\\.|[^"\\])*)"|([{}])',text)
    root={};stack=[root];pending=None
    for quoted,brace in tokens:
        if brace=='{':
            if pending is None:raise ValueError('Invalid Steam configuration')
            child={};stack[-1][pending]=child;stack.append(child);pending=None
        elif brace=='}':
            if pending is not None or len(stack)==1:raise ValueError('Invalid Steam configuration')
            stack.pop()
        elif quoted or not brace:
            # Skip comment matches; empty quoted strings still count as values.
            value=re.sub(r'\\(["\\])',r'\1',quoted)
            if pending is None:pending=value
            else:stack[-1][pending]=value;pending=None
    if len(stack)!=1 or pending is not None:raise ValueError('Invalid Steam configuration')
    return root


def clean_name(value):
    if not isinstance(value,str) or not value.strip() or len(value)>128 or any(ord(c)<32 or ord(c)==127 for c in value):
        raise ValueError('Steam display name unavailable. Open Steam and sign in first.')
    return value


def cached_name(steam_path, active_user):
    if type(active_user) is not int or active_user<=0:
        raise ValueError('Open Steam and sign in before starting the game.')
    root=Path(steam_path)
    local=root/'userdata'/str(active_user)/'config/localconfig.vdf'
    if local.is_file():
        try:
            config=parse_vdf(local.read_text(encoding='utf-8-sig'))
            value=config['UserLocalConfigStore']['friends']['PersonaName']
            return clean_name(value)
        except (KeyError,ValueError,UnicodeError):pass
    config=parse_vdf((root/'config/loginusers.vdf').read_text(encoding='utf-8-sig'))
    account=config['users'].get(str(76561197960265728+active_user),{})
    return clean_name(account.get('PersonaName'))


def current_name():
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam') as key:
        steam_path=winreg.QueryValueEx(key,'SteamPath')[0]
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam\ActiveProcess') as key:
        active_user=winreg.QueryValueEx(key,'ActiveUser')[0]
    return cached_name(steam_path,active_user)


def local_player_id(account_id):
    """Local profile key only; does not validate a Steam account or ticket."""
    import hashlib
    if type(account_id) is not int or account_id<=0:raise ValueError('No active Steam account')
    return 'local-'+hashlib.sha256(('hsho-local-profile-v1:'+str(account_id)).encode()).hexdigest()[:24]


def current_local_player_id():
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam\ActiveProcess') as key:
        active_user=winreg.QueryValueEx(key,'ActiveUser')[0]
    return local_player_id(active_user)
