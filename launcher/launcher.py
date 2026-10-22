"""Single-window launcher for the existing HSHO local test."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import urllib.request
from core import ROOT, install, remove, import_profile


class App:
    def __init__(self, window):
        self.window=window;self.process=None;self.busy=False;self.events=queue.Queue();self.server_ready=False
        window.title('Kuru12 Launcher');window.geometry('900x560');window.resizable(False,False);window.configure(bg='#101115')
        window.option_add('*Font',('Segoe UI',10))
        config=ROOT/'launcher-settings.json'
        data=json.loads(config.read_text()) if config.exists() else {}
        self.path=tk.StringVar(value=data.get('game',r'D:\Program Files (x86)\Steam\steamapps\common\HSHO'))
        self.low=tk.BooleanVar(value=data.get('low_spec',False));self.no_fog=tk.BooleanVar(value=data.get('no_fog',False))
        self.status=tk.StringVar(value='กำลังเตรียม Launcher…');self.buttons=[]
        sidebar=tk.Frame(window,bg='#111216',width=356,height=560);sidebar.place(x=0,y=0)
        logo=tk.Canvas(sidebar,width=285,height=193,bg='#111216',highlightthickness=0);logo.place(x=35,y=17)
        logo.create_line(56,20,224,83,fill='#641b20',width=5);logo.create_line(219,22,50,99,fill='#8f2625',width=6)
        logo.create_text(140,94,text='HSHO',fill='#bc392f',font=('Segoe UI',47,'bold italic'))
        logo.create_rectangle(90,147,195,174,fill='#713c8d',outline='')
        logo.create_text(142,160,text='KURU12',fill='#ffffff',font=('Segoe UI',12,'bold'))
        tk.Label(sidebar,text='FRIENDS EDITION',bg='#111216',fg='#526174',font=('Consolas',9)).place(x=37,y=214)
        tk.Label(sidebar,text='READY TO PLAY',bg='#111216',fg='#ffb125',font=('Segoe UI',10,'bold')).place(x=37,y=260)
        self.local_status=tk.Label(sidebar,text='LOCAL OFFLINE',bg='#2a1b20',fg='#df696a',font=('Consolas',8),padx=7,pady=3)
        self.local_status.place(x=212,y=259)
        tk.Frame(sidebar,bg='#25262c',height=5,width=282).place(x=37,y=290)
        tk.Label(sidebar,textvariable=self.status,bg='#111216',fg='#9ba7b8',wraplength=280,justify='left',font=('Segoe UI',9)).place(x=37,y=305,width=282,height=47)
        for y,label,color,callback in [(365,'START GAME','#10b68b',self.play),(424,'CHECK CONNECTION','#d98600',self.network),(483,'SETTINGS','#0795b4',self.settings)]:
            button=tk.Button(sidebar,text=label,command=callback,bg=color,fg='#ffffff',activebackground=color,activeforeground='white',relief='flat',borderwidth=0,font=('Segoe UI',11,'bold'),cursor='hand2')
            button.place(x=37,y=y,width=282,height=46);self.buttons.append(button)
        version=json.loads((ROOT/'version.json').read_text())['version']
        tk.Label(sidebar,text='v'+version,bg='#111216',fg='#536071',font=('Consolas',8)).place(x=37,y=539)
        scene=tk.Canvas(window,width=544,height=560,bg='#102331',highlightthickness=0);scene.place(x=356,y=0)
        # Original stylized night scene; optional artwork can replace it later.
        import random
        rng=random.Random(12)
        for y in range(0,560,4):
            t=y/560;color='#%02x%02x%02x'%(int(27-20*t),int(48-26*t),int(64-32*t))
            scene.create_rectangle(0,y,544,y+4,fill=color,outline='')
        scene.create_oval(330,30,430,130,fill='#58717c',outline='');scene.create_oval(347,24,442,119,fill='#1b3040',outline='')
        for layer,color in [(0,'#17313d'),(1,'#102631'),(2,'#081923')]:
            for i in range(10):
                x=rng.randint(-40,570);height=rng.randint(130,340)+layer*25;bottom=440+layer*45
                scene.create_polygon(x-62,bottom,x,bottom-height,x+65,bottom,fill=color,outline='')
                scene.create_rectangle(x-5,bottom-80,x+6,560,fill=color,outline='')
        for _ in range(35):
            x,y=rng.randrange(540),rng.randrange(170,460);scene.create_oval(x,y,x+2,y+2,fill='#4d8991',outline='')
        scene.create_text(35,57,text='HOME SWEET HOME',anchor='w',fill='#d6e3e9',font=('Segoe UI',16,'bold'))
        scene.create_text(35,87,text='A NIGHT WITH FRIENDS',anchor='w',fill='#82a2b6',font=('Consolas',9))
        scene.create_text(510,531,text='KURU12  /  COMMUNITY LAUNCHER',anchor='e',fill='#527080',font=('Consolas',8))
        self.welcome=tk.Label(window,text='STEAM · กำลังตรวจบัญชี…',bg='#242a30',fg='#e5edf3',font=('Segoe UI',10,'bold'),padx=14,pady=12)
        self.welcome.place(x=580,y=18,width=300,height=46)
        self.log=tk.Text(window,bg='#0b0e13',fg='#9ba8b9',font=('Consolas',9),relief='solid',borderwidth=1,wrap='word',state='disabled')
        self.log.place(x=392,y=399,width=473,height=115)
        self.append_log('Launcher '+version+' · ready')
        window.protocol('WM_DELETE_WINDOW',self.close);window.after(100,self.poll);window.after(200,self.check_updates)
        def profile():
            try:
                from steam_name import current_name
                self.events.put(('profile','Welcome back, '+current_name()))
            except Exception:self.events.put(('profile','STEAM · กรุณาเปิด Steam และล็อกอิน'))
        threading.Thread(target=profile,daemon=True).start()

    def append_log(self,text):
        self.log.configure(state='normal');self.log.insert('end',time.strftime('[%H:%M:%S] ')+str(text)+'\n');self.log.see('end');self.log.configure(state='disabled')

    def settings(self):
        dialog=tk.Toplevel(self.window);dialog.title('Settings');dialog.geometry('590x350');dialog.configure(bg='#111216');dialog.transient(self.window)
        tk.Label(dialog,text='โฟลเดอร์เกมที่มี HSHO.exe',bg='#111216',fg='white').pack(anchor='w',padx=20,pady=(20,8))
        line=tk.Frame(dialog,bg='#111216');line.pack(fill='x',padx=20)
        tk.Entry(line,textvariable=self.path).pack(side='left',fill='x',expand=True);tk.Button(line,text='เลือกโฟลเดอร์',command=self.browse).pack(side='right')
        for label,var in [('โหมดสเปคต่ำ · 720p / 30 FPS',self.low),('ปิดหมอก',self.no_fog)]:
            tk.Checkbutton(dialog,text=label,variable=var,bg='#111216',fg='white',selectcolor='#29374c',activebackground='#111216',activeforeground='white').pack(anchor='w',padx=20,pady=8)
        for label,callback in [('นำเข้าเซฟเก่าของฉัน',self.migrate),('วิธีเล่นกับเพื่อน',self.friends),('ดูผลคำขอจากเกม',self.progress)]:
            tk.Button(dialog,text=label,command=callback).pack(fill='x',padx=20,pady=3)
        def save():
            (ROOT/'launcher-settings.json').write_text(json.dumps({'game':self.path.get(),'low_spec':self.low.get(),'no_fog':self.no_fog.get()}));dialog.destroy()
        tk.Button(dialog,text='บันทึก',command=save,bg='#10b68b',fg='white').pack(pady=10)

    def check_updates(self):
        def action():
            from github_updates import check_and_stage,install_after_exit
            try:
                update=check_and_stage(ROOT)
            except Exception:
                return 'ตรวจอัปเดตไม่ได้ · ยังเล่นด้วยรุ่นที่ติดตั้งอยู่ได้'
            if update:
                install_after_exit(ROOT,*update)
                self.events.put(('restart',''))
                return 'กำลังติดตั้งรุ่นใหม่และเปิด Launcher อีกครั้ง…'
            return 'พร้อมเล่น · เป็นรุ่นล่าสุดแล้ว'
        self.run(action)

    def browse(self):
        value=filedialog.askdirectory(title='Select folder containing HSHO.exe')
        if value:self.path.set(value)

    def run(self,action):
        if self.busy:return
        self.busy=True
        for b in self.buttons:b.config(state='disabled')
        self.status.set('กำลังทำงาน…')
        def worker():
            try:self.events.put(('done',action()))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        try:
            while True:
                kind,text=self.events.get_nowait()
                if kind=='profile':
                    self.welcome.configure(text=text);continue
                if kind=='restart':
                    self.stop();self.window.destroy();return
                if kind=='network':
                    messagebox.showinfo('สถานะเครือข่าย',text)
                    continue
                self.busy=False
                for b in self.buttons:b.config(state='normal')
                self.status.set(text)
                self.append_log(text)
                if kind=='error':messagebox.showerror('HSHO',text)
        except queue.Empty:pass
        self.local_status.configure(text='LOCAL ONLINE' if self.server_ready else 'LOCAL OFFLINE',bg='#103c31' if self.server_ready else '#2a1b20',fg='#50d4ac' if self.server_ready else '#df696a')
        self.window.after(100,self.poll)

    def prepare(self):
        game=Path(self.path.get())
        self.run(lambda:install(game))

    def play(self):
        game=Path(self.path.get())
        low_enabled=self.low.get()
        no_fog=self.no_fog.get()
        def start():
            if not (game/'HSHO.exe').is_file():raise ValueError('Select the folder containing HSHO.exe')
            if self.process and self.process.poll() is None:
                return 'เซิร์ฟเวอร์กำลังทำงานอยู่ เปิดเกมจากหน้าต่างที่เปิดแล้ว'
            # Do not take over an old server which may contain different state/code.
            import socket
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1',18080))==0:
                    raise ValueError('Port 18080 is in use. Stop the old Local Test server first.')
            from steam_name import current_name, current_local_player_id
            steam_display_name=current_name()
            from automatic_patches import apply_all
            apply_all(game)
            (ROOT/'launcher-settings.json').write_text(json.dumps({'game':str(game),'low_spec':low_enabled,'no_fog':no_fog}))
            from low_spec import default_config
            from fog import configure
            configure(default_config(),low_enabled,no_fog)
            child_env=os.environ.copy()
            child_env['HSHO_LOCAL_DISPLAY_NAME']=steam_display_name
            child_env['HSHO_LOCAL_PLAYER_ID']=current_local_player_id()
            from player_profiles import state_path
            player_save=state_path(child_env['HSHO_LOCAL_PLAYER_ID'])
            output=(ROOT/'server-console.log').open('ab')
            try:
                self.process=subprocess.Popen(([sys.executable,'--local-server'] if getattr(sys,'frozen',False) else [sys.executable,str(ROOT/'server/server.py')])+['--local-profile-experiment','--character-state-file',str(player_save)],cwd=ROOT/'server',env=child_env,stdout=output,stderr=output,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            finally:output.close()
            ready=False
            for _ in range(30):
                if self.process.poll() is not None:break
                try:
                    with urllib.request.urlopen('http://127.0.0.1:18080/health',timeout=.3) as response:
                        ready=json.load(response).get('enabled') is True
                    if ready:break
                except (OSError,ValueError):pass
                time.sleep(.1)
            if not ready:
                self.stop()
                raise ValueError('Local server failed to start. See server-console.log.')
            self.server_ready=True
            try:
                command=[str(game/'HSHO.exe')]
                if low_enabled:command += ['-ResX=1280','-ResY=720','-Windowed','-ForceRes']
                subprocess.Popen(command,cwd=game)
            except Exception:
                self.stop();raise
            return 'เปิดเกมแล้ว — เปิด Steam ไว้ และคงแอปนี้ไว้ระหว่างเล่น'
        self.run(start)

    def migrate(self):
        source=filedialog.askopenfilename(title='Select old local-character-state.json',filetypes=[('Saved characters','local-character-state.json')])
        if not source:return
        if self.process and self.process.poll() is None:
            messagebox.showinfo('HSHO','Close the launcher and reopen before importing.');return
        def action():
            from steam_name import current_local_player_id
            from player_profiles import state_path
            import_profile(source,state_path(current_local_player_id()))
            return 'นำเข้าตัวละครและสกินที่บันทึกแล้ว'
        self.run(action)

    def mew_change(self, undo):
        if self.process and self.process.poll() is None:
            messagebox.showinfo('HSHO','Close the game and reopen the launcher before changing this patch.');return
        game=Path(self.path.get())
        def action():
            if undo:return remove(game,state_name='.hsho-mewmew-test')
            install(game,bundle=ROOT/'mewmew',state_name='.hsho-mewmew-test')
            return 'Mewmew local test installed: heal radius x2; movement unlock. Restart game to test.'
        self.run(action)

    def mew_on(self):self.mew_change(False)

    def mew_off(self):self.mew_change(True)

    def speed_change(self, remove):
        if self.process and self.process.poll() is None:
            messagebox.showinfo('HSHO','Close the game and reopen this launcher before changing the Aisha patch.');return
        game=Path(self.path.get())
        def action():
            from aisha_speed import change
            return change(game,remove=remove)
        self.run(action)

    def speed_on(self):self.speed_change(False)

    def speed_off(self):self.speed_change(True)

    def restore_graphics(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo('HSHO','Close the game and reopen this launcher before restoring graphics.');return
        def action():
            from low_spec import restore, default_config
            from fog import restore as restore_fog
            restore_fog(default_config())
            return restore(default_config())
        self.run(action)

    def friends(self):
        messagebox.showinfo('เล่นกับเพื่อน — ยังต้องทดสอบจริง',
            '1. ทั้งสองเครื่องใช้เกม build เดียวกัน และ Steam คนละบัญชี\n'
            '2. ทั้งคู่เปิดผ่าน Launcher นี้ เข้าเมนูหลักให้ได้ก่อน\n'
            '3. โฮสต์สร้างห้องกำหนดเองในเกม แล้วใช้เมนูเชิญเพื่อนเดิม\n'
            '4. เพื่อนรับคำเชิญ Steam ตรวจว่าเห็นผู้เล่นจริงสองคน\n'
            '5. เลือกตัว กดพร้อม เริ่มแมตช์ และตรวจว่าเห็นกันเดินได้\n'
            '6. จบแมตช์และกลับห้อง แล้วค่อยถือว่าทดสอบผ่าน\n\n'
            'นี่ใช้เส้นทาง Steam lobby/listen ที่พบในไฟล์เกม ไม่ใช่ระบบออนไลน์ที่ยืนยันแล้ว\n'
            'หากติดขั้นไหน กดตรวจเกม / Steam แล้วส่ง network-report.json กับภาพขั้นที่ติด\n'
            'ยังไม่ต้องตั้ง Tailscale หรือเปลี่ยน App ID')

    def network(self):
        game=Path(self.path.get())
        def check():
            from network_report import report
            result=report(game,ROOT)
            self.events.put(('network',result))
            return 'บันทึก network-report.json แล้ว (ไม่แก้การตั้งค่าเครือข่าย)'
        self.run(check)

    def progress(self):
        import sys
        sys.path.insert(0,str(ROOT/'server'))
        from check_progress import summarize
        messagebox.showinfo('ผลล่าสุด',summarize(ROOT/'server/observations.jsonl'))

    def restore(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo('HSHO','Close the game and reopen the launcher before restoring.');return
        game=Path(self.path.get());self.run(lambda:remove(game))

    def stop(self):
        self.server_ready=False
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill()

    def close(self):
        if self.busy:return
        self.stop();self.window.destroy()


if __name__=='__main__':
    if '--local-server' in sys.argv:
        import runpy
        sys.path.insert(0,str(ROOT/'server'))
        sys.argv=[str(ROOT/'server/server.py')]+sys.argv[2:]
        runpy.run_path(str(ROOT/'server/server.py'),run_name='__main__')
    else:
        window=tk.Tk();App(window);window.mainloop()

