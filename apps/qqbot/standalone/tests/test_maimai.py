import base64
from collections import OrderedDict
from io import BytesIO
import json
import unittest
from unittest.mock import patch

from PIL import Image

import bot_fixture

from plugins.qianxia_maimai import b50_reply, command_args, run_maimai
from qianxia_b50 import b50_sections, cover_id, load_b50_covers


class MaimaiTests(unittest.IsolatedAsyncioTestCase):
    async def test_cover_ids_are_shared_and_missing_covers_are_optional(self):
        self.assertEqual(cover_id({"song_id": "10038"}), 38)
        self.assertEqual(cover_id({"song_id": 11001}), 11001)
        self.assertIsNone(cover_id({"song_id": "../38"}))
        data = {"charts": {"sd": [{"song_id": 38}], "dx": [{"song_id": 10038}, {"song_id": 99}]}}
        thumb = Image.new("RGB", (128, 128), "red")
        with patch("qianxia_b50.cover_cache", OrderedDict()), patch(
            "qianxia_b50.fetch_cover", side_effect=lambda _, song: thumb if song == 38 else None
        ) as fetch:
            self.assertEqual(await load_b50_covers(data), {38: thumb})
            self.assertEqual([call.args[1] for call in fetch.await_args_list], [38, 99])
            self.assertEqual(await load_b50_covers({"charts": {"dx": [{"song_id": 10038}]}}), {38: thumb})
            self.assertEqual(fetch.await_count, 2)

    async def test_b50_renders_both_complete_sections(self):
        def rows(count):
            return [{"title": f"测试曲目 {index}", "ra": 300 + index, "level_index": 3,
                     "ds": 13.8, "achievements": 100.5} for index in range(count)]
        data = {"nickname": "测试玩家", "rating": 15000, "charts": {"sd": rows(35), "dx": rows(15)}}
        sections = b50_sections(data)
        self.assertEqual([len(section[2]) for section in sections], [35, 15])
        self.assertEqual(sections[0][2][0]["ra"], 334)
        argv = ["player", "--json", "--qq", "123456"]
        with patch("plugins.qianxia_maimai.run_cli", return_value=json.dumps(data)) as cli:
            result = await b50_reply(argv)
            cli.assert_awaited_once_with("maimai", argv, output_limit=None)
        self.assertEqual(result.type, "image")
        png = base64.b64decode(result.data["file"].removeprefix("base64://"))
        with Image.open(BytesIO(png)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertGreater(image.height, 1100)

    def test_b50_defaults_to_sender_qq(self):
        self.assertEqual(command_args("B50", "onebot:1:2", private=False, sender_qq=2),
                         ["player", "--json", "--openid", "onebot:1:2", "--fallback-qq", "2"])
        self.assertEqual(command_args("B50 123456", "onebot:1:2", private=True, sender_qq=2),
                         ["player", "--json", "--qq", "123456"])

    async def test_local_queries(self):
        self.assertIn("309", await run_maimai(["rating", "--ds", "13.8", "--ach", "100.5"]))
        self.assertIn("Grievous", await run_maimai(["search", "Grievous"]))
        self.assertIn("MASTER", await run_maimai(["song", "Grievous", "--notes"]))

    def test_binding_uses_sender(self):
        args = command_args("绑定 用户名", "onebot:1:2", private=True)
        self.assertEqual(args, ["bind", "--openid", "onebot:1:2", "--username", "用户名"])
        with self.assertRaises(ValueError):
            command_args("令牌 secret", "onebot:1:2", private=False)
        with self.assertRaises(ValueError):
            command_args("推分", "onebot:1:2", private=False)
        self.assertEqual(command_args("推分", "onebot:1:2", private=True),
                         ["player", "--openid", "onebot:1:2", "--all"])

    def test_invalid_rating(self):
        for value in ("nan", "inf", "-1"):
            with self.assertRaises(ValueError):
                command_args(f"评分 {value} 100.5", "onebot:1:2", private=True)
