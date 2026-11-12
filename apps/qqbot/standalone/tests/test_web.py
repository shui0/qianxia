import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

import bot_fixture
from plugins.qianxia_chat import Chat, Config as ChatConfig
from qianxia_web import Search, SearchConfig, SearchError, SearchResult, recent_window


class Config(ChatConfig):
    # Retrieval itself is exercised separately in test_web_body; these tests isolate chat/search.
    qianxia_search_read_enabled: bool = False
    qianxia_web_persona_enabled: bool = False


class SearchTests(unittest.IsolatedAsyncioTestCase):
    def test_sourced_reply_deduplicates_model_reference_links_without_deleting_facts(self):
        from qianxia_web import sourced_reply
        rows = [SearchResult('页面', 'https://example.com/one', '资料')]
        answer = sourced_reply('我给你找来啦，这里有结果。[1]\n\n[1] https://example.com/one', rows)
        self.assertIn('我给你找来啦，这里有结果。[1]', answer)
        self.assertEqual(answer.count('https://example.com/one'), 1)
        self.assertIn('来源：', answer)
        direct = sourced_reply('官网地址是 https://example.com/one ，就在这里。[1]', rows)
        self.assertIn('官网地址是 https://example.com/one', direct)

    def test_citations_keep_only_used_sources_without_changing_ids(self):
        from qianxia_web import citations
        rows = [SearchResult('第一来源', 'https://example.com/one', '一'),
                SearchResult('第二来源', 'https://example.com/two', '二'),
                SearchResult('第三来源', 'https://example.com/three', '三')]
        result = citations(rows, '这个答案来自这里。[2]')
        self.assertIn('[2] 第二来源', result)
        self.assertIn('https://example.com/two', result)
        self.assertNotIn('https://example.com/one', result)
        self.assertNotIn('https://example.com/three', result)
        self.assertIn('https://example.com/one', citations(rows, '没有内文编号的简短答案'))

    async def test_search_filters_unsafe_duplicate_links_and_bounds_content(self):
        rows = [
            {'title': 'bad', 'href': 'javascript:alert(1)', 'body': 'bad'},
            {'title': '文档', 'href': 'https://nonebot.dev/docs/', 'body': '资料' * 1000},
            {'title': 'duplicate', 'href': 'https://nonebot.dev/docs/', 'body': 'duplicate'},
            {'title': '源码', 'href': 'https://github.com/nonebot/nonebot2', 'body': '官方仓库'},
        ]
        with patch('qianxia_web.DDGS') as factory:
            factory.return_value.text.return_value = rows
            result = await Search(Config(qianxia_search_provider='ddgs')).search('请问 NoneBot2 是什么项目？')
        self.assertEqual([r.title for r in result], ['文档', '源码'])
        self.assertLessEqual(len(result[0].snippet), 240)
        self.assertEqual(factory.return_value.text.call_args.args[0], 'NoneBot2')

    async def test_empty_results_and_empty_queries_are_explicit_failures(self):
        with patch('qianxia_web.DDGS') as factory:
            factory.return_value.text.return_value = []
            with self.assertRaises(SearchError):
                await Search(Config(qianxia_search_provider='ddgs')).search('不存在的资料')
            with self.assertRaises(SearchError):
                await Search(Config(qianxia_search_provider='ddgs')).search('  ')

    async def test_exa_is_default_and_parses_official_sse_results(self):
        search = Search(SearchConfig())
        calls = []
        text = ('Title: 官方文档\nURL: https://nonebot.dev/docs/\nPublished: N/A\nHighlights:\n'
                + '现代 Python 聊天机器人框架。' * 100
                + '\n\n---\n\nTitle: unsafe\nURL: javascript:alert(1)\nHighlights:\nignore')
        def endpoint(request):
            calls.append(request)
            self.assertEqual(request.url.host, 'mcp.exa.ai')
            body = json.loads(request.content)
            self.assertEqual(body['method'], 'tools/call')
            self.assertEqual(body['params']['name'], 'web_search_advanced_exa')
            self.assertEqual(body['params']['arguments']['highlightsQuery'], 'NoneBot2 官方文档')
            self.assertGreaterEqual(body['params']['arguments']['textMaxCharacters'], 10000)
            self.assertNotIn('x-api-key', request.headers)
            payload = {'jsonrpc': '2.0', 'id': 1, 'result': {'content': [{'type': 'text', 'text': text}]}}
            return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                                  text='event: message\ndata: ' + json.dumps(payload) + '\n\n')
        client = httpx.AsyncClient
        with patch('qianxia_web.httpx.AsyncClient', side_effect=lambda **kw: client(
            transport=httpx.MockTransport(endpoint), **kw
        )), patch('qianxia_web.DDGS') as old_provider:
            rows = await search.search('NoneBot2 官方文档')
        old_provider.assert_not_called()
        self.assertEqual(len(calls), 1)
        self.assertEqual([r.url for r in rows], ['https://nonebot.dev/docs/'])
        self.assertLessEqual(len(rows[0].snippet), 400)

    async def test_exa_key_auth_and_json_response(self):
        client = httpx.AsyncClient
        def endpoint(request):
            self.assertEqual(request.headers.get('x-api-key'), 'test-only-exa-key')
            return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': {'content': [{
                'type': 'text', 'text': 'Title: 项目\nURL: https://example.com/\nText: 公开资料',
            }]}})
        with patch('qianxia_web.httpx.AsyncClient', side_effect=lambda **kw: client(
            transport=httpx.MockTransport(endpoint), **kw
        )):
            rows = await Search(Config(qianxia_exa_api_key='test-only-exa-key')).search('公开资料')
        self.assertEqual(rows[0].snippet, '公开资料')

    async def test_exa_rate_limit_falls_back_to_existing_search(self):
        client = httpx.AsyncClient
        with patch('qianxia_web.httpx.AsyncClient', side_effect=lambda **kw: client(
            transport=httpx.MockTransport(lambda _: httpx.Response(429)), **kw
        )), patch('qianxia_web.DDGS') as old_provider:
            old_provider.return_value.text.return_value = [{
                'title': '备用来源', 'href': 'https://example.com/backup', 'body': '可查证资料',
            }]
            rows = await Search(Config()).search('资料')
        self.assertEqual(rows[0].url, 'https://example.com/backup')
        old_provider.assert_called_once()

    async def test_exa_protocol_failure_without_fallback_is_explicit(self):
        client = httpx.AsyncClient
        for payload in [
            {'jsonrpc': '2.0', 'id': 1, 'error': {'code': -32603, 'message': 'failed'}},
            {'jsonrpc': '2.0', 'id': 1, 'result': {'isError': True, 'content': []}},
        ]:
            with patch('qianxia_web.httpx.AsyncClient', side_effect=lambda **kw: client(
                transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)), **kw
            )), patch('qianxia_web.DDGS') as old_provider:
                with self.assertRaises(SearchError):
                    await Search(Config(qianxia_search_fallback=False)).search('资料')
            old_provider.assert_not_called()

    async def test_recent_news_uses_live_content_and_publication_window(self):
        client = httpx.AsyncClient
        calls = []
        def endpoint(request):
            body = json.loads(request.content)
            calls.append(body)
            self.assertEqual(body['params']['name'], 'web_search_advanced_exa')
            args = body['params']['arguments']
            self.assertEqual(args['maxAgeHours'], 0)
            self.assertIn('startPublishedDate', args)
            self.assertIn('endPublishedDate', args)
            return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': {'content': [{
                'type': 'text', 'text': json.dumps({'results': [{
                    'title': '新闻', 'url': 'https://example.com/news',
                    'publishedDate': '2026-11-11', 'text': '发生了一件事。',
                }]}),
            }]}})
        with patch('qianxia_web.httpx.AsyncClient', side_effect=lambda **kw: client(
            transport=httpx.MockTransport(endpoint), **kw
        )):
            rows = await Search(Config(qianxia_search_fallback=False)).search('今天发生了什么新闻？')
        self.assertEqual(rows[0].published_at, '2026-11-11')
        self.assertEqual(len(calls), 1)

    def test_relative_news_dates_follow_client_timezone(self):
        from datetime import datetime, timezone, timedelta
        now = datetime(2026, 11, 11, 12, tzinfo=timezone(timedelta(hours=8)))
        self.assertEqual(recent_window('今天有什么新闻', now), ('2026-11-11', '2026-11-12'))
        self.assertEqual(recent_window('昨天发生了什么事', now), ('2026-11-10', '2026-11-11'))
        self.assertEqual(recent_window('最近舞萌日服有什么更新', now), ('2026-10-12', '2026-11-12'))
        self.assertIsNone(recent_window('今天心情怎么样', now))

    async def test_jp_news_domain_filter_does_not_apply_to_cn(self):
        client = httpx.AsyncClient
        for query, expected in [('最近舞萌日服有什么更新', True), ('最近舞萌国服有什么更新', False)]:
            def endpoint(request):
                args = json.loads(request.content)['params']['arguments']
                self.assertEqual('includeDomains' in args, expected)
                return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': {'content': [{
                    'type': 'text', 'text': json.dumps({'results': [{
                        'title': '公告', 'url': 'https://example.com/news', 'text': '更新信息',
                    }]}),
                }]}})
            with patch('qianxia_web.httpx.AsyncClient', side_effect=lambda **kw: client(
                transport=httpx.MockTransport(endpoint), **kw
            )):
                await Search(Config(qianxia_search_fallback=False)).search(query)


class WebChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_list_questions_search_before_a_confident_model_guess(self):
        client = httpx.AsyncClient
        for question in ('游戏甲有哪些公开扩展包', '有哪些支持蓝牙的开源键盘'):
            chat = Chat(Config())
            def endpoint(request):
                body = json.loads(request.content)
                self.assertEqual(json.loads(body['messages'][-1]['content'])['question'], question)
                return httpx.Response(200, json={'choices': [{'message': {'content': '确认有这些条目。[1]'}}]})
            with patch.object(chat.web, 'search', new_callable=AsyncMock, return_value=[
                SearchResult('条目说明', 'https://example.com/items', '确认的条目列表。'),
            ]) as search, patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
                transport=httpx.MockTransport(endpoint), **kw)):
                await chat.complete([{'role': 'user', 'content': question}], use_web=True)
            search.assert_awaited_once_with(question)
        self.assertIsNone(Search(Config()).required_query('你有哪些兴趣爱好'))

    async def test_sourced_cautious_answer_is_not_replaced_by_unknown(self):
        client = httpx.AsyncClient
        for draft in [
            '是 maimai 日服收录曲，艺术家是お月さま交響曲。难度大概是 MASTER 14+ [1]。',
            '是 maimai 日服收录曲，MASTER 14+ [1]。国服什么时候上线我不知道。',
        ]:
            chat = Chat(Config())
            with patch.object(chat.web, 'search', new_callable=AsyncMock, return_value=[
                SearchResult('官方曲目', 'https://music-am.sega.jp/songs/song-02507/',
                             'Aegisfortia；お月さま交響曲；MASTER 14+'),
            ]), patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
                transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
                    'choices': [{'message': {'content': draft}}],
                })), **kw
            )):
                answer = await chat.complete([{'role': 'user', 'content': 'aegisfortia这个是什么'}],
                                             use_web=True, forced_query='aegisfortia')
            self.assertTrue(answer.startswith(draft))
            self.assertIn('https://music-am.sega.jp/songs/song-02507/', answer)

    async def test_unsourced_guesses_and_unverified_marker_remain_unknown(self):
        from qianxia_web import UNKNOWN
        client = httpx.AsyncClient
        for draft in ['凭印象可能是个祭典。', '可能是个祭典。[99]', '[无法查证][1]']:
            chat = Chat(Config())
            with patch.object(chat.web, 'search', new_callable=AsyncMock, return_value=[
                SearchResult('其他资料', 'https://example.com/other', '仅同名词条，无法确认。'),
            ]), patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
                transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
                    'choices': [{'message': {'content': draft}}],
                })), **kw
            )):
                answer = await chat.complete([{'role': 'user', 'content': '星砂节是什么'}],
                                             use_web=True, forced_query='星砂节')
            self.assertEqual(answer, UNKNOWN)

    async def test_bare_lowercase_jp_song_is_identified_before_model_answer(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from qianxia_jp import Catalog, SOURCE
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'jp.json'
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[{
                'title': 'Aegisfortia', 'artist': 'お月さま交響曲', 'dx_lev_mas': '14+',
            }]))) as client:
                await Catalog(path).refresh(client)
            chat = Chat(Config(qianxia_maimai_jp_cache=path))
            client_type = httpx.AsyncClient
            def endpoint(request):
                body = json.loads(request.content)
                self.assertEqual(json.loads(body['messages'][-1]['content'])['question'], 'aegisfortia')
                return httpx.Response(200, json={'choices': [{'message': {'content': 'Aegisfortia 是日服舞萌收录曲。[1]'}}]})
            with patch.object(chat.web, 'search', new_callable=AsyncMock, return_value=[
                SearchResult('日服官方曲库', SOURCE, 'Aegisfortia，お月さま交響曲，MASTER 14+'),
            ]) as search, patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client_type(
                transport=httpx.MockTransport(endpoint), **kw
            )):
                answer = await chat.complete([{'role': 'user', 'content': 'aegisfortia'}], use_web=True)
            self.assertIn('Aegisfortia', search.call_args.args[0])
            self.assertIn('日服', answer)
            search.assert_awaited_once()
    async def test_recent_factual_question_is_checked_before_model_can_use_old_memory(self):
        chat = Chat(Config())
        client = httpx.AsyncClient
        def endpoint(request):
            body = json.loads(request.content)
            self.assertEqual(json.loads(body['messages'][-1]['content'])['question'], '最近舞萌日服更新了什么新曲？')
            return httpx.Response(200, json={'choices': [{'message': {'content': '根据今天的公告，追加了歌曲。[1]'}}]})
        with patch.object(chat.web, 'search', new_callable=AsyncMock, return_value=[
            SearchResult('公告', 'https://example.com/news', '今日追加歌曲。'),
        ]) as search, patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
            transport=httpx.MockTransport(endpoint), **kw
        )):
            answer = await chat.complete([{'role': 'user', 'content': '最近舞萌日服更新了什么新曲？'}], use_web=True)
        search.assert_awaited_once()
        self.assertIn('https://example.com/news', answer)
    async def test_unknown_draft_is_searched_before_any_reply_is_sent(self):
        chat = Chat(Config())
        requests = []
        sent = []
        async def search(query):
            self.assertEqual(sent, [])
            self.assertEqual(query, '星砂节是什么活动？')
            return [SearchResult('活动公告', 'https://example.com/event', '星砂节是一个音乐活动。')]
        def backend(request):
            body = json.loads(request.content)
            requests.append(body)
            if len(requests) == 1:
                return httpx.Response(200, json={'choices': [{'message': {
                    'content': '这个我没听说过，不太清楚，凭印象可能是个祭典。',
                }}]})
            self.assertNotIn('凭印象可能是个祭典', json.dumps(body, ensure_ascii=False))
            self.assertEqual(json.loads(body['messages'][-1]['content'])['question'], '星砂节是什么活动？')
            return httpx.Response(200, json={'choices': [{'message': {'content': '公告说是音乐活动。[1]'}}]})
        client = httpx.AsyncClient
        async def send(answer): sent.append(answer)
        with patch.object(chat.web, 'search', side_effect=search) as search_call, \
             patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
                 transport=httpx.MockTransport(backend), **kw)):
            await chat.reply((1, None, 2), '星砂节是什么活动？', send)
        search_call.assert_awaited_once()
        self.assertEqual(len(sent), 1)
        self.assertIn('https://example.com/event', sent[0])
        self.assertNotIn('凭印象', str(chat.history))

    async def test_unknown_with_empty_search_does_not_invent_an_answer(self):
        from qianxia_web import EmptySearch
        chat = Chat(Config())
        client = httpx.AsyncClient
        transport = httpx.MockTransport(lambda _: httpx.Response(200, json={
            'choices': [{'message': {'content': '我不知道这个活动。'}}],
        }))
        with patch.object(chat.web, 'search', new_callable=AsyncMock,
                          side_effect=EmptySearch('no results')) as search, \
             patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
                 transport=transport, **kw)):
            answer = await chat.complete([{'role': 'user', 'content': '星砂节是什么？'}], use_web=True)
        search.assert_awaited_once()
        self.assertIn('不知道', answer)
        self.assertNotIn('来源', answer)

    async def test_unrelated_results_cannot_be_used_to_guess(self):
        chat = Chat(Config())
        client = httpx.AsyncClient
        transport = httpx.MockTransport(lambda _: httpx.Response(200, json={
            'choices': [{'message': {'content': '[无法查证]'}}],
        }))
        with patch.object(chat.web, 'search', new_callable=AsyncMock, return_value=[
            SearchResult('其他活动', 'https://example.com/other', '资料未提及问题里的活动。'),
        ]) as search, patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
            transport=transport, **kw)):
            answer = await chat.complete([{'role': 'user', 'content': '星砂节是什么？'}],
                                         use_web=True, forced_query='星砂节')
        search.assert_awaited_once()
        self.assertIn('不知道', answer)
        self.assertNotIn('[无法查证]', answer)
        self.assertNotIn('https://example.com/other', answer)

    async def test_small_talk_and_disabled_search_do_not_start_web_queries(self):
        client = httpx.AsyncClient
        for question, draft, use_web, enabled in [
            ('你好呀', '你好呀！', True, True),
            ('你喜欢我吗', '我不知道你想要什么答案，但很高兴见到你。', True, True),
            ('这首歌的名字是什么', '这首歌叫《不知道》。', True, True),
            ('我的API Key你知道吗', '这个我不知道。', True, True),
            ('星砂节是什么', '这个我不知道。', False, True),
            ('星砂节是什么', '这个我不知道。', True, False),
        ]:
            chat = Chat(Config(qianxia_search_enabled=enabled))
            transport = httpx.MockTransport(lambda _: httpx.Response(200, json={
                'choices': [{'message': {'content': draft}}],
            }))
            with patch.object(chat.web, 'search', new_callable=AsyncMock) as search, \
                 patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
                     transport=transport, **kw)):
                self.assertEqual(await chat.complete([{'role': 'user', 'content': question}],
                                                      use_web=use_web), draft)
            search.assert_not_awaited()

    async def test_model_tool_search_receives_evidence_and_appends_real_source(self):
        chat = Chat(Config())
        calls = []
        def backend(request):
            body = json.loads(request.content)
            calls.append(body)
            if len(calls) == 1:
                return httpx.Response(200, json={'choices': [{'message': {
                    'role': 'assistant', 'content': None,
                    'tool_calls': [{'id': 'lookup-1', 'type': 'function', 'function': {
                        'name': 'web_search', 'arguments': json.dumps({'query': 'NoneBot2 官方文档'})}}],
                }}]})
            evidence = json.loads(body['messages'][-1]['content'])
            self.assertEqual(evidence['retrieval']['query'], 'NoneBot2 官方文档')
            self.assertIn('官方资料', body['messages'][-1]['content'])
            self.assertNotIn('tools', body)
            return httpx.Response(200, json={'choices': [{'message': {'content': '我查到官方文档啦。[1]'}}]})
        client = httpx.AsyncClient
        with patch.object(chat.web, 'search', new_callable=AsyncMock, return_value=[
            SearchResult('文档', 'https://nonebot.dev/docs/', '官方资料'),
        ]) as search, patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
            transport=httpx.MockTransport(backend), **kw
        )):
            answer = await chat.complete([{'role': 'user', 'content': '帮我联网查 NoneBot2 文档'}], use_web=True)
        search.assert_awaited_once_with('NoneBot2 官方文档')
        self.assertIn('https://nonebot.dev/docs/', answer)
        self.assertEqual(len(calls), 2)

    async def test_search_failure_cannot_be_misreported_as_a_verified_answer(self):
        chat = Chat(Config())
        with patch.object(chat.web, 'search', new_callable=AsyncMock, side_effect=SearchError('offline')):
            answer = await chat.complete([{'role': 'user', 'content': '查新闻'}],
                                         use_web=True, forced_query='今天的新闻')
        self.assertIn('没搜成功', answer)
        self.assertNotIn('来源', answer)

    async def test_forced_search_sends_only_bounded_evidence_and_saves_plain_history(self):
        chat = Chat(Config())
        sent = []
        def backend(request):
            body = json.loads(request.content)
            self.assertNotIn('tools', body)
            self.assertIn('网页资料', body['messages'][-1]['content'])
            return httpx.Response(200, json={'choices': [{'message': {'content': '查到了。[1]'}}]})
        client = httpx.AsyncClient
        async def send(text): sent.append(text)
        with patch.object(chat.web, 'search', new_callable=AsyncMock, return_value=[
            SearchResult('文档', 'https://nonebot.dev/', '网页资料'),
        ]), patch('plugins.qianxia_chat.httpx.AsyncClient', side_effect=lambda **kw: client(
            transport=httpx.MockTransport(backend), **kw
        )):
            await chat.reply((1, None, 2), 'NoneBot2', send, forced_query='NoneBot2')
        self.assertIn('https://nonebot.dev/', sent[0])
        self.assertEqual([t['role'] for t in chat.history[(1, None, 2)]], ['user', 'assistant'])
        self.assertNotIn('网页资料', str(chat.history[(1, None, 2)]))

    async def test_search_command_reports_model_connection_failures(self):
        from nonebot.adapters.onebot.v11 import Message
        from plugins.qianxia_search import chat as search_chat, matcher, search_web
        from test_chat import message
        with patch.object(search_chat, 'reply', new_callable=AsyncMock, side_effect=httpx.ConnectError('offline')), \
             patch.object(matcher, 'finish', new_callable=AsyncMock) as finish:
            try:
                await search_web(message(), Message('NoneBot2'))
            except httpx.HTTPError:
                pass
        finish.assert_awaited_once()
        self.assertIn('没连上', finish.call_args.args[0])
