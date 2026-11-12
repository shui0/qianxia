from datetime import datetime, timedelta, timezone
import html
import json
from pathlib import Path
import re
import tempfile
import unicodedata

import httpx

SOURCE = 'https://maimai.sega.jp/data/maimai_songs.json'
SGT = timezone(timedelta(hours=8))


def normal(text: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', html.unescape(text)).casefold().split()).strip(' 《》「」“”"？?。!！')


def next_refresh(now: datetime, hour: int) -> datetime:
    now = now.astimezone(SGT)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)


class Catalog:
    def __init__(self, path: Path):
        self.path = path
        self._stamp = None
        self._songs = []
        self.updated_at = None

    def _load(self):
        try:
            stamp = self.path.stat().st_mtime_ns
            if stamp == self._stamp:
                return
            data = json.loads(self.path.read_text(encoding='utf8'))
            songs = data['songs']
            if not isinstance(songs, list) or not all(isinstance(song, dict) for song in songs):
                return
            updated = datetime.fromisoformat(data['updated_at'])
            if updated.tzinfo is None:
                return
            self._songs = songs
            self.updated_at = updated
            self._stamp = stamp
        except (OSError, ValueError, KeyError, TypeError):
            return

    def stale(self) -> bool:
        self._load()
        return (self.updated_at is None or self.updated_at.tzinfo is None
                or datetime.now(SGT) - self.updated_at >= timedelta(days=1))

    def match(self, question: str) -> dict | None:
        self._load()
        query = normal(question)
        if query in {'hi', 'hello', '你好', '你好呀', '早安', '晚安', '谢谢'}:
            return None
        musical = bool(re.search(r'maimai|舞萌|日服|でらっくす|新曲|曲名|歌曲|谱面|难度|定数', query))
        for song in sorted(self._songs, key=lambda row: len(row.get('title', '')), reverse=True):
            title = normal(song.get('title', ''))
            if not title:
                continue
            if query == title:
                return song
            if len(title) >= (3 if musical else 6) and re.search(
                r'(?<![a-z0-9])' + re.escape(title) + r'(?![a-z0-9])', query,
            ):
                return song
        return None

    def describe(self, song: dict) -> str:
        levels = []
        dx = bool(song.get('dx_lev_mas'))
        for field, label in [('bas', 'BASIC'), ('adv', 'ADVANCED'), ('exp', 'EXPERT'),
                             ('mas', 'MASTER'), ('remas', 'Re:MASTER')]:
            level = song.get(('dx_lev_' if dx else 'lev_') + field)
            if level:
                levels.append(f'{label} {level}')
        checked = self.updated_at.astimezone(SGT).isoformat(timespec='seconds') if self.updated_at else '未知'
        return (f'SEGA 日服 maimai 官方曲目目录：{song["title"]}；艺术家：{song.get("artist") or "未标注"}；'
                f'{"DX" if dx else "标准"}难度：{" / ".join(levels)}。目录核验时间：{checked}。'
                '这是日服收录信息；目录时间不是歌曲发行日，也不能据此推断国服上线或谱面定数。')

    async def refresh(self, client: httpx.AsyncClient) -> int:
        response = await client.get(SOURCE)
        response.raise_for_status()
        if len(response.content) > 5 * 1024 * 1024:
            raise ValueError('Official catalogue exceeds size limit')
        data = response.json()
        if not isinstance(data, list) or not data:
            raise ValueError('Invalid official song catalogue')
        songs = [row for row in data if isinstance(row, dict)
                 and isinstance(row.get('title'), str) and row['title'].strip()]
        if len(songs) < len(data) * .8:
            raise ValueError('Too many invalid official song rows')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        value = {'source': SOURCE, 'updated_at': datetime.now(SGT).isoformat(), 'songs': songs}
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf8', dir=self.path.parent,
                                             prefix=self.path.name + '.', suffix='.tmp', delete=False) as out:
                temporary = Path(out.name)
                json.dump(value, out, ensure_ascii=False)
            temporary.replace(self.path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
        self._load()
        return len(songs)
