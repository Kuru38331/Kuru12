import os
os.environ['GACHA_DB']=':memory:'
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import bot
from game import Store,Battle,CATALOG,GameError
from presentation import character_embed,banner_embed,result_embed,battle_embed

class Fixed:
    def __init__(self,roll=.99):self.roll=roll
    def random(self):return self.roll
    def choice(self,items):return items[-1]
    def randrange(self,stop):return 0

class KuruTests(unittest.TestCase):
    def setUp(self):self.store=Store(':memory:')
    def tearDown(self):self.store.db.close()
    def battle(self,second='dragon'):
        for uid,unit in ((1,'kuru'),(2,second)):
            self.store.profile(uid)
            with self.store.db:self.store.db.execute('INSERT OR IGNORE INTO units VALUES(?,?,1)',(uid,unit))
            self.store.equip(uid,unit)
        return Battle(1,2,self.store,Fixed())

    def test_exclusive_to_limited_pool(self):
        self.assertEqual(self.store.pull(1,Fixed(0)),'dragon')
        self.assertEqual(self.store.pull(2,Fixed(0),banner='kuru'),'kuru')
        self.store.equip(2,'kuru')
        self.assertEqual(self.store.profile(2)[2],'kuru')

    def test_separate_pity_and_shared_wallet(self):
        self.store.pull(1,Fixed())
        self.store.pull(1,Fixed(),banner='kuru')
        self.assertEqual(self.store.guarantees(1),(1,1))
        self.assertEqual(self.store.guarantees(1,'kuru'),(1,1))
        self.assertEqual(self.store.profile(1)[0],800)
        with self.store.db:
            self.store.db.execute("UPDATE banner_pity SET pity=49,pity4=9 WHERE player=1 AND banner='kuru'")
        self.assertEqual(self.store.pull(1,Fixed(),banner='kuru'),'kuru')
        self.assertEqual(self.store.guarantees(1,'kuru'),(0,0))
        self.assertEqual(self.store.guarantees(1),(1,1))

    def test_closed_banner_does_not_charge(self):
        self.store.profile(1)
        with patch.dict(os.environ,{'KURU_BANNER_OPEN':'false'}):
            with self.assertRaises(GameError):self.store.pull(1,Fixed(0),banner='kuru')
            self.assertIn('ปิดตู้แล้ว',str(banner_embed('kuru').to_dict()))
        self.assertEqual(self.store.profile(1)[0],1000)
        self.assertEqual(self.store.guarantees(1,'kuru'),(0,0))
        self.assertEqual(self.store.pull(1,Fixed(0)),'dragon')

    def test_ten_limited_has_four_star_guarantee(self):
        units=self.store.pull_many(1,10,Fixed(),banner='kuru')
        self.assertEqual(len(units),10)
        self.assertEqual(CATALOG[units[-1]][1],4)
        self.assertEqual(self.store.guarantees(1,'kuru'),(10,0))
        self.assertEqual(self.store.guarantees(1),(0,0))

    def test_pity_persists_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.db'
            a=Store(path);a.pull(1,Fixed(),banner='kuru');a.db.close()
            b=Store(path)
            self.assertEqual(b.guarantees(1,'kuru'),(1,1))
            self.assertEqual(b.profile(1)[0],900)
            b.db.close()

    def test_max_hp_scaling_ignores_current_hp_and_attack_stat(self):
        battle=self.battle()
        actor,target=battle.fighters
        actor.hp=1;actor.attack=9999
        battle.act(1,'attack')
        self.assertEqual(target.hp,180-38)
        other=self.battle();other.fighters[0].max_hp=400
        other.act(1,'attack')
        self.assertEqual(other.fighters[1].hp,180-64)

    def test_stun_skips_exactly_one_turn_then_recovers(self):
        battle=self.battle()
        text=battle.act(1,'skill')
        actor,target=battle.fighters
        self.assertEqual(target.hp,104)
        self.assertEqual(actor.mana,70)
        self.assertEqual(actor.cooldown,3)
        self.assertEqual(battle.turn,0)
        self.assertEqual(battle.rounds,2)
        self.assertIn('ข้าม 1 เทิร์น',text)
        with self.assertRaises(GameError):battle.act(2,'attack')
        with self.assertRaises(GameError):battle.act(1,'skill')
        battle.act(1,'attack')
        self.assertEqual(battle.turn,1)
        battle.act(2,'guard')
        self.assertEqual(battle.turn,0)

    def test_kuru_skill_has_own_cost_and_cooldown(self):
        battle=self.battle('kuru')
        actor,target=battle.fighters
        actor.mana=29
        with self.assertRaises(GameError):battle.act(1,'skill')
        self.assertEqual((battle.rounds,target.hp,actor.cooldown),(0,240,0))
        actor.mana=100
        battle.act(1,'skill')
        for expected in (2,1,0):
            battle.act(1,'guard')
            self.assertEqual(actor.cooldown,expected)
            battle.act(2,'guard')
        battle.act(1,'skill')
        self.assertEqual(actor.cooldown,3)
        self.assertEqual(battle.turn,0)

    def test_stun_skip_does_not_reduce_victim_skill_cooldown(self):
        battle=self.battle('kuru')
        battle.fighters[1].cooldown=2
        battle.act(1,'skill')
        self.assertEqual(battle.fighters[1].cooldown,2)

    def test_guard_reduces_damage_but_not_stun(self):
        battle=self.battle();battle.fighters[1].guard=True
        battle.act(1,'skill')
        self.assertEqual(battle.fighters[1].hp,142)
        self.assertEqual(battle.turn,0)

    def test_no_extra_stun_after_victory_or_turn_limit(self):
        battle=self.battle();battle.fighters[1].hp=1
        battle.act(1,'skill')
        self.assertEqual(battle.winner,1)
        self.assertEqual(battle.rounds,1)
        self.assertEqual(battle.fighters[1].stunned,0)
        other=self.battle();other.rounds=99
        other.act(1,'skill')
        self.assertTrue(other.finished)
        self.assertIsNone(other.winner)
        self.assertEqual(other.rounds,100)

