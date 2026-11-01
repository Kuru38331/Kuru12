import json
import os
import random
import sqlite3
import time
from dataclasses import dataclass

CATALOG = {
    'knight': ('อัศวิน', 3, 140, 24),
    'mage': ('จอมเวท', 3, 100, 34),
    'ranger': ('นักธนู', 3, 120, 32),
    'paladin': ('พาลาดิน', 4, 170, 33),
    'dragon': ('ราชามังกร', 5, 180, 42),
    'kuru': ('Kuru', 5, 240, 0),
    'eiji': ('Eiji', 5, 170, 30),
    'yuko': ('Yuko Hanaka', 5, 190, 38),
    'mala': ('Mala Natsumi', 4, 155, 25),
}

BANNERS = ('standard','kuru','yuko')
FEATURED = {'kuru':'kuru','yuko':'yuko'}
ULTIMATES = {'kuru': {'name':'สุริยคราสพันผีเสื้อ','hp_percent':60,'energy_cost':100},
    'eiji': {'name':'นิทรรศการความทรงจำ','attack_multiplier':3,'energy_cost':100},
    'yuko': {'name':'สวนบุปผาส่งวิญญาณ','attack_multiplier':3,'energy_cost':100},
    'mala': {'name':'ซิมโฟนีคลื่นเสียง','attack_multiplier':3,'energy_cost':100}}

def banner_is_open(banner):
    return banner == 'standard' or os.getenv(banner.upper()+'_BANNER_OPEN','true').lower() not in ('false','0','no')

def skill_cost(unit):
    return 30 if unit == 'kuru' else 20

def skill_cooldown(unit):
    return 3 if unit == 'kuru' else 2

class GameError(Exception):
    pass

