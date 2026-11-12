import unittest
from unittest.mock import patch
import bot_fixture
from plugins.qianxia_chat import Config, conversation_key, proactive_allowed, proactive_trigger
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent


def message(group=None, user=2, segments=None):
    data = dict(time=1, self_id=1, post_type="message", sub_type="normal",
                message_id=1, user_id=user, raw_message="", font=0,
                message=segments or [{"type": "text", "data": {"text": "你好"}}],
                sender={"user_id": user})
    if group is None:
        return PrivateMessageEvent(message_type="private", **data)
    return GroupMessageEvent(message_type="group", group_id=group, **data)


class RoutingTests(unittest.TestCase):
    def test_private_and_self(self):
        self.assertEqual(conversation_key(message(), set()), (1, None, 2))
        self.assertIsNone(conversation_key(message(user=1), set()))

    def test_group_requires_explicit_mention_and_respects_allowlist(self):
        mention = [{"type": "at", "data": {"qq": "1"}},
                   {"type": "text", "data": {"text": "你好"}}]
        self.assertIsNone(conversation_key(message(group=3), set()))
        self.assertIsNone(conversation_key(message(group=3, segments=mention), {4}))
        self.assertEqual(conversation_key(message(group=3, segments=mention), {3}), (1, 3, 2))

    def test_proactive_replies_default_to_allowed_groups(self):
        event = message(group=3)
        self.assertTrue(proactive_allowed(event, "你好", Config()))
        self.assertFalse(proactive_allowed(event, "你好", Config(qianxia_proactive_enabled=False)))
        self.assertFalse(proactive_allowed(event, "你好", Config(qianxia_groups={4})))
        self.assertFalse(proactive_allowed(event, "你好", Config(qianxia_proactive_groups={4})))
        config = Config(qianxia_proactive_groups={3}, qianxia_groups={3})
        self.assertTrue(proactive_allowed(event, "你好", config))
        self.assertFalse(proactive_allowed(event, "/菜单", config))
        self.assertFalse(proactive_allowed(message(group=3, user=1), "你好", config))

    def test_interests_trigger_even_when_random_is_disabled(self):
        config = Config(qianxia_proactive_probability=0)
        self.assertTrue(proactive_trigger("今天去打舞萌吗", config))
        self.assertFalse(proactive_trigger("今天吃什么", config))

    def test_random_and_custom_interests(self):
        config = Config(qianxia_proactive_keywords=["  ONGEKI  ", " "],
                        qianxia_proactive_probability=.05)
        with patch("plugins.qianxia_chat.random.random", return_value=.8):
            self.assertTrue(proactive_trigger("聊聊ongeki", config))
            self.assertFalse(proactive_trigger("今天吃什么", config))
        with patch("plugins.qianxia_chat.random.random", return_value=.01):
            self.assertTrue(proactive_trigger("今天吃什么", config))



class ChatHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_requests_bypass_proxy_only_on_loopback(self):
        import httpx
        from plugins.qianxia_chat import Chat

        client = httpx.AsyncClient
        transport = httpx.MockTransport(lambda _: httpx.Response(200, json={
            "choices": [{"message": {"content": "早安"}}],
        }))
        for url, expected in (
            ("http://127.0.0.1:11434/v1", False),
            ("http://localhost:11434/v1", False),
            ("http://[::1]:11434/v1", False),
            ("https://model.example/v1", True),
        ):
            chat = Chat(Config(qianxia_model_base_url=url))
            with patch.object(httpx, "AsyncClient", side_effect=lambda **kwargs: client(
                transport=transport, **kwargs
            )) as factory:
                self.assertEqual(await chat.complete([{"role": "user", "content": "早安"}]), "早安")
                self.assertEqual(factory.call_args.kwargs.get("trust_env"), expected)

    async def test_unsent_reply_is_not_saved(self):
        from unittest.mock import AsyncMock, patch
        from plugins.qianxia_chat import Chat, Config

        chat = Chat(Config())
        send = AsyncMock(side_effect=RuntimeError("OneBot disconnected"))
        with patch.object(chat, "complete", return_value="回复"):
            with self.assertRaises(RuntimeError):
                await chat.reply((1, None, 2), "你好", send)
        self.assertEqual(list(chat.history), [])


