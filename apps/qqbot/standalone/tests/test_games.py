import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import bot_fixture
from plugins.qianxia_games import roll_dice
from qianxia_state import Memory


class GamesTests(unittest.TestCase):
    def test_dice_limits(self):
        self.assertEqual(roll_dice("3d6+2", lambda a, b: b), ([6, 6, 6], 20))
        for expression in ("21d6", "d1001", "1", "0d6"):
            with self.assertRaises(ValueError):
                roll_dice(expression)

    def test_guess_persists_and_is_group_scoped(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "state.sqlite"
            game = Memory(path)
            self.assertTrue(game.start_guess((1, 2, 0), 42))
            self.assertFalse(game.start_guess((1, 2, 0), 50))
            game = Memory(path)
            self.assertEqual(game.guess((1, 2, 0), 5), ("low", 1, None))
            self.assertEqual(game.guess((1, 3, 0), 42), ("missing", 0, None))
            self.assertEqual(game.guess((1, 2, 0), 42), ("win", 2, 42))
