import unittest
from unittest.mock import patch

import httpx

import bot_fixture
from plugins.qianxia_voice import synthesize


class VoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_wav_is_forwarded(self):
        client = httpx.AsyncClient
        def backend(request):
            self.assertEqual(request.url.path, "/tts")
            self.assertIn(b"qingxia", request.content)
            return httpx.Response(200, headers={"content-type": "audio/wav"},
                                  content=b"RIFFtestWAVE")
        with patch.object(httpx, "AsyncClient", side_effect=lambda **kwargs: client(
            transport=httpx.MockTransport(backend), **kwargs
        )):
            self.assertEqual(await synthesize("你好"), b"RIFFtestWAVE")

    async def test_rejects_long_text(self):
        with self.assertRaises(ValueError):
            await synthesize("字" * 201)