class WebSocketTests(unittest.TestCase):
    def test_model_failure_context_and_reconnect(self):
        from fastapi.testclient import TestClient
        import httpx
        import json
        import nonebot
        from unittest.mock import patch
        from plugins.qianxia_chat import chat

        requests = []
        real_client = httpx.AsyncClient

        def fake_model(request):
            body = json.loads(request.content)
            requests.append(body)
            text = body["messages"][-1]["content"]
            if text == "fail":
                return httpx.Response(503)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": f"回复 {text}"}}]
            })

        def send_event(socket, text, *, group=None, user=2, mention=False):
            segments = [{"type": "text", "data": {"text": text}}]
            if mention:
                segments.insert(0, {"type": "at", "data": {"qq": "1"}})
            socket.send_json(message(group, user, segments).model_dump(mode="json"))

        def receive_reply(socket):
            response = socket.receive_json()
            self.assertEqual(response["action"], "send_msg")
            socket.send_json({"status": "ok", "retcode": 0, "data": {"message_id": 7},
                              "echo": response["echo"]})
            return response["params"]["message"]

        def expect_reply(socket, text):
            self.assertEqual(receive_reply(socket), [{"type": "text", "data": {"text": text}}])

        path = "/onebot/v11/ws"
        headers = {"x-self-id": "1", "authorization": "Bearer test-only-token"}
        with patch.object(httpx, "AsyncClient", side_effect=lambda **kwargs: real_client(
            transport=httpx.MockTransport(fake_model), **kwargs
        )), TestClient(nonebot.get_app()) as client:
            with client.websocket_connect(path, headers=headers) as socket:
                send_event(socket, "first")
                expect_reply(socket, "回复 first")
                send_event(socket, "fail")
                expect_reply(socket, "刚才没连上，过会儿再叫千夏试试吧。")
            with client.websocket_connect(path, headers=headers) as socket:
                send_event(socket, "unmentioned", group=3)
                send_event(socket, "self", user=1)
                send_event(socket, "/unknown")
                send_event(socket, "next")
                expect_reply(socket, "回复 next")
                send_event(socket, "group", group=3, mention=True)
                expect_reply(socket, "回复 group")
                send_event(socket, "/舞萌 评分 13.8 100.5")
                self.assertIn("309", receive_reply(socket)[0]["data"]["text"])
                send_event(socket, "/B站 发评论 BV1xx411c7mD 预演", group=3)
                expect_reply(socket, "发评论这件事得让已经配置好的操作者私聊找我哦。")
                send_event(socket, "", group=3, mention=True)
                self.assertIn("/骰子", receive_reply(socket)[0]["data"]["text"])
                for phrase in ("帮助", "Help!", "你有什么功能？", "你能做什么呀", "怎么用"):
                    send_event(socket, phrase, group=3, mention=True)
                    help_text = receive_reply(socket)[0]["data"]["text"]
                    for example in ("/舞萌 B50", "/舞萌 推分", "/语音", "/B站 详情", "/猜数字", "/周报"):
                        self.assertIn(example, help_text)
                send_event(socket, "/日记 查看")
                expect_reply(socket, "千夏还没写过日记。")
                send_event(socket, "/周报", group=3)
                expect_reply(socket, "这个群的聊天我还没开始记，暂时整理不了周报哦。")
                send_event(socket, "/日记 写", group=3)
                expect_reply(socket, "这个群的聊天我还没开始记，暂时写不了群日记哦。")
                send_event(socket, "/骰子 d6")
                self.assertIn("合计", receive_reply(socket)[0]["data"]["text"])
                with patch("plugins.qianxia_voice.synthesize", return_value=b"test audio"):
                    send_event(socket, "/语音 你好")
                    record, = receive_reply(socket)
                    self.assertEqual(record["type"], "record")
                    self.assertEqual(record["data"]["file"], "base64://dGVzdCBhdWRpbw==")
                from plugins.qianxia_defense import config as defense_config
                rebuttal = "一次失误不能说明整体水平。"
                verdict = json.dumps({"severity": 2, "rebuttal": rebuttal})
                with patch.object(defense_config, "qianxia_defense_owner_qq", 7), patch(
                    "plugins.qianxia_defense.chat.complete", return_value=verdict
                ):
                    socket.send_json(message(group=3, segments=[
                        {"type": "at", "data": {"qq": "7"}},
                        {"type": "text", "data": {"text": "你就是废物"}},
                    ]).model_dump(mode="json"))
                    quoted, mention, reply = receive_reply(socket)
                    self.assertEqual(quoted["type"], "reply")
                    self.assertEqual(mention["type"], "at")
                    self.assertEqual(mention["data"]["qq"], "2")
                    self.assertEqual(reply["data"]["text"], " " + rebuttal)
                implicit_verdict = json.dumps({"severity": 1, "disagrees": True,
                                               "targets_owner": True, "rebuttal": rebuttal})
                with patch.object(defense_config, "qianxia_defense_owner_qq", 7), patch(
                    "plugins.qianxia_defense.chat.complete", return_value=implicit_verdict
                ):
                    owner_event = message(group=39, user=7).model_copy(update={"message_id": 11})
                    dissent = message(group=39).model_copy(update={"message_id": 12})
                    socket.send_json(owner_event.model_dump(mode="json"))
                    socket.send_json(dissent.model_dump(mode="json"))
                    quoted, mention, reply = receive_reply(socket)
                    self.assertEqual(quoted["data"]["id"], "12")
                    self.assertEqual(mention["data"]["qq"], "2")
                    self.assertEqual(reply["data"]["text"], " " + rebuttal)

        self.assertEqual([body["messages"][-1]["content"] for body in requests],
                         ["first", "fail", "next", "group"])
        self.assertEqual([turn["content"] for turn in requests[2]["messages"][1:]],
                         ["first", "回复 first", "next"])
        self.assertEqual(len(requests[3]["messages"]), 2)
        self.assertEqual(set(chat.history), {(1, None, 2), (1, 3, 2)})