class KuruUITests(unittest.IsolatedAsyncioTestCase):
    def interaction(self,uid):
        return SimpleNamespace(user=SimpleNamespace(id=uid),response=SimpleNamespace(send_message=AsyncMock(),edit_message=AsyncMock()),original_response=AsyncMock())

    async def test_limited_attachment_and_current_banner_pity(self):
        interaction=self.interaction(801)
        await bot.show_banner(interaction,'kuru')
        args=interaction.response.send_message.await_args.kwargs
        self.assertEqual(args['embed'].image.url,'attachment://kuru-banner.png')
        self.assertEqual(args['file'].filename,'kuru-banner.png')
        self.assertEqual(args['view'].banner,'kuru')
        args['file'].close();args['view'].stop()
        view=bot.SummonView('kuru')
        bot.store.pull(802,Fixed(),banner='kuru')
        click=self.interaction(802)
        await view.pity.callback(click)
        embed=click.response.send_message.await_args.kwargs['embed']
        self.assertIn('Kuru Limited',embed.description)
        self.assertIn('1/50',embed.fields[0].name)
        view.stop()

    async def test_skill_button_and_card_show_hp_scaling(self):
        for uid,unit in ((803,'kuru'),(804,'dragon')):
            bot.store.profile(uid)
            with bot.store.db:bot.store.db.execute('INSERT OR IGNORE INTO units VALUES(?,?,1)',(uid,unit))
            bot.store.equip(uid,unit)
        view=bot.Duel(803,804)
        await view.accept.callback(self.interaction(804))
        view.battle.turn=0;view.refresh_buttons()
        self.assertIn('30 MP',view.skill.label)
        self.assertIn('HP-scaling',view.render().fields[0].value)
        await view.move(self.interaction(803),'skill')
        self.assertTrue(view.skill.disabled)
        self.assertIn('ข้าม 1 เทิร์น',str(view.render().to_dict()))
        view.close()
        self.assertIn('240',str(character_embed('kuru').to_dict()))
        self.assertIn('32%',str(character_embed('kuru').to_dict()))
