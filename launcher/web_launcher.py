"""Loopback-only browser launcher. Uses standard Python; no Tk dependency."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
import zipfile
from core import ROOT

RELEASE=json.loads((ROOT/'version.json').read_text())['version']

def patch_fingerprint(game):
    result=[]
    for bundle in [ROOT,ROOT/'mewmew',ROOT/'perks',ROOT/'curse-relic']:
        for row in json.loads((bundle/'patches.json').read_text())['files']:
            p=game/row['path'];actual=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
            result.append({'file':row['path'],'matches':actual==row['installed'],'sha256':actual})
    return result


class Session:
    def __init__(self):
        self.lock=threading.Lock();self.process=None;self.busy=False;self.status='พร้อมตรวจไฟล์และเปิดเกม';self.game_process=None
    def settings(self):
        p=ROOT/'launcher-settings.json'
        try:return json.loads(p.read_text()) if p.exists() else {}
        except (ValueError,UnicodeError):return {}
    def health(self):
        try:
            with urllib.request.urlopen('http://127.0.0.1:18080/health',timeout=.5) as r:return json.load(r).get('enabled') is True
        except (OSError,ValueError):return False
    def start(self,body):
        game=Path(body.get('game',''));low=body.get('low_spec') is True;fog=body.get('no_fog') is True
        if not (game/'HSHO.exe').is_file():raise ValueError('เลือกโฟลเดอร์ที่มี HSHO.exe ให้ถูกต้อง')
        if self.process and self.process.poll() is None:
            raise ValueError('เกมถูกเปิดผ่านแอปนี้แล้ว กรุณากลับไปที่หน้าต่างเกม')
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',18080))==0:raise ValueError('เซิร์ฟเวอร์ชุดเดิมยังเปิดอยู่ กรุณาปิด Launcher เดิมก่อน')
        from steam_name import current_name,current_local_player_id
        display=current_name();local_id=current_local_player_id()
        from automatic_patches import apply_all
        from fog import configure
        from low_spec import default_config
        self.status='กำลังตรวจและติดตั้งแพตช์ที่รวมมาให้…'
        apply_all(game);configure(default_config(),low,fog)
        settings={'game':str(game),'low_spec':low,'no_fog':fog}
        (ROOT/'launcher-settings.json').write_text(json.dumps(settings))
        env=os.environ.copy();env['HSHO_LOCAL_DISPLAY_NAME']=display;env['HSHO_LOCAL_PLAYER_ID']=local_id
        from player_profiles import state_path
        player_save=state_path(local_id)
        with (ROOT/'server-console.log').open('ab') as output:
            self.process=subprocess.Popen(([sys.executable,'--local-server'] if getattr(sys,'frozen',False) else [sys.executable,str(ROOT/'server/server.py')])+['--local-profile-experiment','--character-state-file',str(player_save)],cwd=ROOT/'server',env=env,stdout=output,stderr=output,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for _ in range(50):
            if self.process.poll() is not None:break
            if self.health():
                command=[str(game/'HSHO.exe')]
                if low:command+=['-ResX=1280','-ResY=720','-Windowed','-ForceRes']
                try:self.game_process=subprocess.Popen(command,cwd=game)
                except Exception:self.stop();raise
                self.status='เปิดเกมแล้ว — '+display+' · เปิด Launcher นี้ค้างไว้ระหว่างเล่น';return
            time.sleep(.1)
        self.stop();raise ValueError('เซิร์ฟเวอร์เปิดไม่สำเร็จ กดส่งรายงานปัญหา')
    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill()
    def launch(self,body):
        with self.lock:
            if self.busy:return
            self.busy=True
        def worker():
            try:self.start(body)
            except Exception as exc:self.status=str(exc)
            finally:self.busy=False
        threading.Thread(target=worker,daemon=True).start()
    def diagnostic(self):
        from network_report import report
        settings=self.settings();game=Path(settings.get('game',''))
        try:network=json.loads(report(game,ROOT))
        except Exception:network={'available':False}
        from server_summary import safe_observations
        records=safe_observations(ROOT/'server/observations.jsonl')
        # No account names, ids, session tokens, raw request bodies, or addresses.
        data={'release':RELEASE,'local_server_running':self.health(),'network':network,'patches':patch_fingerprint(game),'observations':records,'multiplayer_verified':False,'checks':['All players should use this release and separate Steam accounts','Test joiners one at a time with an empty host lobby']}
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('friend-report.json',json.dumps(data,indent=2))
        return out.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,code,data,kind='application/json'):
        raw=json.dumps(data,ensure_ascii=False).encode() if kind=='application/json' else data
        self.send_response(code);self.send_header('Content-Type',kind+'; charset=utf-8' if kind.startswith('text/') else kind)
        self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers();self.wfile.write(raw)
    def allowed(self):return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
    def do_GET(self):
        if not self.allowed():return self.reply(403,{'error':'host'})
        if self.path=='/':
            page=(ROOT/'launcher.html').read_text(encoding='utf-8').replace('__TOKEN__',self.server.token).replace('__RELEASE__',RELEASE)
            return self.reply(200,page.encode(),'text/html')
        if self.headers.get('X-Launcher-Token')!=self.server.token:return self.reply(403,{'error':'token'})
        if self.path=='/api/status':return self.reply(200,{'busy':self.server.session.busy,'status':self.server.session.status,'server':self.server.session.health(),'settings':self.server.session.settings()})
        self.reply(404,{'error':'not_found'})
    def do_POST(self):
        if not self.allowed() or self.headers.get('X-Launcher-Token')!=self.server.token:return self.reply(403,{'error':'token'})
        if self.headers.get('Origin') not in (None,f'http://127.0.0.1:{self.server.server_port}'):return self.reply(403,{'error':'origin'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<0 or length>131072:raise ValueError()
            body=json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(body,dict):raise ValueError()
            if self.path=='/api/play':
                self.server.session.launch(body);return self.reply(200,{'ok':True})
            if self.path=='/api/import':
                if self.server.session.busy or (self.server.session.process and self.server.session.process.poll() is None):
                    raise ValueError('ปิดเกมและเปิด Launcher ใหม่ก่อนนำเข้าเซฟ')
                from steam_name import current_local_player_id
                from player_profiles import import_selection
                import_selection(body.get('selection'),current_local_player_id())
                return self.reply(200,{'ok':True})
            if self.path=='/api/diagnose':
                data=self.server.session.diagnostic();return self.reply(200,data,'application/zip')
            if self.path=='/api/exit':
                if self.server.session.busy:raise ValueError('กำลังทำงาน กรุณารอ')
                self.reply(200,{'ok':True});threading.Thread(target=self.server.shutdown,daemon=True).start();return
            self.reply(404,{'error':'not_found'})
        except Exception as exc:self.reply(400,{'error':str(exc)})


def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.session=Session();server.token=secrets.token_hex(24)
    url=f'http://127.0.0.1:{server.server_port}/'
    server.session.busy=True
    def update():
        try:
            server.session.status='กำลังตรวจอัปเดตจาก GitHub…'
            from github_updates import check_and_stage,install_after_exit
            result=check_and_stage(ROOT)
            if result:
                server.session.status='กำลังติดตั้งรุ่นใหม่และเปิดแอปอีกครั้ง…'
                install_after_exit(ROOT,*result);server.shutdown();return
            server.session.status='พร้อมเล่น · เป็นรุ่นล่าสุดแล้ว'
        except Exception:
            server.session.status='ตรวจอัปเดตไม่ได้ ขณะนี้ยังเล่นด้วยรุ่นที่ติดตั้งอยู่ได้'
        finally:server.session.busy=False
    threading.Thread(target=update,daemon=True).start()
    webbrowser.open(url)
    try:server.serve_forever()
    finally:server.session.stop();server.server_close()

if __name__=='__main__':
    if '--local-server' in sys.argv:
        import runpy
        sys.path.insert(0,str(ROOT/'server'))
        sys.argv=[str(ROOT/'server/server.py')]+sys.argv[2:]
        runpy.run_path(str(ROOT/'server/server.py'),run_name='__main__')
    else:main()

