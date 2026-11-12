import json
import asyncio
from io import BytesIO
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from PIL import Image
import bot_fixture


class PixivTests(unittest.IsolatedAsyncioTestCase):
    async def test_character_search_rejects_collections_and_prefers_explicit_title(self):
        from qianxia_pixiv import Pixiv,PixivConfig
        calls=[]
        def endpoint(request):
            calls.append(request)
            if '/ajax/search/' in request.url.path:
                self.assertEqual(request.url.params['s_mode'],'s_tag_full')
                return httpx.Response(200,json={'error':False,'body':{'illust':{'data':[
                    {'id':'21','title':'多人合集','tags':['角色甲','角色乙'],'xRestrict':0,'illustType':0,'pageCount':7},
                    {'id':'22','title':'夏日','tags':['角色甲'],'xRestrict':0,'illustType':0,'pageCount':1},
                    {'id':'23','title':'角色甲的生日','tags':['角色甲'],'xRestrict':0,'illustType':0,'pageCount':1},
                ]}}})
            pid=request.url.path.rsplit('/',1)[1]
            return httpx.Response(200,json={'error':False,'body':{
                'illustId':pid,'illustTitle':'角色甲的生日','userName':'Artist','xRestrict':0,'illustType':0,
                'pageCount':1,'tags':{'tags':[{'tag':'角色甲'}]},
                'urls':{'regular':f'https://i.pximg.net/{pid}.jpg'},
            }})
        client=httpx.AsyncClient
        with patch('qianxia_pixiv.httpx.AsyncClient',side_effect=lambda **kw:client(
            transport=httpx.MockTransport(endpoint),**kw)):
            result=await Pixiv(PixivConfig()).search('角色甲',1)
        self.assertEqual([r.id for r in result],['23'])
        self.assertEqual(len(calls),2)

    async def test_detail_tag_mismatch_or_multiple_pages_is_not_sent(self):
        from qianxia_pixiv import Pixiv,PixivConfig
        client=httpx.AsyncClient
        for pages,tags in [(7,['角色甲']),(1,['角色乙']),(None,['角色甲'])]:
            def endpoint(request):
                if '/ajax/search/' in request.url.path:
                    return httpx.Response(200,json={'error':False,'body':{'illust':{'data':[
                        {'id':'23','title':'角色甲','tags':['角色甲'],'xRestrict':0,'illustType':0,'pageCount':1},
                    ]}}})
                return httpx.Response(200,json={'error':False,'body':{'illustId':'23','illustTitle':'角色甲',
                    'userName':'Artist','xRestrict':0,'illustType':0,'pageCount':pages,
                    'tags':{'tags':[{'tag':tag} for tag in tags]},
                    'urls':{'regular':'https://i.pximg.net/23.jpg'}}})
            with patch('qianxia_pixiv.httpx.AsyncClient',side_effect=lambda **kw:client(
                transport=httpx.MockTransport(endpoint),**kw)):
                self.assertEqual(await Pixiv(PixivConfig()).search('角色甲',1),[])

    async def test_corrupt_png_is_normalized_to_a_preview_failure(self):
        from qianxia_pixiv import Pixiv,PixivConfig,PixivError
        buffer=BytesIO()
        Image.new('RGB',(2,2),'blue').save(buffer,format='PNG')
        data=bytearray(buffer.getvalue())
        index=data.index(b'IDAT')
        size=int.from_bytes(data[index-4:index],'big')
        data[index+4+size]^=1
        client=httpx.AsyncClient
        with patch('qianxia_pixiv.httpx.AsyncClient',side_effect=lambda **kw:client(
            transport=httpx.MockTransport(lambda _:httpx.Response(200,headers={'Content-Type':'image/png'},content=bytes(data))),**kw)):
            with self.assertRaises(PixivError):
                await Pixiv(PixivConfig()).image('https://i.pximg.net/a.png')

    async def test_slow_stream_has_an_overall_download_deadline(self):
        from qianxia_pixiv import Pixiv,PixivConfig,PixivError
        class SlowStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                await asyncio.Event().wait()
                yield b''
        client=httpx.AsyncClient
        with patch('qianxia_pixiv.IMAGE_TIMEOUT',0.03),patch('qianxia_pixiv.httpx.AsyncClient',side_effect=lambda **kw:client(
            transport=httpx.MockTransport(lambda _:httpx.Response(200,headers={'Content-Type':'image/png'},stream=SlowStream())),**kw)):
            with self.assertRaises(PixivError):
                await asyncio.wait_for(Pixiv(PixivConfig()).image('https://i.pximg.net/a.png'),0.5)

    async def test_search_uses_safe_mode_and_details_before_image_download(self):
        from qianxia_pixiv import Pixiv, PixivConfig
        calls = []
        def endpoint(request):
            calls.append(request)
            if '/ajax/search/' in request.url.path:
                self.assertEqual(request.url.params['mode'], 'safe')
                return httpx.Response(200, json={'error':False,'body':{'illust':{'data':[
                    {'id':'11','title':'unsafe','xRestrict':1,'illustType':0},
                    {'id':'12','title':'unknown','illustType':0},
                    {'id':'13','title':'Star','userName':'Artist','xRestrict':0,'illustType':0,'pageCount':1,'tags':['星空']},
                ]}}})
            self.assertTrue(request.url.path.endswith('/13'))
            return httpx.Response(200,json={'error':False,'body':{
                'illustId':'13','illustTitle':'Star','userName':'Artist','xRestrict':0,'illustType':0,
                'pageCount':1,'tags':{'tags':[{'tag':'星空'}]},
                'urls':{'regular':'https://i.pximg.net/img-master/13_p0.jpg'},
            }})
        client = httpx.AsyncClient
        with patch('qianxia_pixiv.httpx.AsyncClient', side_effect=lambda **kw: client(
            transport=httpx.MockTransport(endpoint), **kw)):
            result=await Pixiv(PixivConfig()).search('星空',1)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].title,'Star')
        self.assertEqual(result[0].url,'https://www.pixiv.net/artworks/13')
        self.assertEqual(len(calls),2)

    async def test_unknown_or_restricted_details_are_not_returned(self):
        from qianxia_pixiv import Pixiv, PixivConfig
        client = httpx.AsyncClient
        def endpoint(request):
            if '/ajax/search/' in request.url.path:
                return httpx.Response(200,json={'error':False,'body':{'illust':{'data':[
                    {'id':'13','xRestrict':0,'illustType':0,'pageCount':1,'tags':['星空']},
                ]}}})
            return httpx.Response(200,json={'error':False,'body':{'illustId':'13','illustTitle':'Star',
                'userName':'Artist','xRestrict':1,'urls':{'regular':'https://i.pximg.net/a.jpg'}}})
        with patch('qianxia_pixiv.httpx.AsyncClient', side_effect=lambda **kw: client(
            transport=httpx.MockTransport(endpoint), **kw)):
            self.assertEqual(await Pixiv(PixivConfig()).search('星空',1),[])

    async def test_image_download_never_follows_untrusted_url_or_redirect(self):
        from qianxia_pixiv import Pixiv, PixivConfig, PixivError
        service=Pixiv(PixivConfig())
        for url in ('http://127.0.0.1/a.jpg','https://i.pximg.net.evil.example/a.jpg',
                    'https://i.pximg.net@evil.example/a.jpg'):
            with self.assertRaises(PixivError):
                await service.image(url)

    async def test_redirects_and_oversized_image_headers_are_rejected(self):
        from qianxia_pixiv import Pixiv, PixivConfig, PixivError
        client=httpx.AsyncClient
        for response in [httpx.Response(302,headers={'Location':'http://127.0.0.1/secret'}),
                         httpx.Response(200,headers={'Content-Type':'image/png','Content-Length':str(9*1024*1024)})]:
            calls=[]
            def endpoint(request):
                calls.append(request)
                return response
            with patch('qianxia_pixiv.httpx.AsyncClient',side_effect=lambda **kw:client(
                transport=httpx.MockTransport(endpoint),**kw)):
                with self.assertRaises(PixivError):
                    await Pixiv(PixivConfig()).image('https://i.pximg.net/a.jpg')
            self.assertEqual(len(calls),1)

    async def test_reply_contains_image_artist_and_real_work_link(self):
        from qianxia_pixiv import Artwork
        from plugins.qianxia_pixiv import Query, pixiv, reply_images
        send=AsyncMock()
        work=Artwork('13','Star','Artist','https://i.pximg.net/a.jpg')
        with patch.object(pixiv,'search',return_value=[work]),patch.object(pixiv,'image',return_value=b'test image'):
            await reply_images(Query('星空'),send,key=(1,0,2))
        reply=send.call_args.args[0]
        self.assertTrue(any(segment.type=='image' and segment.data['file'].startswith('base64://') for segment in reply))
        for text in ('Star','Artist','https://www.pixiv.net/artworks/13'):
            self.assertIn(text,reply.extract_plain_text())


class PixivIntentTests(unittest.TestCase):
    def test_group_requires_mention_and_private_message_can_search_directly(self):
        from test_chat import message
        from plugins.qianxia_pixiv import wants_image
        text={'type':'text','data':{'text':'找张星空的图'}}
        self.assertTrue(wants_image(message(segments=[text])))
        self.assertFalse(wants_image(message(group=3,segments=[text])))
        self.assertTrue(wants_image(message(group=3,segments=[{'type':'at','data':{'qq':'1'}},text])))

    def test_natural_intents_do_not_intercept_plain_discussion(self):
        from plugins.qianxia_pixiv import parse_request
        for text, keyword, count in [('找张星空的图','星空',1),('帮我找三张日向千夏的插画','日向千夏',3),
                                     ('来一张星空壁纸','星空',1),('搜图 日向千夏','日向千夏',1)]:
            query=parse_request(text)
            self.assertEqual((query.keyword,query.count),(keyword,count))
        for text in ('你知道这张图是谁画的吗','舞萌15难度有哪些谱面','这张图好看','/舞萌 搜曲 星空'):
            self.assertIsNone(parse_request(text))
