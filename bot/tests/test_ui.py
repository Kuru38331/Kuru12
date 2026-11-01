import os
os.environ['GACHA_DB']=':memory:'
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import bot
from game import Store, CATALOG, Battle, GameError
from presentation import banner_embed, battle_embed, pity_embed, result_embed

class Fixed:
    def random(self): return .99
    def choice(self, items): return items[0]
    def randrange(self, stop): return 0

class EconomyTests(unittest.TestCase):
    def setUp(self): self.store=Store(':memory:')
    def tearDown(self): self.store.db.close()

    def test_ten_guarantee_and_cost(self):
        units=self.store.pull_many(1,10,Fixed())
        self.assertEqual(len(units),10)
        self.assertEqual(sum(CATALOG[u][1]>=4 for u in units),1)
        self.assertEqual(CATALOG[units[-1]][1],4)
        self.assertEqual(self.store.profile(1)[0],0)
        self.assertEqual(self.store.guarantees(1),(10,0))

    def test_single_pulls_share_four_star_guarantee(self):
        for _ in range(9): self.store.pull(1,Fixed())
        self.assertEqual(self.store.guarantees(1),(9,9))
        self.assertEqual(CATALOG[self.store.pull(1,Fixed())][1],4)
        self.assertEqual(self.store.guarantees(1),(10,0))

    def test_five_star_takes_priority_and_resets_both(self):
        self.store.profile(1)
        with self.store.db:
            self.store.db.execute('UPDATE players SET pity=49,pity4=9 WHERE id=1')
        self.assertEqual(CATALOG[self.store.pull(1,Fixed())][1],5)
        self.assertEqual(self.store.guarantees(1),(0,0))

    def test_ten_rolls_back_on_error(self):
        class Broken(Fixed):
            calls=0
            def random(self):
                self.calls+=1
                if self.calls==2: raise RuntimeError('synthetic interrupted roll')
                return .99
        before=self.store.collection(1)
        with self.assertRaises(RuntimeError): self.store.pull_many(1,10,Broken())
        self.assertEqual(self.store.profile(1)[0],1000)
        self.assertEqual(self.store.guarantees(1),(0,0))
        self.assertEqual(self.store.collection(1),before)

    def test_insufficient_ten_does_not_charge_or_roll(self):
        self.store.pull(1,Fixed())
        before=(self.store.profile(1),self.store.collection(1),self.store.guarantees(1))
        with self.assertRaises(GameError): self.store.pull_many(1,10,Fixed())
        self.assertEqual((self.store.profile(1),self.store.collection(1),self.store.guarantees(1)),before)

    def test_legacy_database_migration_is_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'legacy.db'
            db=sqlite3.connect(path)
            db.executescript("CREATE TABLE players(id INTEGER PRIMARY KEY,gems INTEGER NOT NULL DEFAULT 1000,daily INTEGER NOT NULL DEFAULT -1,pity INTEGER NOT NULL DEFAULT 0,active TEXT NOT NULL DEFAULT 'knight'); INSERT INTO players VALUES(42,800,20000,23,'knight');")
            db.close()
            for _ in range(2):
                migrated=Store(path)
                self.assertEqual(migrated.profile(42),(800,23,'knight'))
                self.assertEqual(migrated.guarantees(42),(23,0))
                migrated.db.close()

    def test_mana_cost_recovery_and_rejected_action(self):
        battle=Battle(1,2,self.store,Fixed())
        battle.act(1,'skill')
        self.assertEqual(battle.fighters[0].mana,80)
        battle.act(2,'guard'); battle.act(1,'guard')
        self.assertEqual(battle.fighters[0].mana,95)
        battle.act(2,'guard'); battle.act(1,'attack')
        self.assertEqual(battle.fighters[0].mana,100)
        battle.act(2,'guard')
        battle.fighters[0].mana=19
        before=(battle.turn,battle.rounds,battle.fighters[1].hp)
        with self.assertRaises(GameError): battle.act(1,'skill')
        self.assertEqual((battle.turn,battle.rounds,battle.fighters[1].hp),before)

class UITests(unittest.IsolatedAsyncioTestCase):
    def interaction(self, uid):
        return SimpleNamespace(user=SimpleNamespace(id=uid),response=SimpleNamespace(send_message=AsyncMock(),edit_message=AsyncMock()),original_response=AsyncMock())

    async def test_banner_posts_attachment_without_spending(self):
        interaction=self.interaction(201)
        before=bot.store.profile(201)
        await bot.show_banner(interaction)
        args=interaction.response.send_message.await_args.kwargs
        self.assertEqual(args['embed'].image.url,'attachment://summon-banner.png')
        self.assertEqual(args['file'].filename,'summon-banner.png')
        self.assertEqual(len(args['view'].children),3)
        args['file'].close();args['view'].stop()
        self.assertEqual(bot.store.profile(201),before)

    async def test_public_banner_charges_clicker_only(self):
        view=bot.SummonView()
        other=bot.store.profile(202)
        interaction=self.interaction(203)
        await view.ten.callback(interaction)
        self.assertEqual(bot.store.profile(203)[0],0)
        self.assertEqual(bot.store.profile(202),other)
        args=interaction.response.send_message.await_args.kwargs
        self.assertTrue(args['ephemeral'])
        self.assertEqual(len(args['embed'].fields[0].value.splitlines()),10)
        view.stop()

    async def test_error_has_no_charge_and_expiry_disables_banner(self):
        view=bot.SummonView()
        interaction=self.interaction(204)
        bot.store.pull(204,Fixed())
        await view.ten.callback(interaction)
        self.assertEqual(bot.store.profile(204)[0],900)
        self.assertIn('เพชรไม่พอ',interaction.response.send_message.await_args.args[0])
        view.message=SimpleNamespace(edit=AsyncMock())
        await view.on_timeout()
        self.assertTrue(all(b.disabled for b in view.children))
        view.stop()

    async def test_battle_embeds_and_buttons_follow_turn(self):
        view=bot.Duel(205,206)
        self.assertTrue(view.attack.disabled)
        await view.accept.callback(self.interaction(206))
        self.assertNotIn(view.accept,view.children)
        self.assertFalse(view.attack.disabled)
        current=view.battle.fighters[view.battle.turn]
        other=view.battle.fighters[1-view.battle.turn]
        await view.move(self.interaction(current.uid),'skill')
        self.assertEqual(current.mana,80)
        await view.move(self.interaction(other.uid),'guard')
        self.assertTrue(view.skill.disabled)
        embed=view.render()
        self.assertIn('80/100 MP',embed.fields[view.battle.turn].value)
        self.assertIn(f'<@{current.uid}>',embed.fields[2].value)
        self.assertLess(len(embed),6000)
        view.close()
