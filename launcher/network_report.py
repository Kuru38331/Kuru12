"""Read-only Windows checks. Socket presence is not a successful multiplayer test."""
import hashlib
import json
from pathlib import Path
import subprocess

SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$gameProcesses = @(Get-Process -Name 'HSHO-Win64-Shipping' -ErrorAction SilentlyContinue)
$steamProcesses = @(Get-Process -Name 'steam' -ErrorAction SilentlyContinue)
$gameIds = @($gameProcesses | ForEach-Object { $_.Id })
$udpPorts = @(); $tcpPorts = @(); $socketCheck = $true
try {
 $udpPorts = @(Get-NetUDPEndpoint -ErrorAction Stop | Where-Object { $gameIds -contains $_.OwningProcess } | Select-Object -ExpandProperty LocalPort -Unique)
 $tcpPorts = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $gameIds -contains $_.OwningProcess } | Select-Object -ExpandProperty LocalPort -Unique)
} catch { $socketCheck = $false }
[pscustomobject]@{game_running=($gameIds.Count -gt 0); steam_running=($steamProcesses.Count -gt 0); socket_check_available=$socketCheck; udp_ports=$udpPorts; tcp_listen_ports=$tcpPorts} | ConvertTo-Json -Compress
'''


def sanitize(raw):
    result={name:raw.get(name) is True for name in ('game_running','steam_running','socket_check_available')}
    for name in ('udp_ports','tcp_listen_ports'):
        values=raw.get(name,[])
        if type(values) is int:values=[values]
        if not isinstance(values,list):values=[]
        result[name]=sorted({p for p in values if type(p) is int and 0<p<=65535})
    return result


def report(game, root):
    game,root=Path(game),Path(root)
    completed=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',SCRIPT],capture_output=True,text=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if completed.returncode:
        raise ValueError('Windows network status could not be read; no settings changed')
    data=sanitize(json.loads(completed.stdout))
    exe=game/'HSHO/Binaries/Win64/HSHO-Win64-Shipping.exe'
    data['shipping_sha256']=hashlib.sha256(exe.read_bytes()).hexdigest()
    appids=[]
    for path in (game/'steam_appid.txt',game/'HSHO/Binaries/Win64/steam_appid.txt'):
        if path.is_file():
            value=path.read_text(errors='replace').strip()
            if value.isascii() and value.isdigit() and len(value)<=12:appids.append(value)
    data['local_app_ids']=sorted(set(appids))
    data['same_machine_app_id_conflict']=len(data['local_app_ids'])>1
    data['multiplayer_verified']=False
    data['note']='Game socket presence does not verify lobby invitation, peer connection, match start or match completion.'
    (root/'network-report.json').write_text(json.dumps(data,indent=2)+'\n')
    return json.dumps(data,indent=2)
