import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from datetime import datetime, timedelta, timezone

import httpx

from qianxia_jp import Catalog, next_refresh


SONGS = [{
    'title': 'Aegisfortia', 'artist': 'お月さま交響曲', 'catcode': 'maimai',
    'dx_lev_bas': '6', 'dx_lev_adv': '9', 'dx_lev_exp': '12+', 'dx_lev_mas': '14+',
    'release': '000000', 'version': '26513',
}]


class CatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_makes_official_jp_song_available_case_insensitively(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'jp.json'
            catalogue = Catalog(path)
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=SONGS)
            )) as client:
                await catalogue.refresh(client)
            self.assertFalse(catalogue.stale())
            match = catalogue.match('aegisfortia')
            self.assertEqual(match['title'], 'Aegisfortia')
            self.assertEqual(catalogue.match('你知道 AEGISFORTIA 吗')['artist'], 'お月さま交響曲')
            text = catalogue.describe(match)
            self.assertIn('日服', text)
            self.assertIn('14+', text)
            self.assertNotIn('2026-08-07', text)
            self.assertEqual(Catalog(path).match('Aegisfortia')['title'], match['title'])

    async def test_bad_refresh_keeps_previous_valid_catalogue(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'jp.json'
            catalogue = Catalog(path)
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=SONGS)
            )) as client:
                await catalogue.refresh(client)
            original = path.read_bytes()
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={'error': 'maintenance'})
            )) as client:
                with self.assertRaises(ValueError):
                    await catalogue.refresh(client)
            self.assertEqual(path.read_bytes(), original)
            self.assertIsNotNone(catalogue.match('aegisfortia'))

    def test_daily_refresh_is_at_eight_in_client_timezone(self):
        tz = timezone(timedelta(hours=8))
        before = datetime(2026, 11, 11, 7, 59, tzinfo=tz)
        after = datetime(2026, 11, 11, 9, 0, tzinfo=tz)
        self.assertEqual(next_refresh(before, 8), datetime(2026, 11, 11, 8, tzinfo=tz))
        self.assertEqual(next_refresh(after, 8), datetime(2026, 11, 12, 8, tzinfo=tz))

    async def test_background_worker_records_next_run_and_stops_cleanly(self):
        import asyncio
        import os
        from unittest.mock import patch
        import bot_fixture
        from plugins import qianxia_catalog as plugin
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'jp.json'
            catalogue = Catalog(path)
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=SONGS)
            )) as client:
                await catalogue.refresh(client)
            cfg = plugin.config.model_copy(update={'qianxia_maimai_jp_cache': path,
                'qianxia_maimai_jp_refresh_enabled': True, 'qianxia_maimai_jp_refresh_hour': 8})
            with patch.object(plugin, 'config', cfg), patch.object(plugin, 'catalog', catalogue), patch.object(plugin, 'task', None):
                await plugin.start_refresh()
                try:
                    status = path.with_suffix('.schedule.json')
                    async with asyncio.timeout(1):
                        while not status.exists():
                            await asyncio.sleep(.01)
                    record = json.loads(status.read_text(encoding='utf8'))
                    self.assertEqual(record['pid'], os.getpid())
                    self.assertEqual(datetime.fromisoformat(record['next_refresh']).hour, 8)
                finally:
                    await plugin.stop_refresh()
