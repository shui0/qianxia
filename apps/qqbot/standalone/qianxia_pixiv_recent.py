from contextlib import closing
from pathlib import Path
import sqlite3


class RecentImages:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=1)) as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS pixiv_recent (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot INTEGER, scope INTEGER, peer INTEGER,
                    work_id TEXT, image_hash TEXT
                );
                CREATE INDEX IF NOT EXISTS pixiv_recent_scope ON pixiv_recent(bot,scope,peer,id);
            ''')

    def ids(self, key: tuple[int, int, int]) -> set[str]:
        with closing(sqlite3.connect(self.path, timeout=1)) as db:
            return {row[0] for row in db.execute(
                'SELECT work_id FROM pixiv_recent WHERE bot=? AND scope=? AND peer=? ORDER BY id DESC LIMIT 20', key)}

    def has_hash(self, key: tuple[int, int, int], digest: str) -> bool:
        with closing(sqlite3.connect(self.path, timeout=1)) as db:
            return db.execute('SELECT 1 FROM pixiv_recent WHERE bot=? AND scope=? AND peer=? AND image_hash=? LIMIT 1',
                              (*key, digest)).fetchone() is not None

    def mark(self, key: tuple[int, int, int], work_id: str, digest: str):
        with closing(sqlite3.connect(self.path, timeout=1)) as db, db:
            db.execute('DELETE FROM pixiv_recent WHERE bot=? AND scope=? AND peer=? AND work_id=?', (*key, work_id))
            db.execute('INSERT INTO pixiv_recent(bot,scope,peer,work_id,image_hash) VALUES (?,?,?,?,?)',
                       (*key, work_id, digest))
            db.execute('''DELETE FROM pixiv_recent WHERE bot=? AND scope=? AND peer=? AND id NOT IN
                (SELECT id FROM pixiv_recent WHERE bot=? AND scope=? AND peer=? ORDER BY id DESC LIMIT 20)''', (*key, *key))
