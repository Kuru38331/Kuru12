import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch, call
from types import SimpleNamespace

os.environ['GACHA_DB'] = ':memory:'
import bot

class ViewTests(unittest.IsolatedAsyncioTestCase):
    def interaction(self, uid):
        return SimpleNamespace(user=SimpleNamespace(id=uid),response=SimpleNamespace(send_message=AsyncMock(),edit_message=AsyncMock()))

    async def test_accept_turns_and_timeout(self):
        view=bot.Duel(11,22)
        bot.busy.update(view.ids)
        outsider=self.interaction(33)
        self.assertFalse(await view.interaction_check(outsider))
        await view.accept.callback(self.interaction(11))
        self.assertIsNone(view.battle)
        await view.accept.callback(self.interaction(22))
        self.assertIsNotNone(view.battle)
        current=view.battle.fighters[view.battle.turn].uid
        wrong=view.battle.fighters[1-view.battle.turn].uid
        before=view.battle.rounds
        await view.move(self.interaction(wrong),'attack')
        self.assertEqual(view.battle.rounds,before)
        await view.move(self.interaction(current),'attack')
        self.assertEqual(view.battle.rounds,before+1)
        view.message=SimpleNamespace(edit=AsyncMock())
        await view.on_timeout()
        self.assertTrue(view.closed)
        self.assertFalse(bot.busy.intersection(view.ids))
        self.assertTrue(all(c.disabled for c in view.children))

    async def test_cancel_releases_players(self):
        view=bot.Duel(44,55)
        bot.busy.update(view.ids)
        await view.cancel.callback(self.interaction(44))
        self.assertTrue(view.closed)
        self.assertFalse(bot.busy.intersection(view.ids))

    async def test_commands_registered(self):
        self.assertEqual({c.name for c in bot.bot.tree.get_commands()}, {'daily','gacha','collection','team','battle'})


class StartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_server_access_falls_back_to_global(self):
        response = SimpleNamespace(status=403, reason='Forbidden')
        error = bot.discord.Forbidden(response, {'code':50001, 'message':'Missing Access'})
        client = bot.Client()
        try:
            with patch.dict(os.environ, {'DISCORD_GUILD_ID':'123'}), patch.object(client.tree, 'sync', new=AsyncMock(side_effect=[error, []])) as sync:
                with self.assertLogs(level='WARNING') as logs:
                    await client.setup_hook()
                self.assertEqual(sync.await_count, 2)
                self.assertEqual(sync.await_args_list[0].kwargs['guild'].id,123)
                self.assertEqual(sync.await_args_list[1],call())
                self.assertIn('Registering global commands', logs.output[0])
        finally:
            await client.close()

    async def test_accessible_server_does_not_sync_globally(self):
        client = bot.Client()
        try:
            with patch.dict(os.environ, {'DISCORD_GUILD_ID':'123'}), patch.object(client.tree, 'sync', new=AsyncMock(return_value=[])) as sync:
                await client.setup_hook()
                sync.assert_awaited_once()
                self.assertEqual(sync.await_args.kwargs['guild'].id,123)
        finally:
            await client.close()

    async def test_unrelated_forbidden_is_not_hidden(self):
        error = bot.discord.Forbidden(SimpleNamespace(status=403,reason='Forbidden'), {'code':50013,'message':'Missing Permissions'})
        client = bot.Client()
        try:
            with patch.dict(os.environ, {'DISCORD_GUILD_ID':'123'}), patch.object(client.tree,'sync',new=AsyncMock(side_effect=error)) as sync:
                with self.assertRaises(bot.discord.Forbidden):
                    await client.setup_hook()
                sync.assert_awaited_once()
        finally:
            await client.close()
