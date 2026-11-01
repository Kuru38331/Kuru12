import os
os.environ['GACHA_DB']=':memory:'
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import bot
from game import Store,GameError

class AdminStoreTests(unittest.TestCase):
    def setUp(self):self.store=Store(':memory:')
    def tearDown(self):self.store.db.close()

    def test_add_gems_preserves_existing_and_records_audit(self):
        self.store.profile(2)
        self.store.admin_grant('a',1,10,2,'gems',5000,reason='ทดสอบ')
        self.assertEqual(self.store.profile(2)[0],6000)
        row=self.store.admin_history(10)[0]
        self.assertEqual(row[1:],(1,2,'gems','gems',5000))
        self.assertEqual(self.store.admin_history(11),[])

    def test_duplicate_request_never_grants_twice(self):
        self.store.admin_grant('a',1,10,2,'gems',100)
        with self.assertRaises(GameError):self.store.admin_grant('a',1,10,2,'gems',100)
        self.assertEqual(self.store.profile(2)[0],1100)
        self.assertEqual(len(self.store.admin_history(10)),1)

    def test_character_grants_add_copies_without_changing_pity(self):
        self.store.profile(2)
        self.store.admin_grant('a',1,10,2,'character',2,'kuru')
        self.store.admin_grant('b',1,10,2,'character',3,'kuru')
        self.assertIn(('kuru',5),self.store.collection(2))
        self.assertEqual(self.store.profile(2),(1000,0,'knight'))
        self.assertEqual(self.store.guarantees(2,'kuru'),(0,0))

    def test_team_grant_makes_requested_four_character_team_playable(self):
        self.store.admin_grant('a',1,10,2,'team')
        self.assertEqual(self.store.lineup(2),['kuru','eiji','yuko','mala'])
        self.assertEqual(self.store.profile(2)[2],'kuru')
        owned=dict(self.store.collection(2))
        for unit in ('kuru','eiji','yuko','mala'):self.assertEqual(owned[unit],1)
        self.assertEqual(self.store.admin_history(10)[0][3],'team')

    def test_validation_cannot_remove_money_or_create_unknown_units(self):
        for amount in (-1,0,True,1_000_000_001):
            with self.assertRaises(GameError):self.store.admin_grant(str(amount),1,10,2,'gems',amount)
        with self.assertRaises(GameError):self.store.admin_grant('x',1,10,2,'character',1,'unknown')
        with self.assertRaises(GameError):self.store.admin_grant('y',1,10,2,'gems',1,reason='x'*201)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM players').fetchone()[0],0)
        self.assertEqual(self.store.admin_history(10),[])

    def test_audit_failure_rolls_back_entire_grant(self):
        self.store.profile(2)
        self.store.db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON admin_audit BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.store.admin_grant('a',1,10,2,'gems',100)
        self.assertEqual(self.store.profile(2)[0],1000)
        self.assertEqual(self.store.admin_history(10),[])

    def test_team_failure_rolls_back_earlier_unit_and_team_changes(self):
        self.store.profile(2)
        with self.store.db:self.store.db.execute("INSERT INTO units VALUES(2,'eiji',1000000)")
        with self.assertRaises(GameError):self.store.admin_grant('a',1,10,2,'team')
        self.assertNotIn('kuru',dict(self.store.collection(2)))
        with self.assertRaises(GameError):self.store.lineup(2)
        self.assertEqual(self.store.admin_history(10),[])

    def test_audit_and_grants_persist_after_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.db';a=Store(path)
            a.admin_grant('a',1,10,2,'team');a.db.close()
            b=Store(path)
            self.assertEqual(b.lineup(2),['kuru','eiji','yuko','mala'])
            self.assertEqual(len(b.admin_history(10)),1);b.db.close()

class AdminCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings=patch.dict(os.environ,{'ADMIN_GUILD_ID':'','DISCORD_GUILD_ID':''})
        self.settings.start()
    def tearDown(self):self.settings.stop()
    def interaction(self,request=99001,is_admin=True,guild=10):
        return SimpleNamespace(id=request,guild_id=guild,user=SimpleNamespace(id=2001),permissions=bot.discord.Permissions(administrator=is_admin),response=SimpleNamespace(send_message=AsyncMock()))
    def member(self,uid=2002,guild=10,is_bot=False):return SimpleNamespace(id=uid,guild=SimpleNamespace(id=guild),bot=is_bot)

    async def test_non_admin_direct_call_and_discord_check_both_reject(self):
        interaction=self.interaction(is_admin=False)
        with patch.object(bot.store,'admin_grant') as grant:
            with self.assertRaises(GameError):await bot.admin_gems.callback(interaction,self.member(),100)
            grant.assert_not_called()
        for check in bot.admin_gems.checks:
            with self.assertRaises(bot.app_commands.MissingPermissions):await check(interaction)
        self.assertTrue(bot.admin.default_permissions.administrator)

    async def test_dm_wrong_guild_and_bot_target_rejected_before_writes(self):
        for interaction,member in ((self.interaction(guild=None),self.member()),(self.interaction(),self.member(guild=11)),(self.interaction(),self.member(is_bot=True))):
            with patch.object(bot.store,'admin_grant') as grant:
                with self.assertRaises(GameError):await bot.admin_team.callback(interaction,member)
                grant.assert_not_called()
        with patch.dict(os.environ,{'ADMIN_GUILD_ID':'11'}):
            with self.assertRaises(GameError):bot.require_admin(self.interaction())
        with patch.dict(os.environ,{'ADMIN_GUILD_ID':'bad'}):
            with self.assertRaises(GameError):bot.require_admin(self.interaction())

    async def test_authorized_grant_is_ephemeral_and_targeted(self):
        interaction=self.interaction()
        before=bot.store.profile(2002)[0]
        await bot.admin_gems.callback(interaction,self.member(),1234)
        self.assertEqual(bot.store.profile(2002)[0],before+1234)
        self.assertTrue(interaction.response.send_message.await_args.kwargs['ephemeral'])
        self.assertIn('<@2002>',interaction.response.send_message.await_args.kwargs['embed'].description)

    async def test_busy_target_cannot_have_team_replaced(self):
        bot.busy.add(2003)
        try:
            with patch.object(bot.store,'admin_grant') as grant:
                with self.assertRaises(GameError):await bot.admin_team.callback(self.interaction(99002),self.member(2003))
                grant.assert_not_called()
        finally:bot.busy.discard(2003)
