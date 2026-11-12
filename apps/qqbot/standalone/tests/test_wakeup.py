import json
import unittest
from unittest.mock import Mock, patch

import httpx
import bot_fixture
from test_chat import message
from plugins.qianxia_chat import conversation_key


class WakeupTests(unittest.TestCase):
    def test_starting_with_name_is_addressed_without_at_and_respects_scope(self):
        for text in ('千夏，今天吃什么', '千夏:你好', ' 千夏 你好', '千夏帮我看看', '千夏', '千夏！'):
            event = message(group=3, segments=[{'type': 'text', 'data': {'text': text}}])
            self.assertEqual(conversation_key(event, {3}), (1, 3, 2), text)
            self.assertIsNone(conversation_key(event, {4}), text)
            event.user_id = 1
            self.assertIsNone(conversation_key(event, set()), text)

    def test_mentioning_name_in_middle_does_not_wake(self):
        for text in ('我觉得千夏很可爱', '日向千夏的新图', '「千夏，帮我」是一个例子', '/搜图 千夏'):
            event = message(group=3, segments=[{'type': 'text', 'data': {'text': text}}])
            self.assertIsNone(conversation_key(event, set()), text)

    def test_menu_and_rule_images_understand_wakeup_punctuation(self):
        from plugins.qianxia_menu import wants_menu
        from plugins.qianxia_pixiv import wants_image
        for text in ('千夏，帮助', '千夏：help', '千夏你有什么功能'):
            self.assertTrue(wants_menu(message(group=3, segments=[{'type': 'text', 'data': {'text': text}}])), text)
        for text in ('千夏，找张星空的图', '千夏：来五张日向千夏的图'):
            self.assertTrue(wants_image(message(group=3, segments=[{'type': 'text', 'data': {'text': text}}])), text)
        self.assertFalse(wants_menu(message(group=3, segments=[{'type': 'text', 'data': {'text': '千夏'}}])))


class WakeupWebSocketTests(unittest.TestCase):
    def test_no_at_text_image_menu_and_rule_images_route_once(self):
        self.assertIsNotNone(conversation_key(message(group=12345, segments=[
            {'type': 'text', 'data': {'text': '千夏，在吗'}}]), set()))
        from fastapi.testclient import TestClient
        import nonebot
        from plugins.qianxia_chat import chat, pending, config
        from plugins.qianxia_menu import TEXT
        from qianxia_vision import VisualInput
        from nonebot.adapters.onebot.v11 import MessageSegment
        requests = []
        real_client = httpx.AsyncClient
        def model(request):
            body = json.loads(request.content)
            requests.append(body)
            return httpx.Response(200, json={'choices': [{'message': {'content': '醒着呢！'}}]})
        def send(socket, text, *, image=False):
            segments = [{'type': 'text', 'data': {'text': text}}]
            if image:
                segments.append({'type': 'image', 'data': {'file': 'test.image', 'url': 'https://gchat.qpic.cn/test'}})
            socket.send_json(message(group=12345, user=23456, segments=segments).model_dump(mode='json'))
        def reply(socket):
            body = socket.receive_json()
            self.assertEqual(body['action'], 'send_msg')
            socket.send_json({'status': 'ok', 'retcode': 0, 'data': {'message_id': 77}, 'echo': body['echo']})
            return ''.join(p['data']['text'] for p in body['params']['message'] if p['type'] == 'text')
        async def image_action(key, query):
            from nonebot.matcher import current_matcher
            await current_matcher.get().send(MessageSegment.text(f'规则搜图:{query.keyword}:{query.count}'))
            return query.count
        # The test uses an isolated in-memory scope and restores the singleton
        # history/cache because other WebSocket tests inspect those explicitly.
        history = chat.history.copy()
        pictures = chat.last_pictures.copy()
        try:
            with patch.object(httpx, 'AsyncClient', side_effect=lambda **kw: real_client(
                    transport=httpx.MockTransport(model), **kw)), patch.object(
                    chat.vision, 'read', return_value=VisualInput(True, ['data:image/jpeg;base64,YQ=='])), patch.object(
                    chat, 'image_handler', side_effect=image_action), patch.object(
                    config, 'qianxia_proactive_probability', 1), TestClient(nonebot.get_app()) as app:
                with app.websocket_connect('/onebot/v11/ws', headers={
                        'x-self-id': '1', 'authorization': 'Bearer test-only-token'}) as socket:
                    for text in ('千夏，在吗', '千夏！'):
                        send(socket, text)
                        self.assertEqual(reply(socket), '醒着呢！')
                    send(socket, '千夏，这张图是什么', image=True)
                    self.assertEqual(reply(socket), '醒着呢！')
                    self.assertIsInstance(requests[-1]['messages'][-1]['content'], list)
                    queued = Mock()
                    pending[(1, 12345)] = queued
                    send(socket, '千夏：帮助')
                    self.assertEqual(reply(socket), TEXT)
                    queued.cancel.assert_called_once_with()
                    self.assertNotIn((1, 12345), pending)
                    send(socket, '千夏：找张星空的图')
                    self.assertEqual(reply(socket), '规则搜图:星空:1')
                    self.assertEqual(len(requests), 3)
                    self.assertEqual(requests[0]['messages'][-1]['content'], '在吗')
                    self.assertNotIn((1, 12345), pending)
        finally:
            pending.pop((1, 12345), None)
            chat.history.clear(); chat.history.update(history)
            chat.last_pictures.clear(); chat.last_pictures.update(pictures)