class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS players(id INTEGER PRIMARY KEY, gems INTEGER NOT NULL DEFAULT 1000, daily INTEGER NOT NULL DEFAULT -1, pity INTEGER NOT NULL DEFAULT 0, active TEXT NOT NULL DEFAULT 'knight');
        CREATE TABLE IF NOT EXISTS units(player INTEGER, unit TEXT, copies INTEGER NOT NULL, PRIMARY KEY(player,unit));
        CREATE TABLE IF NOT EXISTS admin_audit(request TEXT PRIMARY KEY, time INTEGER NOT NULL, actor INTEGER NOT NULL, guild INTEGER NOT NULL, target INTEGER NOT NULL, action TEXT NOT NULL, item TEXT NOT NULL, amount INTEGER NOT NULL, reason TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS squads(player INTEGER PRIMARY KEY, units TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS banner_pity(player INTEGER, banner TEXT, pity INTEGER NOT NULL DEFAULT 0, pity4 INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(player,banner));
        ''')
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(players)')}
        if 'pity4' not in columns:
            with self.db:
                self.db.execute('ALTER TABLE players ADD COLUMN pity4 INTEGER NOT NULL DEFAULT 0')

        banner_columns = {row[1] for row in self.db.execute('PRAGMA table_info(banner_pity)')}
        if 'featured' not in banner_columns:
            with self.db:
                self.db.execute('ALTER TABLE banner_pity ADD COLUMN featured INTEGER NOT NULL DEFAULT 0')
                # Honor the previous version's promised Kuru on existing banner saves.
                self.db.execute("UPDATE banner_pity SET featured=1 WHERE banner='kuru'")

    def ensure(self, uid):
        self.db.execute('INSERT OR IGNORE INTO players(id) VALUES(?)', (uid,))
        self.db.execute("INSERT OR IGNORE INTO units VALUES(?,'knight',1)", (uid,))

    def profile(self, uid):
        with self.db:
            self.ensure(uid)
        return self.db.execute('SELECT gems,pity,active FROM players WHERE id=?', (uid,)).fetchone()

    def collection(self, uid):
        self.profile(uid)
        return self.db.execute('SELECT unit,copies FROM units WHERE player=? ORDER BY unit', (uid,)).fetchall()

    def daily(self, uid, now=None):
        day = int(time.time() if now is None else now)//86400
        with self.db:
            self.ensure(uid)
            if not self.db.execute('UPDATE players SET gems=gems+300,daily=? WHERE id=? AND daily<?', (day,uid,day)).rowcount:
                raise GameError('รับรางวัลวันนี้แล้ว กลับมาใหม่หลัง 07:00 น. เวลาไทย')
        return 300

    def guarantees(self, uid, banner='standard'):
        self.profile(uid)
        if banner not in BANNERS:
            raise GameError('ไม่พบตู้กาชานี้')
        if banner == 'standard':
            return self.db.execute('SELECT pity,pity4 FROM players WHERE id=?',(uid,)).fetchone()
        row = self.db.execute('SELECT pity,pity4 FROM banner_pity WHERE player=? AND banner=?',(uid,banner)).fetchone()
        return row or (0,0)

    def featured_guaranteed(self,uid,banner):
        if banner not in FEATURED:
            return False
        row=self.db.execute('SELECT featured FROM banner_pity WHERE player=? AND banner=?',(uid,banner)).fetchone()
        return bool(row and row[0])

    def set_lineup(self,uid,units):
        if len(units)!=4 or len(set(units))!=4 or any(unit not in CATALOG for unit in units):
            raise GameError('ทีม 4v4 ต้องมีตัวละครที่ไม่ซ้ำกัน 4 ตัว')
        with self.db:
            self.ensure(uid)
            owned={row[0] for row in self.db.execute('SELECT unit FROM units WHERE player=?',(uid,))}
            if not set(units)<=owned:
                raise GameError('จัดทีมได้เฉพาะตัวละครที่คุณเป็นเจ้าของ')
            self.db.execute('INSERT INTO squads VALUES(?,?) ON CONFLICT(player) DO UPDATE SET units=excluded.units',(uid,json.dumps(units)))

    def lineup(self,uid):
        row=self.db.execute('SELECT units FROM squads WHERE player=?',(uid,)).fetchone()
        if not row:
            raise GameError('ยังไม่ได้จัดทีม 4 ตัว ใช้ /squad ก่อนท้า 4v4')
        units=json.loads(row[0])
        owned={unit for unit,_ in self.collection(uid)}
        if len(units)!=4 or len(set(units))!=4 or not set(units)<=owned or not set(units)<=CATALOG.keys():
            raise GameError('ทีมไม่สมบูรณ์ กรุณาจัดทีมด้วย /squad ใหม่')
        return units

    def pull(self, uid, rng=random, banner='standard'):
        return self.pull_many(uid,1,rng,banner=banner)[0]

    def pull_many(self, uid, count, rng=random, banner='standard'):
        if type(count) is not int or count not in (1,10):
            raise GameError('เลือกสุ่มได้ครั้งละ 1 หรือ 10 ครั้ง')
        if banner not in BANNERS:
            raise GameError('ไม่พบตู้กาชานี้')
        if not banner_is_open(banner):
            raise GameError('ตู้ Limited นี้ปิดแล้ว เพชรยังอยู่ครบ')
        with self.db:
            self.ensure(uid)
            gems,pity,pity4 = self.db.execute('SELECT gems,pity,pity4 FROM players WHERE id=?',(uid,)).fetchone()
            if banner != 'standard':
                self.db.execute('INSERT OR IGNORE INTO banner_pity(player,banner) VALUES(?,?)',(uid,banner))
                pity,pity4 = self.db.execute('SELECT pity,pity4 FROM banner_pity WHERE player=? AND banner=?',(uid,banner)).fetchone()
            featured=self.featured_guaranteed(uid,banner)
            if gems < count*100:
                raise GameError(f'เพชรไม่พอ ต้องใช้ {count*100:,} เพชร ลองรับ /daily ก่อน')
            units = []
            for _ in range(count):
                roll = rng.random()
                rarity = 5 if pity >= 49 or roll < .02 else 4 if pity4 >= 9 or roll < .12 else 3
                pool = [k for k,v in CATALOG.items() if v[1] == rarity and k not in FEATURED]
                if banner in FEATURED and rarity == 5:
                    won = featured or rng.random()<.5
                    pool = [FEATURED[banner] if won else 'eiji']
                    featured = not won
                unit = rng.choice(pool)
                pity = 0 if rarity == 5 else pity+1
                pity4 = 0 if rarity >= 4 else pity4+1
                self.db.execute('INSERT INTO units VALUES(?,?,1) ON CONFLICT(player,unit) DO UPDATE SET copies=copies+1',(uid,unit))
                units.append(unit)
            if banner == 'standard':
                self.db.execute('UPDATE players SET gems=gems-?,pity=?,pity4=? WHERE id=?',(count*100,pity,pity4,uid))
            else:
                self.db.execute('UPDATE players SET gems=gems-? WHERE id=?',(count*100,uid))
                self.db.execute('UPDATE banner_pity SET pity=?,pity4=?,featured=? WHERE player=? AND banner=?',(pity,pity4,int(featured),uid,banner))
        return units

    def admin_grant(self,request,actor,guild,target,action,amount=1,item='',reason='แอดมินแจกของ'):
        if action not in ('gems','character','team'):
            raise GameError('ประเภทของไม่ถูกต้อง')
        limit=1_000_000_000 if action=='gems' else 1000 if action=='character' else 1
        if type(amount) is not int or not 1<=amount<=limit:
            raise GameError(f'จำนวนต้องอยู่ระหว่าง 1 ถึง {limit:,}')
        if action=='character' and item not in CATALOG:
            raise GameError('ไม่พบตัวละครนี้')
        if not isinstance(reason,str) or len(reason)>200:
            raise GameError('เหตุผลยาวได้ไม่เกิน 200 ตัวอักษร')
        if action=='team':item='kuru,eiji,yuko,mala'
        if action=='gems':item='gems'
        with self.db:
            if self.db.execute('SELECT 1 FROM admin_audit WHERE request=?',(str(request),)).fetchone():
                raise GameError('คำสั่งนี้ดำเนินการแล้ว ไม่เพิ่มของซ้ำ')
            self.ensure(target)
            if action=='gems':
                balance=self.db.execute('SELECT gems FROM players WHERE id=?',(target,)).fetchone()[0]
                if balance+amount>1_000_000_000_000:
                    raise GameError('ยอดเพชรรวมเกินเพดาน 1 ล้านล้าน')
                self.db.execute('UPDATE players SET gems=gems+? WHERE id=?',(amount,target))
            else:
                units=['kuru','eiji','yuko','mala'] if action=='team' else [item]
                for unit in units:
                    count=self.db.execute('SELECT copies FROM units WHERE player=? AND unit=?',(target,unit)).fetchone()
                    if (count[0] if count else 0)+amount>1_000_000:
                        raise GameError('จำนวนสำเนาตัวละครเกินเพดาน')
                    self.db.execute('INSERT INTO units VALUES(?,?,?) ON CONFLICT(player,unit) DO UPDATE SET copies=copies+excluded.copies',(target,unit,amount))
                if action=='team':
                    self.db.execute('UPDATE players SET active=? WHERE id=?',('kuru',target))
                    self.db.execute('INSERT INTO squads VALUES(?,?) ON CONFLICT(player) DO UPDATE SET units=excluded.units',(target,json.dumps(units)))
            self.db.execute('INSERT INTO admin_audit VALUES(?,?,?,?,?,?,?,?,?)',(str(request),int(time.time()),actor,guild,target,action,item,amount,reason))

    def admin_history(self,guild):
        return self.db.execute('SELECT time,actor,target,action,item,amount FROM admin_audit WHERE guild=? ORDER BY time DESC,rowid DESC LIMIT 10',(guild,)).fetchall()

    def equip(self, uid, unit):
        with self.db:
            self.ensure(uid)
            if not self.db.execute('SELECT 1 FROM units WHERE player=? AND unit=?',(uid,unit)).fetchone():
                raise GameError('ยังไม่มีตัวละครนี้')
            self.db.execute('UPDATE players SET active=? WHERE id=?',(unit,uid))

@dataclass
class Fighter:
    uid: int
    unit: str
    hp: int
    attack: int
    guard: bool = False
    cooldown: int = 0
    mana: int = 100
    max_hp: int = 0
    stunned: int = 0
    energy: int = 0
    recorded: int = 0
    bleed: int = 0
    bleed_damage: int = 0

    def __post_init__(self):
        if self.max_hp == 0:
            self.max_hp = self.hp

class Battle:
    def __init__(self, first, second, store, rng=random):
        self._initialize(first,second,[[store.profile(uid)[2]] for uid in (first,second)],rng)

    def _initialize(self,first,second,lineups,rng):
        if first==second:
            raise GameError('ท้าตัวเองไม่ได้')
        self.owners=(first,second)
        self.fighters=[]
        for uid,units in zip(self.owners,lineups):
            for unit in units:
                _,_,hp,attack=CATALOG[unit]
                self.fighters.append(Fighter(uid,unit,hp,attack))
        size=len(lineups[0])
        starting_side=rng.randrange(2)
        self.order=[slot+size*side for slot in range(size) for side in (starting_side,1-starting_side)]
        self.turn=self.order[0]
        self.finished=False
        self.winner=None
        self.rounds=0
        self.limit=100 if size==1 else 200

    def enemies(self):
        actor=self.fighters[self.turn]
        return [i for i,fighter in enumerate(self.fighters) if fighter.uid!=actor.uid and fighter.hp>0]

    def _outcome(self):
        alive={f.uid for f in self.fighters if f.hp>0}
        if len(alive)<=1:
            self.finished=True
            self.winner=next(iter(alive),None)
        elif self.rounds>=self.limit:
            self.finished=True
        return self.finished

    def _damage(self,target,damage):
        lost=min(target.hp,max(0,damage))
        target.hp-=lost
        if lost and target.unit in ULTIMATES:
            target.energy=min(100,target.energy+10)
        if target.unit=='eiji':
            target.recorded=min(90,target.recorded+lost)
        return lost

    def _heal(self,actor,percent,allies=False):
        team=[f for f in self.fighters if f.uid==actor.uid and f.hp>0]
        targets=team if allies else [min(team,key=lambda f:f.hp/f.max_hp)]
        healed=0
        for fighter in targets:
            amount=min(fighter.max_hp-fighter.hp,max(1,fighter.max_hp*percent//100))
            fighter.hp+=amount
            healed+=amount
        return healed

    def _advance(self):
        notes=[]
        position=self.order.index(self.turn)
        while not self.finished:
            position=(position+1)%len(self.order)
            index=self.order[position]
            fighter=self.fighters[index]
            if fighter.hp<=0:
                continue
            if fighter.bleed:
                fighter.bleed-=1
                lost=self._damage(fighter,fighter.bleed_damage)
                notes.append(f'🌺 {CATALOG[fighter.unit][0]} เสีย {lost} HP จากฮิกังบาน')
                if self._outcome():break
                if fighter.hp<=0:continue
            if fighter.stunned:
                fighter.stunned-=1
                fighter.guard=False
                self.rounds+=1
                notes.append(f'🦋 สตั้น: {CATALOG[fighter.unit][0]} ข้าม 1 เทิร์น!')
                if self._outcome():break
                continue
            self.turn=index
            break
        return '\n'.join(notes)

    def act(self,uid,action,target_index=None):
        if self.finished:raise GameError('การต่อสู้จบแล้ว')
        actor=self.fighters[self.turn]
        if actor.uid!=uid:raise GameError('ยังไม่ถึงตาของคุณ')
        if action not in ('attack','skill','ultimate','guard','surrender'):
            raise GameError('คำสั่งไม่ถูกต้อง')
        enemies=self.enemies()
        if target_index is None:target_index=enemies[0]
        if type(target_index) is not int or target_index not in enemies:
            raise GameError('เลือกเป้าหมายที่ยังมีชีวิตอยู่จากทีมตรงข้าม')
        target=self.fighters[target_index]
        if action=='ultimate':
            if actor.unit not in ULTIMATES:raise GameError('ตัวละครนี้ยังไม่มีอันติ')
            if actor.energy<100:raise GameError('เกจอันติยังไม่เต็ม ต้องใช้พลัง 100')
        if action=='skill' and actor.cooldown:
            raise GameError(f'สกิลรออีก {actor.cooldown} เทิร์นของคุณ')
        if action=='skill' and actor.mana<skill_cost(actor.unit):
            raise GameError(f'มานาไม่พอ ต้องใช้ {skill_cost(actor.unit)} MP')
        if action=='surrender':
            self.finished=True
            self.winner=next(owner for owner in self.owners if owner!=uid)
            return 'ยอมแพ้ทั้งทีม'
        actor.guard=False
        actor.cooldown=max(0,actor.cooldown-1)
        if action=='guard':
            actor.guard=True
            actor.mana=min(100,actor.mana+15)
            text='ตั้งรับ ลดความเสียหายครั้งถัดไป 50% และฟื้น 15 MP'
        else:
            if action=='ultimate':
                config=ULTIMATES[actor.unit]
                damage=max(1,actor.max_hp*config['hp_percent']//100) if 'hp_percent' in config else actor.attack*config['attack_multiplier']
                actor.energy-=100
            elif actor.unit=='kuru':
                damage=max(1,actor.max_hp*(32 if action=='skill' else 16)//100)
            else:
                damage=actor.attack*(2 if action=='skill' else 1)
            if actor.unit=='eiji' and action in ('skill','ultimate'):
                damage+=actor.recorded if action=='ultimate' else actor.recorded//2
                actor.recorded=0
            if target.guard:damage//=2
            target.guard=False
            self._damage(target,damage)
            if action=='skill':
                actor.cooldown=skill_cooldown(actor.unit)
                actor.mana-=skill_cost(actor.unit)
                if actor.unit=='kuru' and target.hp>0:target.stunned=1
            elif action=='attack':actor.mana=min(100,actor.mana+10)
            label=f'🌘 อันติ {ULTIMATES[actor.unit]["name"]}' if action=='ultimate' else 'ใช้สกิล' if action=='skill' else 'โจมตี'
            text=f'{label} ใส่ {CATALOG[target.unit][0]} ทำความเสียหาย {damage}'
            if actor.unit=='yuko' and action in ('skill','ultimate') and target.hp>0:
                target.bleed=3 if action=='ultimate' else 2
                target.bleed_damage=max(1,target.max_hp*8//100)
                text+=' 🌺 แผลฮิกังบาน'
            if actor.unit=='mala' and action in ('skill','ultimate'):
                healed=self._heal(actor,18 if action=='ultimate' else 12,allies=action=='ultimate')
                text+=f' 🎵 ฟื้นฟูทีม {healed} HP'
        if actor.unit in ULTIMATES and action!='ultimate':
            actor.energy=min(100,actor.energy+{'attack':25,'skill':35,'guard':15}[action])
        self.rounds+=1
        if not self._outcome():
            notes=self._advance()
            if notes:text+='\n'+notes
        if self.finished and self.winner is None:text+=f' • ครบ {self.limit} เทิร์น เสมอ'
        return text

class TeamBattle(Battle):
    def __init__(self,first,second,store,rng=random):
        self._initialize(first,second,[store.lineup(uid) for uid in (first,second)],rng)
