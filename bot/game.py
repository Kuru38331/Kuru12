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
}

class GameError(Exception):
    pass

class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS players(id INTEGER PRIMARY KEY, gems INTEGER NOT NULL DEFAULT 1000, daily INTEGER NOT NULL DEFAULT -1, pity INTEGER NOT NULL DEFAULT 0, active TEXT NOT NULL DEFAULT 'knight');
        CREATE TABLE IF NOT EXISTS units(player INTEGER, unit TEXT, copies INTEGER NOT NULL, PRIMARY KEY(player,unit));
        ''')
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(players)')}
        if 'pity4' not in columns:
            with self.db:
                self.db.execute('ALTER TABLE players ADD COLUMN pity4 INTEGER NOT NULL DEFAULT 0')

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

    def guarantees(self, uid):
        self.profile(uid)
        return self.db.execute('SELECT pity,pity4 FROM players WHERE id=?',(uid,)).fetchone()

    def pull(self, uid, rng=random):
        return self.pull_many(uid,1,rng)[0]

    def pull_many(self, uid, count, rng=random):
        if type(count) is not int or count not in (1,10):
            raise GameError('เลือกสุ่มได้ครั้งละ 1 หรือ 10 ครั้ง')
        with self.db:
            self.ensure(uid)
            gems,pity,pity4 = self.db.execute('SELECT gems,pity,pity4 FROM players WHERE id=?',(uid,)).fetchone()
            if gems < count*100:
                raise GameError(f'เพชรไม่พอ ต้องใช้ {count*100:,} เพชร ลองรับ /daily ก่อน')
            units = []
            for _ in range(count):
                roll = rng.random()
                rarity = 5 if pity >= 49 or roll < .02 else 4 if pity4 >= 9 or roll < .12 else 3
                unit = rng.choice([k for k,v in CATALOG.items() if v[1] == rarity])
                pity = 0 if rarity == 5 else pity+1
                pity4 = 0 if rarity >= 4 else pity4+1
                self.db.execute('INSERT INTO units VALUES(?,?,1) ON CONFLICT(player,unit) DO UPDATE SET copies=copies+1',(uid,unit))
                units.append(unit)
            self.db.execute('UPDATE players SET gems=gems-?,pity=?,pity4=? WHERE id=?',(count*100,pity,pity4,uid))
        return units

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

class Battle:
    def __init__(self, first, second, store, rng=random):
        if first == second:
            raise GameError('ท้าตัวเองไม่ได้')
        self.fighters = []
        for uid in (first,second):
            unit = store.profile(uid)[2]
            _,_,hp,attack = CATALOG[unit]
            self.fighters.append(Fighter(uid,unit,hp,attack))
        self.turn = rng.randrange(2)
        self.finished = False
        self.winner = None
        self.rounds = 0

    def act(self, uid, action):
        if self.finished:
            raise GameError('การต่อสู้จบแล้ว')
        actor,target = self.fighters[self.turn],self.fighters[1-self.turn]
        if actor.uid != uid:
            raise GameError('ยังไม่ถึงตาของคุณ')
        if action not in ('attack','skill','guard','surrender'):
            raise GameError('คำสั่งไม่ถูกต้อง')
        if action == 'skill' and actor.cooldown:
            raise GameError(f'สกิลรออีก {actor.cooldown} เทิร์นของคุณ')
        if action == 'skill' and actor.mana < 20:
            raise GameError('มานาไม่พอ ต้องใช้ 20 MP')
        if action == 'surrender':
            self.finished, self.winner = True,target.uid
            return 'ยอมแพ้'
        actor.guard = False
        actor.cooldown = max(0,actor.cooldown-1)
        if action == 'guard':
            actor.guard = True
            actor.mana = min(100,actor.mana+15)
            text = 'ตั้งรับ ลดความเสียหายครั้งถัดไป 50% และฟื้น 15 MP'
        else:
            damage = actor.attack * (2 if action == 'skill' else 1)
            if target.guard:
                damage //= 2
            target.guard = False
            target.hp = max(0,target.hp-damage)
            if action == 'skill':
                actor.cooldown = 2
                actor.mana -= 20
            else:
                actor.mana = min(100,actor.mana+10)
            text = f'{"ใช้สกิล" if action == "skill" else "โจมตี"} ทำความเสียหาย {damage}'
        self.rounds += 1
        if target.hp == 0:
            self.finished,self.winner = True,actor.uid
        elif self.rounds >= 100:
            self.finished = True
            text += ' • ครบ 100 เทิร์น เสมอ'
        else:
            self.turn = 1-self.turn
        return text
