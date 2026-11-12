import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

import httpx
import bot_fixture


class RecentTests(unittest.TestCase):
    def test_persists_only_recent_twenty_and_separates_conversations(self):
        from qianxia_pixiv_recent import RecentImages
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'recent.sqlite3'
            store=RecentImages(path)
            key=(1,0,2)
            for number in range(25):
                store.mark(key,str(number),f'hash-{number}')
            again=RecentImages(path)
            self.assertEqual(again.ids(key),{str(i) for i in range(5,25)})
            self.assertFalse(again.has_hash(key,'hash-0'))
            self.assertTrue(again.has_hash(key,'hash-24'))
            self.assertEqual(again.ids((1,0,3)),set())
            self.assertEqual(again.ids((1,99,0)),set())


class PixivSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_randomizes_within_the_same_relevance_tier(self):
        from qianxia_pixiv import Pixiv,PixivConfig
        def endpoint(request):
            if '/ajax/search/' in request.url.path:
                return httpx.Response(200,json={'error':False,'body':{'illust':{'total':2,'data':[
                    {'id':str(i),'title':'角色甲','tags':['角色甲'],'pageCount':1,'xRestrict':0,'illustType':0}
                    for i in (21,22)
                ]}}})
            pid=request.url.path.rsplit('/',1)[1]
            return httpx.Response(200,json={'error':False,'body':{
                'illustId':pid,'illustTitle':'角色甲','tags':{'tags':[{'tag':'角色甲'}]},
                'pageCount':1,'xRestrict':0,'illustType':0,'userName':'Artist',
                'urls':{'regular':f'https://i.pximg.net/{pid}.jpg'},
            }})
        client=httpx.AsyncClient
        with patch('qianxia_pixiv.random.shuffle',side_effect=lambda values:values.reverse()) as shuffle, \
             patch('qianxia_pixiv.httpx.AsyncClient',side_effect=lambda **kw:client(
                 transport=httpx.MockTransport(endpoint),**kw)):
            result=await Pixiv(PixivConfig()).search('角色甲')
        shuffle.assert_called_once()
        self.assertEqual(result[0].id,'22')

    async def test_excludes_recent_before_selection_and_looks_on_next_page(self):
        from qianxia_pixiv import Pixiv,PixivConfig
        pages=[]
        def endpoint(request):
            if '/ajax/search/' in request.url.path:
                page=int(request.url.params['p']);pages.append(page)
                pid='21' if page==1 else '22'
                return httpx.Response(200,json={'error':False,'body':{'illust':{'total':61,'data':[
                    {'id':pid,'title':'角色甲','tags':['角色甲'],'pageCount':1,'xRestrict':0,'illustType':0},
                ]}}})
            self.assertTrue(request.url.path.endswith('/22'))
            return httpx.Response(200,json={'error':False,'body':{
                'illustId':'22','illustTitle':'角色甲','tags':{'tags':[{'tag':'角色甲'}]},
                'pageCount':1,'xRestrict':0,'illustType':0,'userName':'Artist',
                'urls':{'regular':'https://i.pximg.net/22.jpg'},
            }})
        client=httpx.AsyncClient
        with patch('qianxia_pixiv.httpx.AsyncClient',side_effect=lambda **kw:client(
            transport=httpx.MockTransport(endpoint),**kw)):
            result=await Pixiv(PixivConfig()).search('角色甲',1,exclude_ids={'21'})
        self.assertEqual([w.id for w in result],['22'])
        self.assertEqual(pages,[1,2])


class PixivDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_identical_image_file_under_a_new_work_id_is_skipped(self):
        import hashlib
        from qianxia_pixiv import Artwork
        from qianxia_pixiv_recent import RecentImages
        import plugins.qianxia_pixiv as plugin
        with TemporaryDirectory() as tmp:
            store=RecentImages(Path(tmp)/'recent.sqlite3')
            store.mark((1,0,2),'21',hashlib.sha256(b'same image').hexdigest())
            works=[Artwork(str(i),'Star','Artist',f'https://i.pximg.net/{i}.jpg') for i in (22,23)]
            async def search(keyword,count,*,exclude_ids):
                return [w for w in works if w.id not in exclude_ids][:count]
            send=AsyncMock()
            with patch.object(plugin,'recent',store),patch.object(plugin.pixiv,'search',side_effect=search), \
                 patch.object(plugin.pixiv,'image',side_effect=lambda url:b'same image' if '/22.' in url else b'new image'):
                await plugin.reply_images(plugin.Query('星空'),send,key=(1,0,2))
            self.assertEqual(send.await_count,1)
            self.assertIn('/artworks/23',send.call_args.args[0].extract_plain_text())
            self.assertEqual(store.ids((1,0,2)),{'21','23'})

    def test_group_shares_recent_images_while_private_chats_are_independent(self):
        from plugins.qianxia_pixiv import image_scope
        from test_chat import message
        self.assertEqual(image_scope(message(group=3,user=2)),image_scope(message(group=3,user=4)))
        self.assertNotEqual(image_scope(message(user=2)),image_scope(message(user=4)))

    async def test_concurrent_requests_do_not_send_same_work_and_survive_reopen(self):
        from qianxia_pixiv import Artwork
        from qianxia_pixiv_recent import RecentImages
        import plugins.qianxia_pixiv as plugin
        with TemporaryDirectory() as tmp:
            store=RecentImages(Path(tmp)/'recent.sqlite3')
            works=[Artwork(str(i),'Star','Artist',f'https://i.pximg.net/{i}.jpg') for i in (21,22)]
            async def search(keyword,count,*,exclude_ids):
                await asyncio.sleep(0)
                return [w for w in works if w.id not in exclude_ids][:count]
            sent=[]
            async def send(message):
                await asyncio.sleep(0)
                sent.append(message.extract_plain_text())
            with patch.object(plugin,'recent',store),patch.object(plugin.pixiv,'search',side_effect=search), \
                 patch.object(plugin.pixiv,'image',side_effect=lambda url:url.encode()):
                await asyncio.gather(*(plugin.reply_images(plugin.Query('星空'),send,key=(1,0,2)) for _ in range(2)))
            self.assertEqual(len(sent),2)
            self.assertNotEqual(sent[0],sent[1])
            self.assertEqual(RecentImages(store.path).ids((1,0,2)),{'21','22'})

    async def test_failed_send_or_link_only_does_not_mark_image_sent(self):
        from qianxia_pixiv import Artwork,PixivError
        from qianxia_pixiv_recent import RecentImages
        import plugins.qianxia_pixiv as plugin
        with TemporaryDirectory() as tmp:
            store=RecentImages(Path(tmp)/'recent.sqlite3')
            work=Artwork('21','Star','Artist','https://i.pximg.net/21.jpg')
            with patch.object(plugin,'recent',store),patch.object(plugin.pixiv,'search',return_value=[work]), \
                 patch.object(plugin.pixiv,'image',return_value=b'image'):
                with self.assertRaises(RuntimeError):
                    await plugin.reply_images(plugin.Query('星空'),AsyncMock(side_effect=RuntimeError('send failed')),key=(1,0,2))
            self.assertEqual(store.ids((1,0,2)),set())
            with patch.object(plugin,'recent',store),patch.object(plugin.pixiv,'search',return_value=[work]), \
                 patch.object(plugin.pixiv,'image',side_effect=PixivError('download failed')):
                await plugin.reply_images(plugin.Query('星空'),AsyncMock(),key=(1,0,2))
            self.assertEqual(store.ids((1,0,2)),set())
