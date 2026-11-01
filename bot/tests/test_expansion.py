import os
os.environ['GACHA_DB']=':memory:'
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import bot
from game import Store,Battle,TeamBattle,GameError,CATALOG,ULTIMATES
from presentation import character_embed,banner_embed

SQUAD=['kuru','eiji','yuko','mala']
class Fixed:
    def __init__(self,values=(.99,)):
        self.values=iter(values);self.last=.99
    def random(self):
        self.last=next(self.values,self.last);return self.last
    def choice(self,items):return items[0]
    def randrange(self,stop):return 0

def grant(store,uid,units=SQUAD):
    store.profile(uid)
    with store.db:
        for unit in units:store.db.execute('INSERT OR IGNORE INTO units VALUES(?,?,1)',(uid,unit))
    store.set_lineup(uid,list(units))

class ExpansionTests(unittest.TestCase):
    def setUp(self):self.store=Store(':memory:')
    def tearDown(self):self.store.db.close()

    def test_lost_5050_then_featured_and_separate_banner_guarantee(self):
        self.assertEqual(self.store.pull(1,Fixed((0,.99)),banner='kuru'),'eiji')
        self.assertTrue(self.store.featured_guaranteed(1,'kuru'))
        self.assertFalse(self.store.featured_guaranteed(1,'yuko'))
        self.assertEqual(self.store.pull(1,Fixed((0,.99)),banner='kuru'),'kuru')
        self.assertFalse(self.store.featured_guaranteed(1,'kuru'))
        self.assertEqual(self.store.pull(1,Fixed((0,0)),banner='yuko'),'yuko')
        self.assertEqual(self.store.profile(1)[0],700)

    def test_ten_pull_tracks_multiple_five_stars_in_same_batch(self):
        units=self.store.pull_many(1,10,Fixed((0,.99,0,0,.99)),banner='yuko')
        self.assertEqual(units[:3],['eiji','yuko','eiji'])
        self.assertTrue(self.store.featured_guaranteed(1,'yuko'))
        self.assertEqual(self.store.profile(1)[0],0)

    def test_failed_batch_keeps_wallet_and_guarantee_unchanged(self):
        class Broken(Fixed):
            count=0
            def random(self):
                self.count+=1
                if self.count==3:raise RuntimeError('interrupted')
                return 0 if self.count==1 else .99
        self.store.profile(1)
        with self.assertRaises(RuntimeError):self.store.pull_many(1,10,Broken(),banner='yuko')
        self.assertEqual(self.store.profile(1)[0],1000)
        self.assertFalse(self.store.featured_guaranteed(1,'yuko'))
        self.assertEqual(self.store.guarantees(1,'yuko'),(0,0))
        self.assertEqual(self.store.collection(1),[('knight',1)])

    def test_yuko_loses_then_guaranteed_persists_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.db'
            a=Store(path);a.pull(1,Fixed((0,.99)),banner='yuko');a.db.close()
            b=Store(path)
            self.assertTrue(b.featured_guaranteed(1,'yuko'))
            self.assertEqual(b.pull(1,Fixed((0,.99)),banner='yuko'),'yuko')
            b.db.close()

    def test_migrate_previous_kuru_promise_without_reapplying(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'old.db';db=sqlite3.connect(path)
            db.executescript("CREATE TABLE banner_pity(player INTEGER,banner TEXT,pity INTEGER DEFAULT 0,pity4 INTEGER DEFAULT 0,PRIMARY KEY(player,banner)); INSERT INTO banner_pity VALUES(1,'kuru',25,3);")
            db.close()
            a=Store(path)
            self.assertTrue(a.featured_guaranteed(1,'kuru'))
            self.assertEqual(a.guarantees(1,'kuru'),(25,3))
            self.assertEqual(a.pull(1,Fixed((0,.99)),banner='kuru'),'kuru')
            a.db.close()
            b=Store(path)
            self.assertFalse(b.featured_guaranteed(1,'kuru'));b.db.close()

    def test_standard_excludes_both_limited_and_mala_is_shared(self):
        self.assertEqual(self.store.pull(1,Fixed((0,))),'dragon')
        for banner in ('standard','kuru','yuko'):
            rng=Fixed((.05,));rng.choice=lambda items:items[-1]
            self.assertEqual(self.store.pull(2,rng,banner=banner),'mala')
        self.assertIn('50%',str(banner_embed('yuko').to_dict()))

    def test_invalid_lineup_does_not_replace_valid_team(self):
        grant(self.store,1)
        with self.assertRaises(GameError):self.store.set_lineup(1,['knight']*4)
        with self.assertRaises(GameError):self.store.set_lineup(1,['knight','mage','ranger','dragon'])
        self.assertEqual(self.store.lineup(1),SQUAD)
        with self.assertRaises(GameError):TeamBattle(1,2,self.store)

    def test_saved_squad_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.db';a=Store(path);grant(a,1);a.db.close()
            b=Store(path);self.assertEqual(b.lineup(1),SQUAD);b.db.close()

    def team(self):
        grant(self.store,1);grant(self.store,2)
        return TeamBattle(1,2,self.store,Fixed())

    def test_kuru_and_all_three_new_characters_share_team_and_turn_order(self):
        battle=self.team()
        self.assertEqual([f.unit for f in battle.fighters[:4]],SQUAD)
        observed=[]
        for _ in range(8):
            observed.append((battle.turn,battle.fighters[battle.turn].uid))
            battle.act(battle.fighters[battle.turn].uid,'guard')
        self.assertEqual(observed,[(0,1),(4,2),(1,1),(5,2),(2,1),(6,2),(3,1),(7,2)])

    def test_second_side_start_preserves_each_teams_slot_order(self):
        self.team()
        rng=Fixed();rng.randrange=lambda stop:1
        battle=TeamBattle(1,2,self.store,rng)
        observed=[]
        for _ in range(8):
            observed.append(battle.turn)
            battle.act(battle.fighters[battle.turn].uid,'guard')
        self.assertEqual(observed,[4,0,5,1,6,2,7,3])

    def test_targets_allies_dead_out_of_turn_are_rejected_without_mutation(self):
        battle=self.team();before=battle.rounds
        for target in (0,1,99,-1):
            with self.assertRaises(GameError):battle.act(1,'attack',target)
        with self.assertRaises(GameError):battle.act(2,'attack',4)
        battle.fighters[4].hp=0
        with self.assertRaises(GameError):battle.act(1,'attack',4)
        self.assertEqual(battle.rounds,before)
        self.assertEqual(battle.fighters[0].mana,100)

    def test_ko_skips_unit_but_does_not_end_whole_team(self):
        battle=self.team();battle.fighters[4].hp=1
        battle.act(1,'attack',4)
        self.assertFalse(battle.finished)
        self.assertEqual(battle.turn,1)
        for i in (5,6,7):battle.fighters[i].hp=0
        # A normal terminal action detects all enemies dead; simulate last KO instead.
        battle.fighters[6].hp=1
        battle.act(1,'attack',6)
        self.assertTrue(battle.finished);self.assertEqual(battle.winner,1)

    def test_targeted_stun_consumed_only_on_targets_own_slot(self):
        battle=self.team()
        battle.act(1,'skill',5)
        self.assertEqual(battle.fighters[5].stunned,1)
        self.assertEqual(battle.turn,4)
        battle.act(2,'guard');text=battle.act(1,'guard')
        self.assertEqual(battle.turn,2)
        self.assertEqual(battle.fighters[5].stunned,0)
        self.assertIn('ข้าม 1 เทิร์น',text)

    def test_eiji_records_damage_and_spends_recording_on_skill_and_ultimate(self):
        grant(self.store,1);self.store.equip(1,'eiji')
        battle=Battle(1,2,self.store,Fixed())
        actor,target=battle.fighters
        battle._damage(actor,50)
        self.assertEqual(actor.recorded,50)
        battle.act(1,'skill')
        self.assertEqual(target.hp,140-85)
        self.assertEqual(actor.recorded,0)
        battle._damage(actor,20);actor.energy=100;battle.turn=0
        battle.act(1,'ultimate')
        self.assertEqual(target.hp,0)
        self.assertEqual(actor.recorded,0)

    def test_yuko_bleed_ticks_ignores_guard_and_expires(self):
        grant(self.store,1);self.store.equip(1,'yuko')
        self.store.equip(2,'knight')
        battle=Battle(1,2,self.store,Fixed());target=battle.fighters[1]
        battle.act(1,'skill')
        self.assertEqual(target.hp,140-76-11)
        self.assertEqual(target.bleed,1)
        battle.act(2,'guard');battle.act(1,'guard')
        self.assertEqual(target.hp,42)
        self.assertEqual(target.bleed,0)

    def test_bleed_can_end_battle_without_dead_fighter_acting(self):
        grant(self.store,1);self.store.equip(1,'yuko')
        battle=Battle(1,2,self.store,Fixed());battle.fighters[1].hp=80
        text=battle.act(1,'skill')
        self.assertTrue(battle.finished);self.assertEqual(battle.winner,1)
        self.assertIn('ฮิกังบาน',text)

    def test_mala_skill_heals_weakest_ratio_ally_including_kuru(self):
        battle=self.team();battle.turn=3
        battle.fighters[0].hp=20
        battle.act(1,'skill',4)
        self.assertEqual(battle.fighters[0].hp,48)
        self.assertEqual(battle.fighters[4].hp,190)

    def test_mala_ultimate_heals_all_living_teammates_but_not_dead(self):
        battle=self.team();battle.turn=3
        for f in battle.fighters[:4]:f.hp=100
        battle.fighters[1].hp=0;battle.fighters[3].energy=100
        battle.act(1,'ultimate',4)
        self.assertEqual([f.hp for f in battle.fighters[:4]],[143,0,134,127])
        self.assertEqual(battle.fighters[4].hp,165)

    def test_seeded_full_matches_terminate_with_valid_health_and_winner(self):
        for seed in range(8):
            battle=self.team();rng=random.Random(seed)
            for _ in range(210):
                if battle.finished:break
                actor=battle.fighters[battle.turn]
                if actor.energy>=100 and actor.unit in ULTIMATES:action='ultimate'
                elif actor.cooldown==0 and actor.mana>=30:action='skill'
                else:action=rng.choice(['attack','attack','guard'])
                battle.act(actor.uid,action,rng.choice(battle.enemies()))
                self.assertTrue(all(0<=f.hp<=f.max_hp and 0<=f.mana<=100 and 0<=f.energy<=100 for f in battle.fighters))
            self.assertTrue(battle.finished)
            if battle.winner:
                self.assertTrue(all(f.hp==0 for f in battle.fighters if f.uid!=battle.winner))

class TeamUITests(unittest.IsolatedAsyncioTestCase):
    def interaction(self,uid):
        return SimpleNamespace(user=SimpleNamespace(id=uid),response=SimpleNamespace(send_message=AsyncMock(),edit_message=AsyncMock()))
    async def test_accept_target_select_wrong_user_and_chosen_damage(self):
        grant(bot.store,1001);grant(bot.store,1002)
        view=bot.Duel(1001,1002,'4v4')
        self.assertNotIn(view.target_select,view.children)
        await view.accept.callback(self.interaction(1002))
        self.assertEqual(len(view.battle.fighters),8)
        self.assertIn(view.target_select,view.children)
        view.battle.turn=0;view.refresh_buttons()
        before=view.target
        await view.choose_target(self.interaction(1002),5)
        self.assertEqual(view.target,before)
        await view.choose_target(self.interaction(1001),5)
        self.assertEqual(view.target,5)
        await view.move(self.interaction(1001),'attack')
        self.assertEqual(view.battle.fighters[5].hp,132)
        self.assertEqual(view.battle.fighters[4].hp,240)
        self.assertLess(len(view.render()),6000)
        self.assertTrue(all(len(field.value)<=1024 for field in view.render().fields))
        view.close();self.assertTrue(view.target_select.disabled)

    async def test_new_characters_are_selectable_and_have_details(self):
        self.assertTrue({'eiji','yuko','mala'}<={choice.value for choice in bot.bot.tree.get_command('character').parameters[0].choices})
        for unit in SQUAD:self.assertIn(CATALOG[unit][0],character_embed(unit).title)
        self.assertIn('squad',{command.name for command in bot.bot.tree.get_commands()})
