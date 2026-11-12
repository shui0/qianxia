import unittest

import bot_fixture
from plugins.qianxia_bili import CommentDrafts, read_args


class BiliTests(unittest.TestCase):
    def test_reads_are_validated(self):
        self.assertEqual(read_args("搜索", "音击"), ["search", "--", "音击"])
        self.assertEqual(read_args("详情", "https://www.bilibili.com/video/BV1xx411c7mD"),
                         ["info", "BV1xx411c7mD"])
        with self.assertRaises(ValueError):
            read_args("评论", "not-a-video")

    def test_confirmation_is_scoped_expires_and_is_single_use(self):
        drafts = CommentDrafts()
        owner = (1, 2)
        code = drafts.prepare(owner, "BV1xx411c7mD", "预演", now=10)
        self.assertIsNone(drafts.consume((1, 3), code, now=11))
        self.assertEqual(drafts.consume(owner, code, now=11), ("BV1xx411c7mD", "预演"))
        self.assertIsNone(drafts.consume(owner, code, now=11))
        code = drafts.prepare(owner, "BV1xx411c7mD", "过期", now=10)
        self.assertIsNone(drafts.consume(owner, code, now=131))
