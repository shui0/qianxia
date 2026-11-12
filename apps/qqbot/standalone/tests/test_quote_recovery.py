import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
import bot_fixture
from plugins.qianxia_chat import Chat, Config
from qianxia_web import SearchResult, UNKNOWN, recover_quotes


class QuoteRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def test_quote_spanning_multiple_source_records_keeps_their_boundaries(self):
        body = 'Aster\nType A\nRuntime 15 hours\n\nCedar\nType B\nRuntime 15 hours'
        raw = json.dumps({'quotes': [{'source_id': 1, 'text': ' '.join(body.split())}]})
        result = recover_quotes(raw, [SearchResult('Report', 'https://example.com/a', body)])
        self.assertEqual(result.count('• '), 2)
        self.assertIn('• Aster', result)
        self.assertIn('• Cedar', result)

    async def test_reader_refusal_can_recover_only_verbatim_sourced_facts(self):
        for quote, expected in [('产品甲的续航为15小时。', '产品甲'),
                                ('产品乙的续航为99小时。', UNKNOWN)]:
            chat = Chat(Config(qianxia_search_read_enabled=False, qianxia_web_persona_enabled=False))
            calls = []
            client = httpx.AsyncClient
            def endpoint(request):
                calls.append(json.loads(request.content))
                text = '[无法查证]' if len(calls) == 1 else json.dumps({
                    'quotes': [{'source_id': 1, 'text': quote}],
                }, ensure_ascii=False)
                return httpx.Response(200, json={'choices': [{'message': {'content': text}}]})
            with patch.object(chat.web, 'search', new_callable=AsyncMock, return_value=[
                SearchResult('测试表', 'https://example.com/a', '产品甲的续航为15小时。产品乙的续航为9小时。', content_kind='page_excerpt'),
            ]), patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
                transport=httpx.MockTransport(endpoint), **kw)):
                answer = await chat.complete([{'role':'user','content':'产品15小时有哪些'}], use_web=True)
            self.assertEqual(len(calls), 2)
            self.assertIn(expected, answer)
            if expected != UNKNOWN:
                self.assertIn('https://example.com/a', answer)

    async def test_empty_recovery_does_not_turn_unrelated_results_into_an_answer(self):
        chat = Chat(Config(qianxia_search_read_enabled=False, qianxia_web_persona_enabled=False))
        client = httpx.AsyncClient
        calls = []
        def endpoint(request):
            calls.append(request)
            text = '[无法查证]' if len(calls) == 1 else '{"quotes":[]}'
            return httpx.Response(200, json={'choices':[{'message':{'content':text}}]})
        with patch.object(chat.web, 'search', new_callable=AsyncMock, return_value=[
            SearchResult('别的活动', 'https://example.com/other', '这里没有所问活动的资料。'),
        ]), patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
            transport=httpx.MockTransport(endpoint), **kw)):
            answer = await chat.complete([{'role':'user','content':'星砂节有哪些活动'}], use_web=True)
        self.assertEqual(answer, UNKNOWN)
        self.assertEqual(len(calls), 2)
