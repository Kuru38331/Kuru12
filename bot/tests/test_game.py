import tempfile
import unittest
from pathlib import Path
from game import Store, Battle, GameError, CATALOG

class Rolls:
    def random(self): return .99
    def choice(self, items): return items[0]
    def randrange(self, stop): return 0

class Tests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.path=Path(self.directory.name)/'test.db'
        self.store=Store(self.path)
    def tearDown(self):
        self.store.db.close()
        self.directory.cleanup()
    def test_daily_and_persistence(self):
        self.assertEqual(self.store.daily(1,86400),300)
        with self.assertRaises(GameError): self.store.daily(1,86401)
        self.store.daily(1,172800)
        other=Store(self.path)
        self.assertEqual(other.profile(1)[0],1600)
        other.db.close()
    def test_cost_and_insufficient_funds(self):
        for _ in range(10): self.store.pull(1,Rolls())
        with self.assertRaises(GameError): self.store.pull(1,Rolls())
        self.assertEqual(self.store.profile(1)[0],0)
        self.assertEqual(sum(n for _,n in self.store.collection(1)),11)
    def test_pity_and_ownership(self):
        self.store.profile(1)
        with self.store.db: self.store.db.execute('UPDATE players SET pity=49 WHERE id=1')
        self.assertEqual(self.store.pull(1,Rolls()),'dragon')
        self.assertEqual(self.store.profile(1)[1],0)
        self.store.equip(1,'dragon')
        with self.assertRaises(GameError): self.store.equip(2,'dragon')
    def test_star_rate_boundaries(self):
        class FixedRoll(Rolls):
            def __init__(self, value): self.value = value
            def random(self): return self.value
        for uid, (roll, stars) in enumerate(((0,5),(.01999,5),(.02,4),(.11999,4),(.12,3),(.99999,3)),100):
            with self.subTest(roll=roll):
                unit = self.store.pull(uid,FixedRoll(roll))
                self.assertEqual(CATALOG[unit][1],stars)
                self.assertEqual(self.store.profile(uid)[1],0 if stars==5 else 1)

    def test_existing_collection_and_pity_survive_reopen(self):
        self.store.profile(1)
        with self.store.db:
            self.store.db.execute('INSERT INTO units VALUES(?,?,?)',(1,'paladin',2))
            self.store.db.execute("UPDATE players SET active='paladin',pity=49 WHERE id=1")
        self.store.db.close()
        self.store=Store(self.path)
        self.assertEqual(self.store.profile(1),(1000,49,'paladin'))
        self.assertIn(('paladin',2),self.store.collection(1))
        self.assertEqual(CATALOG['paladin'][1],4)
        self.assertEqual(CATALOG[self.store.pull(1,Rolls())][1],5)

    def test_turns_guard_skill_and_winner(self):
        b=Battle(1,2,self.store,Rolls())
        with self.assertRaises(GameError): b.act(2,'attack')
        b.act(1,'guard'); b.act(2,'skill')
        self.assertEqual(b.fighters[0].hp,116)
        b.act(1,'attack')
        with self.assertRaises(GameError): b.act(2,'skill')
        b.act(2,'attack'); b.act(1,'skill'); b.act(2,'attack')
        b.act(1,'attack'); b.act(2,'skill'); b.act(1,'attack')
        b.act(2,'attack')
        self.assertTrue(b.finished)
        self.assertEqual(b.winner,2)
        with self.assertRaises(GameError): b.act(2,'attack')
    def test_surrender_and_self_duel(self):
        with self.assertRaises(GameError): Battle(1,1,self.store)
        b=Battle(1,2,self.store,Rolls()); b.act(1,'surrender')
        self.assertEqual(b.winner,2)
    def test_draw_limit(self):
        b=Battle(1,2,self.store,Rolls())
        for _ in range(100): b.act(b.fighters[b.turn].uid,'guard')
        self.assertTrue(b.finished)
        self.assertIsNone(b.winner)

if __name__=='__main__': unittest.main()
