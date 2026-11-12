import asyncio
import base64
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from PIL import Image
import bot_fixture
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.event import Reply
from plugins.qianxia_chat import Chat, Config
from qianxia_state import Memory
from test_chat import message


def picture_bytes(size=(1400, 900)):
    out = BytesIO()
    Image.new('RGB', size, 'red').save(out, 'PNG')
    return out.getvalue()


def image_segment(url='https://gchat.qpic.cn/test.png', file='example.image'):
    return {'type': 'image', 'data': {'url': url, 'file': file}}


class VisionInputTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_and_quoted_images_are_resized_and_sent_as_data(self):
        from qianxia_vision import Vision
        event = message(segments=[image_segment()])
        event.reply = Reply(time=1, message_type='group', message_id=2, real_id=2,
                            sender={'user_id': 9}, message=[MessageSegment(
                                **image_segment('https://multimedia.nt.qq.com.cn/quoted.png', 'quote.image'))])
        client = httpx.AsyncClient
        urls = []
        def endpoint(request):
            urls.append(str(request.url))
            return httpx.Response(200, content=picture_bytes())
        with patch('qianxia_vision.httpx.AsyncClient', side_effect=lambda **kw: client(
                transport=httpx.MockTransport(endpoint), **kw)):
            result = await Vision(Config()).read(AsyncMock(), event)
        self.assertTrue(result.present)
        self.assertEqual(len(result.images), 2)
        self.assertEqual(len(urls), 2)
        for data in result.images:
            self.assertTrue(data.startswith('data:image/jpeg;base64,'))
            with Image.open(BytesIO(base64.b64decode(data.split(',', 1)[1]))) as img:
                self.assertLessEqual(max(img.size), 768)

    async def test_expired_url_is_resolved_with_onebot_get_image(self):
        from qianxia_vision import Vision
        bot = AsyncMock()
        bot.get_image.return_value = {'url': 'https://gchat.qpic.cn/fresh.png'}
        client = httpx.AsyncClient
        def endpoint(request):
            return (httpx.Response(403) if request.url.path == '/test.png'
                    else httpx.Response(200, content=picture_bytes()))
        with patch('qianxia_vision.httpx.AsyncClient', side_effect=lambda **kw: client(
                transport=httpx.MockTransport(endpoint), **kw)):
            result = await Vision(Config()).read(bot, message(segments=[image_segment()]))
        self.assertEqual(len(result.images), 1)
        bot.get_image.assert_awaited_once_with(file='example.image')

    async def test_untrusted_urls_local_files_and_redirects_are_not_read(self):
        from qianxia_vision import Vision
        for url in ('http://127.0.0.1:11434/props', 'https://qpic.cn.evil.test/a',
                    'file:///C:/Windows/win.ini', 'https://gchat.qpic.cn/redirect'):
            bot = AsyncMock()
            client = httpx.AsyncClient
            visited = []
            def endpoint(request):
                visited.append(str(request.url))
                return httpx.Response(302, headers={'Location': 'http://127.0.0.1/private'})
            with patch('qianxia_vision.httpx.AsyncClient', side_effect=lambda **kw: client(
                    transport=httpx.MockTransport(endpoint), **kw)):
                result = await Vision(Config()).read(bot, message(segments=[image_segment(url, 'C:/private.png')]))
            self.assertFalse(result.images)
            self.assertTrue(result.note)
            self.assertFalse(any('127.0.0.1' in u for u in visited))
            bot.get_image.assert_not_awaited()

    async def test_bad_oversize_and_excess_images_do_not_reach_model(self):
        from qianxia_vision import Vision
        client = httpx.AsyncClient
        for response in (httpx.Response(200, content=b'not an image'),
                         httpx.Response(200, headers={'content-length': '99999999'}, content=b'x')):
            with patch('qianxia_vision.httpx.AsyncClient', side_effect=lambda **kw: client(
                    transport=httpx.MockTransport(lambda _: response), **kw)):
                result = await Vision(Config()).read(AsyncMock(), message(segments=[image_segment(file='')]))
            self.assertFalse(result.images)
            self.assertTrue(result.note)
        with patch('qianxia_vision.httpx.AsyncClient', side_effect=lambda **kw: client(
                transport=httpx.MockTransport(lambda _: httpx.Response(200, content=picture_bytes())), **kw)):
            result = await Vision(Config()).read(AsyncMock(), message(segments=[
                image_segment(f'https://gchat.qpic.cn/{i}.png', f'{i}.image') for i in range(4)]))
        self.assertEqual(len(result.images), 3)
        self.assertIn('3', result.note)

    def test_picture_only_mention_does_not_show_menu(self):
        from plugins.qianxia_menu import wants_menu
        event = message(group=3, segments=[{'type': 'at', 'data': {'qq': '1'}}, image_segment()])
        self.assertFalse(wants_menu(event))
        self.assertTrue(wants_menu(message(group=3, segments=[{'type': 'at', 'data': {'qq': '1'}}])))

    async def test_large_dimensions_and_stream_without_length_are_rejected(self):
        from qianxia_vision import Vision
        out = BytesIO()
        Image.new('1', (6000, 4001)).save(out, 'PNG')
        client = httpx.AsyncClient
        for content in (out.getvalue(), b'x' * (8 * 1024 * 1024 + 1)):
            def endpoint(request):
                response = httpx.Response(200, content=content)
                del response.headers['content-length']
                return response
            with patch('qianxia_vision.httpx.AsyncClient', side_effect=lambda **kw: client(
                    transport=httpx.MockTransport(endpoint), **kw)):
                result = await Vision(Config()).read(AsyncMock(), message(segments=[image_segment(file='')]))
            self.assertFalse(result.images)
            self.assertTrue(result.note)


class VisionChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_followup_waits_for_new_image_download_and_uses_new_picture(self):
        from qianxia_vision import VisualInput
        chat = Chat(Config(qianxia_search_enabled=False))
        with patch.object(chat, 'complete', return_value='旧图'):
            await chat.reply((1, None, 2), '旧图', AsyncMock(), pictures=['data:image/jpeg;base64,b2xk'])
        started, release = asyncio.Event(), asyncio.Event()
        seen = []
        async def load():
            started.set()
            await release.wait()
            return VisualInput(present=True, images=['data:image/jpeg;base64,bmV3'])
        async def complete(messages, **kw):
            seen.append(messages[-1]['content'])
            return '新图'
        with patch.object(chat, 'complete', side_effect=complete):
            first = asyncio.create_task(chat.reply((1, None, 2), '新图', AsyncMock(), load_pictures=load))
            # Avoid a hanging test if the loader never starts.
            await asyncio.wait_for(started.wait(), timeout=1)
            second = asyncio.create_task(chat.reply((1, None, 2), '这张图是什么', AsyncMock()))
            await asyncio.sleep(0)
            self.assertEqual(seen, [])
            release.set()
            await asyncio.gather(first, second)
        self.assertEqual(len(seen), 2)
        for content in seen:
            self.assertIn('bmV3', str(content))
            self.assertNotIn('b2xk', str(content))

    async def test_image_payload_and_followup_are_visual_but_history_is_text_only(self):
        data = 'data:image/jpeg;base64,' + base64.b64encode(picture_bytes()).decode()
        calls = []
        client = httpx.AsyncClient
        def endpoint(request):
            body = json.loads(request.content)
            calls.append(body)
            return httpx.Response(200, json={'choices': [{'message': {'content': '红色的方块呀。'}}]})
        with TemporaryDirectory() as tmp:
            memory = Memory(Path(tmp) / 'memory.sqlite3')
            chat = Chat(Config(qianxia_search_enabled=True), memory)
            with patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
                    transport=httpx.MockTransport(endpoint), **kw)), patch.object(
                    chat.web, 'required_query', side_effect=AssertionError('must see image before searching')):
                await chat.reply((1, 3, 2), '这张图是什么', AsyncMock(), pictures=[data])
                await chat.reply((1, 3, 2), '刚才那张图是什么颜色', AsyncMock())
            self.assertEqual(len(calls), 2)
            for body in calls:
                content = body['messages'][-1]['content']
                self.assertIsInstance(content, list)
                self.assertTrue(any(p['type'] == 'image_url' and p['image_url']['url'] == data for p in content))
            self.assertNotIn('data:image', json.dumps(list(chat.history.values())))
            self.assertNotIn('data:image', json.dumps(memory.history((1, 3, 2))))

    async def test_visual_cache_is_scoped_expiring_and_not_used_after_failed_new_image(self):
        chat = Chat(Config(qianxia_search_enabled=False))
        calls = []
        async def complete(messages, **kw):
            calls.append(messages[-1]['content'])
            return '看到了。'
        with patch.object(chat, 'complete', side_effect=complete):
            await chat.reply((1, 3, 2), '看图', AsyncMock(), pictures=['data:image/jpeg;base64,YQ=='])
            await chat.reply((1, 3, 9), '刚才那张图', AsyncMock())
            await chat.reply((1, 4, 2), '刚才那张图', AsyncMock())
            await chat.reply((1, None, 2), '刚才那张图', AsyncMock())
            self.assertTrue(all(isinstance(c, str) for c in calls[1:]))
            failed = AsyncMock()
            await chat.reply((1, 3, 2), '新图', failed, pictures=[], picture_note='图片没读到。')
            self.assertEqual(len(calls), 4)
            failed.assert_awaited_once()
            await chat.reply((1, 3, 2), '刚才那张图', AsyncMock())
            self.assertIsInstance(calls[-1], str)
            with patch('plugins.qianxia_chat.time.monotonic', return_value=10):
                await chat.reply((1, 3, 2), '看图', AsyncMock(), pictures=['data:image/jpeg;base64,YQ=='])
            with patch('plugins.qianxia_chat.time.monotonic', return_value=611):
                await chat.reply((1, 3, 2), '刚才那张图', AsyncMock())
            self.assertIsInstance(calls[-1], str)

    async def test_model_receives_current_visual_question_after_long_history(self):
        chat = Chat(Config(qianxia_search_enabled=False))
        chat.image_handler = AsyncMock()
        chat.history[(1, None, 2)] = [{'role': 'user', 'content': '历史文字' * 1000}] * 12
        client = httpx.AsyncClient
        def endpoint(request):
            body = json.loads(request.content)
            self.assertIsInstance(body['messages'][-1]['content'], list)
            self.assertIn('识别文字', str(body['messages'][-1]['content']))
            self.assertLess(len(json.dumps(body['messages'][:-1], ensure_ascii=False)), 5000)
            return httpx.Response(200, json={'choices': [{'message': {'content': '看到了。'}}]})
        with patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
                transport=httpx.MockTransport(endpoint), **kw)):
            await chat.reply((1, None, 2), '识别文字', AsyncMock(), pictures=['data:image/jpeg;base64,YQ=='])

    async def test_failed_new_visual_request_does_not_leave_old_picture_for_followup(self):
        chat = Chat(Config(qianxia_search_enabled=False))
        with patch.object(chat, 'complete', return_value='旧图。'):
            await chat.reply((1, None, 2), '旧图', AsyncMock(), pictures=['data:image/jpeg;base64,b2xk'])
        with patch.object(chat, 'complete', side_effect=httpx.ReadTimeout('model timeout')):
            with self.assertRaises(httpx.ReadTimeout):
                await chat.reply((1, None, 2), '新图', AsyncMock(), pictures=['data:image/jpeg;base64,bmV3'])
        seen = []
        async def complete(messages, **kw):
            seen.append(messages[-1]['content'])
            return '请重新发图。'
        with patch.object(chat, 'complete', side_effect=complete):
            await chat.reply((1, None, 2), '刚才那张图', AsyncMock())
        self.assertIsInstance(seen[0], str)

    async def test_visual_web_reader_retains_picture_and_cannot_recover_from_text_only_quotes(self):
        from qianxia_web import SearchResult, UNVERIFIED, UNKNOWN
        chat = Chat(Config(qianxia_search_enabled=True))
        turns = []
        client = httpx.AsyncClient
        def endpoint(request):
            body = json.loads(request.content)
            turns.append(body)
            if len(turns) == 1:
                return httpx.Response(200, json={'choices': [{'message': {'content': None, 'tool_calls': [{
                    'id': 'lookup', 'type': 'function', 'function': {'name': 'web_search',
                    'arguments': '{"query":"某游戏角色 官方"}'}}]}}]})
            self.assertIsInstance(body['messages'][-1]['content'], list)
            return httpx.Response(200, json={'choices': [{'message': {'content': UNVERIFIED}}]})
        source = SearchResult(title='官方网站', url='https://example.com/character', snippet='某角色介绍')
        with patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
                transport=httpx.MockTransport(endpoint), **kw)), patch.object(chat.web, 'search', return_value=[source]), patch.object(
                chat.web, 'read', return_value=[source]):
            sent = AsyncMock()
            await chat.reply((1, None, 2), '查查图里这个角色', sent, pictures=['data:image/jpeg;base64,YQ=='])
        self.assertEqual(len(turns), 2)
        sent.assert_awaited_once_with(UNKNOWN)
