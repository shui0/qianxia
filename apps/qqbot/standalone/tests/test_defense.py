import unittest
from unittest.mock import patch

import bot_fixture
from test_chat import message
from plugins.qianxia_defense import (
    config, defend, implicit_context, is_candidate, matcher, parse_rebuttal,
    remember_context, target_for,
)


class DefenseTests(unittest.TestCase):
    def test_target_comes_from_onebot_segments(self):
        mention = [{"type": "at", "data": {"qq": "7"}}, {"type": "text", "data": {"text": "你就是废物"}}]
        self.assertEqual(target_for(message(group=3, segments=mention)), 7)
        self.assertIsNone(target_for(message(group=3)))
        mention[0]["data"]["qq"] = "1"
        self.assertIsNone(target_for(message(group=3, segments=mention)))

    def test_owner_threshold_and_formal_rebuttal(self):
        verdict = '{"severity":2,"rebuttal":"一次失误推不出整体水平，得看长期表现。"}'
        self.assertIsNotNone(parse_rebuttal(verdict, owner=True))
        self.assertIsNone(parse_rebuttal(verdict, owner=False))
        self.assertIsNone(parse_rebuttal('{"severity":3,"rebuttal":"请注意你的言辞"}', owner=True))
        self.assertIsNone(parse_rebuttal("invalid", owner=True))
        disagreement = '{"severity":1,"disagrees":true,"rebuttal":"第一天没有数据，还不足以判断后续不会更新。"}'
        self.assertIsNotNone(parse_rebuttal(disagreement, owner=True))
        self.assertIsNone(parse_rebuttal(disagreement, owner=False))
        self.assertIsNone(parse_rebuttal(disagreement, owner=True, implicit=True))
        confirmed = disagreement.replace('{"severity"', '{"targets_owner":true,"severity"')
        self.assertIsNotNone(parse_rebuttal(confirmed, owner=True, implicit=True))

    def test_sarcasm_reaches_classifier_only_with_identifiable_target(self):
        def addressed(text):
            return message(group=3, segments=[
                {"type": "at", "data": {"qq": "7"}},
                {"type": "text", "data": {"text": text}},
            ])
        with patch.object(config, "qianxia_defense_owner_qq", 7):
            self.assertTrue(is_candidate(addressed("我攻击你？我还没开始认真呢")))
            self.assertTrue(is_candidate(addressed("迁移半成品就敢上线，勇气可嘉啊")))
            self.assertTrue(is_candidate(addressed("这个机器人查分功能太少了")))
            self.assertFalse(is_candidate(message(group=3, segments=[
                {"type": "text", "data": {"text": "我还没开始认真呢"}},
            ])))


class DispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_unaddressed_message_requires_recent_owner_in_same_group(self):
        original = message(group=32, user=7).model_copy(update={"time": 100, "message_id": 1})
        reply = message(group=32).model_copy(update={"time": 105, "message_id": 2})
        with patch.object(config, "qianxia_defense_owner_qq", 7):
            await remember_context(original)
            await remember_context(reply)
            self.assertEqual(implicit_context(reply), [{"speaker": "保护对象", "text": "你好"}])
            self.assertEqual(implicit_context(reply.model_copy(update={"group_id": 33})), [])
            self.assertEqual(implicit_context(reply.model_copy(update={"time": 191})), [])

    async def test_quotes_and_mentions_each_distinct_message(self):
        segments = [{"type": "at", "data": {"qq": "7"}},
                    {"type": "text", "data": {"text": "你就是废物"}}]
        event = message(group=12, segments=segments)
        next_event = event.model_copy(update={"message_id": 2})
        answer = "一次失误推不出整体水平，得看长期表现。"
        with patch.object(config, "qianxia_defense_owner_qq", 7), patch(
            "plugins.qianxia_defense.chat.complete",
            return_value='{"severity":2,"rebuttal":"' + answer + '"}',
        ) as complete, patch.object(matcher, "send") as send, patch("plugins.qianxia_defense.current_matcher"):
            await defend(event)
            await defend(event)
            await defend(next_event)
        self.assertEqual(complete.await_count, 2)
        self.assertEqual(send.await_count, 2)
        sent = send.await_args_list[0].args[0]
        self.assertEqual(sent[0].type, "reply")
        self.assertEqual(sent[0].data["id"], str(event.message_id))
        self.assertEqual(sent[1].type, "at")
        self.assertEqual(sent[1].data["qq"], str(event.user_id))
        self.assertEqual(sent[2].data["text"], " " + answer)
