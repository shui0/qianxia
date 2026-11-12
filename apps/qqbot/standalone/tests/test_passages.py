import unittest

from qianxia_passages import passages


class PassageTests(unittest.TestCase):
    def test_short_table_rows_inherit_their_heading_and_header_context(self):
        body = ('# Bluetooth mechanical keyboard products\nUpdated 2026-11-11\n'
                '| Name | Connection |\n| --- | --- |\n| Aster | Bluetooth |\n| Birch | Bluetooth |')
        text = passages('Bluetooth mechanical keyboard products', body, 600)
        self.assertIn('Aster', text)
        self.assertIn('Birch', text)

    def test_matching_record_does_not_inherit_unlabelled_counters(self):
        body = '# Performance\nReport\n978\nAster\nType A\nRuntime 15 hours\n3.8 · 3 人\n94\nCedar\nRuntime 15 hours'
        excerpt = passages('Runtime 15 hours', body, 600)
        self.assertIn('Aster', excerpt)
        self.assertIn('Cedar', excerpt)
        self.assertNotIn('978', excerpt)
        self.assertNotIn('3.8', excerpt)

    def test_irrelevant_navigation_is_not_added_just_to_fill_budget(self):
        body = ('# 产品性能\n版本信息\n\n查询全部产品评分、续航分布和玩家评价。\n'
                'Aster\nType A\n续航 15 小时\n查看导航页\n'
                'Birch\nType B\n续航 9 小时\n点击查看更多\n'
                'Cedar\nType A\n续航 15 小时\n访问导航菜单\n')
        excerpt = passages('产品15小时有哪些', body, 900)
        self.assertIn('Aster', excerpt)
        self.assertIn('Cedar', excerpt)
        self.assertNotIn('访问导航菜单', excerpt)
        self.assertNotIn('查看导航页', excerpt)

    def test_long_previous_line_cannot_displace_matching_sentence(self):
        body = '# Report\nSummary\n' + 'General background. ' * 300 + '\nAster endurance is 15 hours.'
        self.assertIn('Aster endurance is 15 hours', passages('Aster endurance 15 hours', body, 600))

    def test_query_year_does_not_filter_out_relevant_records(self):
        body = ('# Test report\nPublished 2026-11-11\n' + 'General background.\n' * 5
                + '## endurance ranking\nAster products endurance 20 hours, ranked first.\n'
                + 'Birch products endurance 18 hours, ranked second.')
        excerpt = passages('2026 products endurance', body, 600)
        self.assertIn('Aster', excerpt)
        self.assertIn('Birch', excerpt)

    def test_numeric_tokens_do_not_confuse_distinct_decimal_values(self):
        body = '# Report\nSummary\n' + ''.join(
            f'Product {i} endurance 15.2 hours.\n' for i in range(60)) + 'Aster endurance 15 hours.'
        self.assertIn('Aster', passages('endurance 15 hours products', body, 600))

    def test_finds_evidence_after_long_intro_without_subject_specific_rules(self):
        body = ('欢迎访问。这里介绍页面操作和导航。\n\n' * 120
                + '## 2026年电池测试\n\n型号 Aster 的续航为 15 小时，重量 950 克。\n\n'
                + '型号 Birch 的续航为 9 小时。')
        excerpt = passages('续航15小时的型号是什么', body, 600)
        self.assertIn('Aster', excerpt)
        self.assertIn('15 小时', excerpt)
        self.assertLessEqual(len(excerpt), 600)

    def test_keeps_table_headers_and_matching_rows(self):
        body = '# 产品表\n\n| 名称 | 续航 | 重量 |\n| --- | --- | --- |\n' + ''.join(
            f'| 产品{i} | {15 if i in (21, 38) else 9} 小时 | 1kg |\n' for i in range(50))
        excerpt = passages('哪些产品续航15小时', body, 650)
        self.assertIn('| 名称 | 续航 | 重量 |', excerpt)
        self.assertIn('产品21', excerpt)
        self.assertIn('产品38', excerpt)
        self.assertLessEqual(len(excerpt), 650)

    def test_preserves_bullet_record_context_and_multiple_matches(self):
        body = '\n'.join(['# 统计数据', '数据截至 2026-11-11；仅统计测试区。'] + [
            f'- Record{i} | Stage B | {15 if i in (2, 19, 31) else 2015} | special'
            for i in range(40)])
        excerpt = passages('Stage B 15', body, 800)
        for number in (2, 19, 31):
            self.assertIn(f'Record{number} |', excerpt)
        self.assertIn('仅统计测试区', excerpt)

    def test_empty_shells_do_not_count_as_readable_evidence(self):
        for body in ('', 'Loading...', '<script>secret()</script>',
                     '| {{ item.title }} | {{ item.level }} |'):
            self.assertEqual(passages('产品', body, 500), '')

    def test_no_match_still_obeys_budget(self):
        excerpt = passages('unrelated topic', 'An article about something else.\n\n' * 100, 300)
        self.assertLessEqual(len(excerpt), 300)
