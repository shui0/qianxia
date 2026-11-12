import unittest

from qianxia_persona import valid_rephrase, short_fallback


class PersonaTests(unittest.TestCase):
    def test_chinese_names_and_original_values_cannot_disappear(self):
        original = '1. 产品甲 续航15小时 [1]\n2. 产品乙 续航9小时 [1]'
        self.assertFalse(valid_rephrase(original, '我找到啦。[1]'))
        self.assertFalse(valid_rephrase(original, '产品甲和产品乙都有呢。[1]'))
        self.assertFalse(valid_rephrase(original, '续航15小时和9小时。[1]'))

    def test_indented_values_remain_attached_to_listed_names(self):
        original = '根据资料：\n1. 产品甲\n   续航15小时 [1]\n2. 产品乙\n   续航9小时 [1]\n\n注：仅测试区。'
        text = short_fallback(original)
        self.assertIn('产品甲 续航15小时 [1]', text)
        self.assertIn('产品乙 续航9小时 [1]', text)

    def test_voice_change_preserves_listed_names_and_numbers(self):
        original = '根据资料可确认：\n1. Aster 续航15小时 [1]\n2. Birch 续航9小时 [1]'
        self.assertTrue(valid_rephrase(original, '我给你找来啦：Aster 续航15小时，Birch 续航9小时。[1]'))
        self.assertFalse(valid_rephrase(original, 'Aster 续航15小时。[1]'))
        self.assertFalse(valid_rephrase(original, 'Aster 续航18小时，Birch 续航9小时。[1]'))
        self.assertFalse(valid_rephrase(original, 'Aster 续航15小时，Birch 续航9小时，还有 Cedar。[1]'))

    def test_excluded_names_in_notes_cannot_be_added_back_to_the_answer(self):
        original = '1. Aster 15小时 [1]\n2. Birch 9小时 [1]\n\n注：Cedar 是概念产品，不列入。'
        self.assertFalse(valid_rephrase(original, 'Aster 15小时，Birch 9小时，另外还有 Cedar。[1]'))

    def test_fallback_keeps_facts_and_discards_report_disclaimers(self):
        original = '根据资料，无法列出全部。\n1. Aster 15小时 [1]\n2. Birch 9小时 [1]\n\n注：资料不完整。'
        text = short_fallback(original)
        self.assertIn('Aster 15小时 [1]', text)
        self.assertIn('Birch 9小时 [1]', text)
        self.assertNotIn('资料不完整', text)
        self.assertNotIn('无法列出', text)
