from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
import re
import sqlite3
import time

Key = tuple[int, int | None, int]
PRAISE = re.compile("可爱|厉害|好棒|太强|喜欢|爱你|优秀|温柔|贴心|好看")
INSULT = re.compile("笨蛋|讨厌|滚|闭嘴|烦人|恶心|垃圾")
ENERGY = [(0, 12), (5, 10), (7, 45), (9, 80), (12, 85), (14, 50),
          (16, 75), (19, 82), (22, 60), (24, 20)]


def scope_key(key: Key) -> tuple[int, int, int]:
    bot, group, user = key
    return bot, group or 0, user


def affinity_label(score: float) -> str:
    for threshold, label in ((20, "有点陌生"), (50, "熟人"), (100, "朋友"),
                             (200, "好朋友"), (400, "很喜欢")):
        if score < threshold:
            return label
    return "最喜欢"


def drift_mood(previous, now: float) -> tuple[float, float]:
    clock = datetime.fromtimestamp(now)
    hour = clock.hour + clock.minute / 60
    for (start, low), (end, high) in zip(ENERGY, ENERGY[1:]):
        if start <= hour < end:
            base = low + (high - low) * (hour - start) / (end - start)
            break
    if previous is None:
        return base, 60
    energy, mood, ts = previous
    drift = 1 - .4 ** min(max(0, now - ts) / 3600, 6)
    return energy + (base - energy) * drift, mood + (60 - mood) * drift * .5


def mood_label(energy: float, mood: float) -> str:
    if energy < 22:
        return "困得不行"
    if mood < 28:
        return "有点蔫"
    if mood > 82 and energy > 55:
        return "超兴奋"
    if energy < 45:
        return "有点累"
    return "心情不错" if mood > 65 else "平静"


