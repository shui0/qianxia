import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
import nonebot
from fastapi.testclient import TestClient

import bot_fixture
from plugins.qianxia_chat import chat
from qianxia_web import SearchResult, UNKNOWN
from test_chat import message


class SearchDeliveryTests(unittest.TestCase):
    def test_original_qq_question_delivers_sourced_answer(self):
        draft = '是 maimai 日服收录曲，作者是お月さま交響曲，难度大概是 MASTER 14+ [1]。'
        url = 'https://music-am.sega.jp/songs/song-02507/'
        client = httpx.AsyncClient
        with patch.object(chat.web, 'required_query', return_value='aegisfortia'), \
             patch.object(chat.web, 'search', new_callable=AsyncMock, return_value=[
                 SearchResult('官方曲目', url, 'Aegisfortia；お月さま交響曲；MASTER 14+'),
             ]), patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
                 transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
                     'choices': [{'message': {'content': draft}}],
                 })), **kw
             )), TestClient(nonebot.get_app()) as app:
            with app.websocket_connect('/onebot/v11/ws', headers={
                'Authorization': 'Bearer test-only-token', 'X-Self-ID': '1',
            }) as socket:
                event = message(user=98765, segments=[
                    {'type': 'text', 'data': {'text': 'aegisfortia这个是什么'}},
                ])
                socket.send_json(event.model_dump(mode='json'))
                response = socket.receive_json()
                socket.send_json({'status': 'ok', 'retcode': 0, 'data': {'message_id': 123},
                                  'echo': response['echo']})
                self.assertEqual(response['action'], 'send_msg')
                body = json.dumps(response['params']['message'], ensure_ascii=False)
                self.assertIn(draft, body)
                self.assertIn(url, body)
                self.assertNotIn(UNKNOWN, body)
