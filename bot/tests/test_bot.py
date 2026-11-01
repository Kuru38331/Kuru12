import os
import tempfile
import unittest
from unittest.mock import AsyncMock
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