class Memory:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY, bot INTEGER, scope INTEGER, peer INTEGER,
                    input TEXT, output TEXT, ts REAL
                );
                CREATE INDEX IF NOT EXISTS turn_scope ON turns(bot,scope,peer,id);
                CREATE TABLE IF NOT EXISTS affinity (
                    bot INTEGER, scope INTEGER, peer INTEGER, score REAL,
                    PRIMARY KEY (bot,scope,peer)
                );
                CREATE TABLE IF NOT EXISTS mood (
                    bot INTEGER, scope INTEGER, peer INTEGER, energy REAL, mood REAL, ts REAL,
                    PRIMARY KEY (bot,scope,peer)
                );
                CREATE TABLE IF NOT EXISTS group_messages (
                    id INTEGER PRIMARY KEY, bot INTEGER, scope INTEGER, sender INTEGER,
                    nickname TEXT, body TEXT, ts REAL
                );
                CREATE INDEX IF NOT EXISTS group_scope ON group_messages(bot,scope,id);
                CREATE TABLE IF NOT EXISTS diaries (
                    id INTEGER PRIMARY KEY, bot INTEGER, scope INTEGER, peer INTEGER,
                    body TEXT, ts REAL
                );
                CREATE INDEX IF NOT EXISTS diary_scope ON diaries(bot,scope,peer,id);
                CREATE TABLE IF NOT EXISTS guesses (
                    bot INTEGER, scope INTEGER, peer INTEGER, target INTEGER, tries INTEGER,
                    PRIMARY KEY (bot,scope,peer)
                );
            """)

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=1)) as db, db:
            yield db

    def history(self, key: Key) -> list[dict[str, str]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT input,output FROM turns WHERE bot=? AND scope=? AND peer=? ORDER BY id DESC LIMIT 6",
                scope_key(key),
            ).fetchall()
        return [turn for user, reply in reversed(rows) for turn in (
            {"role": "user", "content": user}, {"role": "assistant", "content": reply},
        )]

    def save_turn(self, key: Key, text: str, answer: str, now: float) -> None:
        scope = scope_key(key)
        mood_scope = scope[:2] + (0 if key[1] is not None else key[2],)
        praised, insulted = bool(PRAISE.search(text)), bool(INSULT.search(text))
        delta = min(3, .6 + 2 * praised - 1.2 * insulted + (key[1] is not None))
        with self.connect() as db:
            db.execute("INSERT INTO turns(bot,scope,peer,input,output,ts) VALUES (?,?,?,?,?,?)",
                       (*scope, text[:2000], answer[:4000], now))
            db.execute("""DELETE FROM turns WHERE bot=? AND scope=? AND peer=? AND id <
                       (SELECT id FROM turns WHERE bot=? AND scope=? AND peer=? ORDER BY id DESC LIMIT 1 OFFSET 5)""",
                       (*scope, *scope))
            db.execute("""INSERT INTO affinity VALUES (?,?,?,?)
                       ON CONFLICT(bot,scope,peer) DO UPDATE SET score=max(0,min(999,score+?))""",
                       (*scope, 30 + delta, delta))
            old = db.execute("SELECT energy,mood,ts FROM mood WHERE bot=? AND scope=? AND peer=?",
                             mood_scope).fetchone()
            energy, mood = drift_mood(old, now)
            energy = min(100, energy + 4 * praised)
            mood = max(0, min(100, mood + (8 if praised else -10 if insulted else .8)))
            db.execute("INSERT OR REPLACE INTO mood VALUES (?,?,?,?,?,?)",
                       (*mood_scope, energy, mood, now))

    def profile(self, key: Key, now: float) -> tuple[float, float, float]:
        scope = scope_key(key)
        mood_scope = scope[:2] + (0 if key[1] is not None else key[2],)
        with self.connect() as db:
            score = db.execute("SELECT score FROM affinity WHERE bot=? AND scope=? AND peer=?",
                               scope).fetchone()
            mood = db.execute("SELECT energy,mood,ts FROM mood WHERE bot=? AND scope=? AND peer=?",
                              mood_scope).fetchone()
        return (score[0] if score else 30, *drift_mood(mood, now))

    def record_group(self, bot: int, group: int, user: int, nickname: str, text: str, now: float):
        with self.connect() as db:
            db.execute("INSERT INTO group_messages(bot,scope,sender,nickname,body,ts) VALUES (?,?,?,?,?,?)",
                       (bot, group, user, nickname[:60], text[:300], now))
            db.execute("""DELETE FROM group_messages WHERE bot=? AND scope=? AND
                       (ts < ? OR id < (SELECT id FROM group_messages WHERE bot=? AND scope=?
                       ORDER BY id DESC LIMIT 1 OFFSET 4999))""",
                       (bot, group, now - 7 * 86400, bot, group))

    def group_messages(self, bot: int, group: int, since: float) -> list[tuple[str, str]]:
        with self.connect() as db:
            return db.execute("""SELECT nickname,body FROM group_messages
                              WHERE bot=? AND scope=? AND ts>=? ORDER BY id DESC LIMIT 800""",
                              (bot, group, since)).fetchall()

    def write_diary(self, key: Key, text: str, now: float | None = None):
        scope = scope_key(key)
        with self.connect() as db:
            db.execute("INSERT INTO diaries(bot,scope,peer,body,ts) VALUES (?,?,?,?,?)",
                       (*scope, text[:400], time.time() if now is None else now))
            db.execute("""DELETE FROM diaries WHERE bot=? AND scope=? AND peer=? AND id <
                       (SELECT id FROM diaries WHERE bot=? AND scope=? AND peer=? ORDER BY id DESC LIMIT 1 OFFSET 29)""",
                       (*scope, *scope))

    def diaries(self, key: Key) -> list[tuple[float, str]]:
        with self.connect() as db:
            return db.execute("""SELECT ts,body FROM diaries WHERE bot=? AND scope=? AND peer=?
                              ORDER BY id DESC LIMIT 3""", scope_key(key)).fetchall()

    def start_guess(self, key: Key, target: int) -> bool:
        with self.connect() as db:
            row = db.execute("INSERT OR IGNORE INTO guesses VALUES (?,?,?,?,0)", (*scope_key(key), target))
            return row.rowcount == 1

    def has_guess(self, key: Key) -> bool:
        with self.connect() as db:
            return db.execute("SELECT 1 FROM guesses WHERE bot=? AND scope=? AND peer=?",
                              scope_key(key)).fetchone() is not None

    def end_guess(self, key: Key) -> int | None:
        with self.connect() as db:
            row = db.execute("DELETE FROM guesses WHERE bot=? AND scope=? AND peer=? RETURNING target",
                             scope_key(key)).fetchone()
            return row[0] if row else None

    def guess(self, key: Key, value: int) -> tuple[str, int, int | None]:
        scope = scope_key(key)
        with self.connect() as db:
            row = db.execute("""UPDATE guesses SET tries=tries+1 WHERE bot=? AND scope=? AND peer=?
                              RETURNING target,tries""", scope).fetchone()
            if not row:
                return "missing", 0, None
            target, tries = row
            if value == target or tries >= 20:
                db.execute("DELETE FROM guesses WHERE bot=? AND scope=? AND peer=?", scope)
                return ("win" if value == target else "gaveup"), tries, target
            return ("high" if value > target else "low"), tries, None
