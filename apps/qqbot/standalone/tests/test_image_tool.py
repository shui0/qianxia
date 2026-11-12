import json
import unittest
from unittest.mock import AsyncMock,patch

import httpx
import bot_fixture
from plugins.qianxia_chat import Chat,Config


class ImageToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_ai_request_dispatches_once_and_records_actual_count(self):
        chat=Chat(Config())
        execute=AsyncMock(return_value=4)
        chat.image_handler=execute
        send=AsyncMock()
        client=httpx.AsyncClient
        def endpoint(request):
            body=json.loads(request.content)
            names={t['function']['name'] for t in body['tools']}
            self.assertIn('search_images',names)
            self.assertIn('web_search',names)
            return httpx.Response(200,json={'choices':[{'message':{'content':'我发五张给你！',
                'tool_calls':[{'id':'image-1','type':'function','function':{'name':'search_images',
                    'arguments':json.dumps({'keyword':'日向千夏','count':5})}}]}}]})
        with patch('plugins.qianxia_chat.httpx.AsyncClient',side_effect=lambda **kw:client(
            transport=httpx.MockTransport(endpoint),**kw)):
            await chat.reply((1,None,2),'来5张日向千夏',send)
        execute.assert_awaited_once()
        key,query=execute.call_args.args
        self.assertEqual((key,query.keyword,query.count),((1,None,2),'日向千夏',5))
        send.assert_not_awaited()
        saved=chat.history[(1,None,2)][-1]['content']
        self.assertIn('4',saved)
        self.assertNotIn('发五张',saved)

    async def test_bad_model_arguments_do_not_execute_images(self):
        for args in ({'keyword':'日向千夏','count':99},{'keyword':'日向千夏','count':True},
                     {'keyword':'','count':1},{'keyword':'日向千夏','count':'5'}):
            chat=Chat(Config())
            execute=AsyncMock();chat.image_handler=execute
            client=httpx.AsyncClient
            transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'choices':[{'message':{
                'content':None,'tool_calls':[{'id':'a','type':'function','function':{
                    'name':'search_images','arguments':json.dumps(args)}}]}}]}))
            send=AsyncMock()
            with patch('plugins.qianxia_chat.httpx.AsyncClient',side_effect=lambda **kw:client(transport=transport,**kw)):
                await chat.reply((1,None,2),'找图',send)
            execute.assert_not_awaited()
            send.assert_awaited_once()

    async def test_internal_and_proactive_paths_do_not_offer_image_tool(self):
        chat=Chat(Config());chat.image_handler=AsyncMock()
        client=httpx.AsyncClient
        def endpoint(request):
            body=json.loads(request.content)
            self.assertNotIn('search_images',str(body.get('tools',[])))
            return httpx.Response(200,json={'choices':[{'message':{'content':'普通回复'}}]})
        with patch('plugins.qianxia_chat.httpx.AsyncClient',side_effect=lambda **kw:client(
            transport=httpx.MockTransport(endpoint),**kw)):
            await chat.complete([{'role':'user','content':'只判断，不发图'}])
            await chat.reply((1,3,2),'聊聊音游',AsyncMock(),allow_web=False)
        chat.image_handler.assert_not_awaited()

    async def test_explicit_do_not_send_images_disables_execution_tool(self):
        chat=Chat(Config());chat.image_handler=AsyncMock()
        client=httpx.AsyncClient
        def endpoint(request):
            body=json.loads(request.content)
            self.assertNotIn('search_images',str(body.get('tools',[])))
            return httpx.Response(200,json={'choices':[{'message':{'content':'那就先不发图。'}}]})
        with patch('plugins.qianxia_chat.httpx.AsyncClient',side_effect=lambda **kw:client(
            transport=httpx.MockTransport(endpoint),**kw)):
            await chat.reply((1,None,2),'先不要发图，聊聊这个功能',AsyncMock())
        chat.image_handler.assert_not_awaited()

    def test_five_image_rule_commands_remain_available(self):
        from plugins.qianxia_pixiv import command_query,parse_request
        self.assertEqual(command_query('日向千夏 5').count,5)
        self.assertEqual(parse_request('来五张日向千夏的图').count,5)
        self.assertIsNone(parse_request('来5张日向千夏'))

    async def test_rule_image_request_bypasses_ai_and_preserves_followup_context(self):
        from qianxia_pixiv import ImageRequest
        chat=Chat(Config());chat.image_handler=AsyncMock(return_value=2)
        chat.image_ai_enabled=False
        send=AsyncMock()
        with patch.object(chat,'complete',side_effect=AssertionError('rule must bypass AI')):
            await chat.reply((1,None,2),'找两张角色甲的图',send,
                             allow_web=False,image_request=ImageRequest('角色甲',2))
        chat.image_handler.assert_awaited_once()
        send.assert_not_awaited()
        history=chat.history[(1,None,2)]
        self.assertIn('角色甲',history[-1]['content'])
        self.assertIn('2',history[-1]['content'])
