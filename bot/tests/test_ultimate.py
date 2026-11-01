import os
os.environ['GACHA_DB']=':memory:'
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
import bot
from game import Store,Battle,GameError
from presentation import character_embed

class Fixed:
    def randrange(self,stop):return 0

class UltimateTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(':memory:')
        for uid,unit in ((1,'kuru'),(2,'dragon')):
            self.store.profile(uid)
            with self.store.db:self.store.db.execute('INSERT OR IGNORE INTO units VALUES(?,?,1)',(uid,unit))
            self.store.equip(uid,unit)
        self.battle=Battle(1,2,self.store,Fixed())
    def tearDown(self):self.store.db.close()

    def test_not_ready_rejects_without_spending_turn_or_resources(self):
        actor,target=self.battle.fighters
        actor.energy=99;actor.cooldown=2;actor.guard=True
        before=vars(actor).copy(),vars(target).copy(),self.battle.turn,self.battle.rounds
        with self.assertRaises(GameError):self.battle.act(1,'ultimate')
        self.assertEqual((vars(actor),vars(target),self.battle.turn,self.battle.rounds),before)

    def test_ultimate_uses_max_hp_consumes_energy_and_no_mana_or_stun(self):
        actor,target=self.battle.fighters
        actor.energy=100;actor.mana=0;actor.hp=1;actor.attack=999;actor.cooldown=3
        text=self.battle.act(1,'ultimate')
        self.assertEqual(target.hp,36)
        self.assertEqual(actor.energy,0)
        self.assertEqual(actor.mana,0)
        self.assertEqual(actor.cooldown,2)
        self.assertEqual(self.battle.turn,1)
        self.assertEqual(self.battle.rounds,1)
        self.assertEqual(target.stunned,0)
        self.assertIn('สุริยคราสพันผีเสื้อ',text)
        self.assertIn('144',text)

    def test_defense_reduces_ultimate_damage(self):
        actor,target=self.battle.fighters
        actor.energy=100;target.guard=True
        self.battle.act(1,'ultimate')
        self.assertEqual(target.hp,108)
        self.assertFalse(target.guard)

    def test_scaled_ultimate_can_finish_battle_and_cannot_repeat(self):
        actor,target=self.battle.fighters
        actor.energy=100;actor.max_hp=400
        self.battle.act(1,'ultimate')
        self.assertEqual(target.hp,0)
        self.assertEqual(self.battle.winner,1)
        with self.assertRaises(GameError):self.battle.act(1,'ultimate')

    def test_cannot_use_other_players_turn_or_unsupported_character(self):
        actor,target=self.battle.fighters
        target.energy=100
        with self.assertRaises(GameError):self.battle.act(2,'ultimate')
        self.battle.act(1,'guard')
        before=self.battle.rounds
        with self.assertRaisesRegex(GameError,'ยังไม่มีอันติ'):self.battle.act(2,'ultimate')
        self.assertEqual(self.battle.rounds,before)

    def test_charge_from_actions_and_incoming_damage_caps_at_100(self):
        actor,target=self.battle.fighters
        self.battle.act(1,'skill')
        self.assertEqual(actor.energy,35)
        self.battle.act(1,'attack')
        self.assertEqual(actor.energy,60)
        self.battle.act(2,'attack')
        self.assertEqual(actor.energy,70)
        self.battle.act(1,'guard')
        self.assertEqual(actor.energy,85)
        self.battle.act(2,'attack')
        self.assertEqual(actor.energy,95)
        self.battle.act(1,'guard')
        self.assertEqual(actor.energy,100)

    def test_reachable_charge_then_release_then_charge_again(self):
        actor,target=self.battle.fighters
        for _ in range(7):
            self.battle.act(1,'guard');self.battle.act(2,'guard')
        self.assertEqual(actor.energy,100)
        self.battle.act(1,'ultimate')
        self.assertEqual(actor.energy,0)
        self.battle.act(2,'guard');self.battle.act(1,'attack')
        self.assertEqual(actor.energy,25)

    def test_energy_resets_for_new_match(self):
        self.battle.fighters[0].energy=100
        fresh=Battle(1,2,self.store,Fixed())
        self.assertEqual(fresh.fighters[0].energy,0)

class UltimateUITests(unittest.IsolatedAsyncioTestCase):
    def interaction(self,uid):
        return SimpleNamespace(user=SimpleNamespace(id=uid),response=SimpleNamespace(send_message=AsyncMock(),edit_message=AsyncMock()))

    async def test_button_ready_state_and_energy_bar_follow_current_player(self):
        for uid,unit in ((901,'kuru'),(902,'dragon')):
            bot.store.profile(uid)
            with bot.store.db:bot.store.db.execute('INSERT OR IGNORE INTO units VALUES(?,?,1)',(uid,unit))
            bot.store.equip(uid,unit)
        view=bot.Duel(901,902)
        self.assertTrue(view.ultimate.disabled)
        await view.accept.callback(self.interaction(902))
        view.battle.turn=0;view.refresh_buttons()
        self.assertTrue(view.ultimate.disabled)
        view.battle.fighters[0].energy=100;view.refresh_buttons()
        self.assertFalse(view.ultimate.disabled)
        self.assertEqual(view.ultimate.style,bot.discord.ButtonStyle.danger)
        self.assertIn('สุริยคราสพันผีเสื้อ',view.ultimate.label)
        self.assertIn('100/100 พลังอันติ',view.render().fields[0].value)
        await view.ultimate.callback(self.interaction(901))
        self.assertEqual(view.battle.fighters[0].energy,0)
        self.assertEqual(view.battle.fighters[1].hp,36)
        self.assertTrue(view.ultimate.disabled)
        self.assertIn('อันติ',str(view.render().to_dict()))
        view.close()
        self.assertTrue(view.ultimate.disabled)
        self.assertIn('60%',str(character_embed('kuru').to_dict()))
