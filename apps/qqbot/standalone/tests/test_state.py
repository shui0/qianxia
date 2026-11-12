from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from qianxia_state import Memory


class MemoryTests(unittest.TestCase):
    def test_turns_survive_restart_and_stay_isolated(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "bot.sqlite3"
            store = Memory(path)
            store.save_turn((1, 3, 2), "你好", "晚上好", now=100)
            restored = Memory(path)
            self.assertEqual(restored.history((1, 3, 2)), [
                {"role": "user", "content": "你好"}, {"role": "assistant", "content": "晚上好"},
            ])
            self.assertEqual(restored.history((1, 3, 4)), [])
            self.assertEqual(restored.history((1, None, 2)), [])

    def test_diary_and_reports_stay_in_scope(self):
        with TemporaryDirectory() as folder:
            store = Memory(Path(folder) / "bot.sqlite3")
            store.write_diary((1, 3, 0), "群三", now=100)
            store.record_group(1, 3, 2, "甲", "打舞萌", now=100)
            self.assertEqual(store.diaries((1, 4, 0)), [])
            self.assertEqual(store.group_messages(1, 4, since=0), [])
            self.assertEqual(store.group_messages(1, 3, since=0), [("甲", "打舞萌")])
