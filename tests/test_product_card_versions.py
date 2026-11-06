import base64
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import service
import cards


class ProductCardVersionTests(unittest.TestCase):
    def test_product_cards_render_with_their_images_prices_and_reasons(self):
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/aXsAAAAASUVORK5CYII=')
        thumbnail = 'data:image/png;base64,' + base64.b64encode(png).decode('ascii')
        for version in ('v2', 'v4'):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                documents = []
                sections = []
                for rank in range(1, 4):
                    title = '测试保湿面膜%d' % rank
                    sections.append('### %d. %s\n\n**商品分析**：分析%d\n**推荐理由**：理由%d' % (rank, title, rank, rank))
                    documents.append({
                        'kind': 'filtalgo.shopping.block:filtmall.product-card/' + version,
                        'value': {'block': {
                            'schema': 'filtmall.product-card/' + version,
                            'payload': {'rank': rank, 'recommendation_reason': '', 'product': {
                                'title': title, 'rank': rank, 'goods_id': 'goods-%d' % rank,
                                'sku_id': 'sku-%d' % rank, 'price_amount': str(rank * 10),
                                'spec_summary': '%d片/盒' % rank, 'thumbnail': thumbnail,
                            }},
                        }},
                    })
                    if version == 'v4':
                        documents[-1]['value']['block']['payload']['analysis_evidence'] = {
                            'schema': 'filtmall.cited-facts-inline/v2',
                            'payload': {
                                'segments': [
                                    {'text': '普通说明。', 'citation_ids': []},
                                    {'text': '引用分析%d。' % rank, 'citation_ids': ['ref-%d' % rank]},
                                ],
                                'references': [{
                                    'citation_id': 'ref-%d' % rank, 'number': rank,
                                    'goods_id': 'goods-%d' % rank, 'sku_id': 'sku-%d' % rank,
                                    'title': '测试来源%d' % rank, 'publisher': '测试发布者',
                                    'public_snippet': '测试资料摘要%d' % rank,
                                }],
                            },
                        }
                answer = '\n\n'.join(sections)
                payload = service.render({'answer': {'value': {'content': answer}}, 'context_documents': documents}, 'widget', 3)
                self.assertEqual(payload['card_count'], 3)
                if version == 'v4':
                    self.assertEqual(payload['widget_cards'][0]['analysis_evidence'], documents[0]['value']['block']['payload']['analysis_evidence'])
                    for renderer in (lambda items: cards.render_markdown(items, {}),
                                     lambda items: cards.render_text(items, {}, False, 80)):
                        output = renderer(payload['widget_cards'])
                        self.assertIn('引用分析1。[1]', output)
                        self.assertIn('测试来源1', output)
                service.write_outputs(payload, {'conversation': 'version-test'}, directory)
                fragment = Path(payload['fragment_file']).read_text(encoding='utf8')
                self.assertIn(fragment, Path(payload['page_file']).read_text(encoding='utf8'))
                self.assertEqual(Path(payload['answer_file']).read_text(encoding='utf8'), answer)
                self.assertEqual(fragment.count('<img '), 3)
                for rank in range(1, 4):
                    self.assertIn('测试保湿面膜%d' % rank, fragment)
                    self.assertIn('¥%d' % (rank * 10), fragment)
                    self.assertIn('理由%d' % rank, fragment)
                    self.assertIn('goodsId=goods-%d' % rank, fragment)
                    if version == 'v4':
                        self.assertIn('引用分析%d。[%d]' % (rank, rank), fragment)
                        self.assertIn('测试来源%d' % rank, fragment)
                        self.assertIn('测试资料摘要%d' % rank, fragment)
                if version == 'v4':
                    self.assertEqual(fragment.count('<details'), 3)
                    self.assertEqual(len(payload.get('product_links', [])), 3)
                    self.assertNotIn('<a href=', fragment.split('<details')[0])

    def test_v1_product_card_is_no_longer_supported(self):
        result = {'context_documents': [{
            'kind': 'filtalgo.shopping.block:filtmall.product-card/v1',
            'value': {'block': {'schema': 'filtmall.product-card/v1', 'payload': {
                'product': {'title': '旧版商品', 'goods_id': 'old', 'sku_id': 'old'},
            }}},
        }]}
        self.assertEqual(service.render(result, 'json', 0)['card_count'], 0)

    def test_v4_references_for_another_sku_are_not_displayed(self):
        card = {'title': '当前商品', 'rank': 1, 'goods_id': 'g', 'sku_id': 's',
                'url': 'https://example.test/product', 'overview': '普通分析',
                'analysis_evidence': {'schema': 'filtmall.cited-facts-inline/v2', 'payload': {
                    'segments': [{'text': '错误关联分析', 'citation_ids': ['r']}],
                    'references': [{'citation_id': 'r', 'number': 1, 'goods_id': 'g',
                                    'sku_id': 'different', 'title': '其他SKU的资料',
                                    'publisher': '测试发布者', 'public_snippet': '其他SKU的摘要'}],
                }}}
        fragment = cards.render_widget([card], {}, 'auto')
        self.assertNotIn('其他SKU的资料', fragment)
        self.assertNotIn('错误关联分析', fragment)
        self.assertIn('引用资料格式或商品关联异常', fragment)

    def test_v4_shared_reference_group_keeps_only_references_used_by_this_card(self):
        card = {'title': '当前商品', 'rank': 1, 'goods_id': 'g', 'sku_id': 's',
                'analysis_evidence': {'schema': 'filtmall.cited-facts-inline/v2', 'payload': {
                    'segments': [{'text': '当前商品分析', 'citation_ids': ['r1']}],
                    'references': [
                        {'citation_id': 'r1', 'number': 1, 'goods_id': 'g', 'sku_id': 's',
                         'title': '当前资料', 'publisher': '发布者', 'public_snippet': '当前摘要'},
                        {'citation_id': 'r2', 'number': 2, 'goods_id': 'g2', 'sku_id': 's2',
                         'title': '其他商品资料', 'publisher': '发布者', 'public_snippet': '其他摘要'},
                    ],
                }}}
        fragment = cards.render_widget([card], {}, 'auto')
        self.assertIn('当前商品分析[1]', fragment)
        self.assertIn('当前资料', fragment)
        self.assertNotIn('其他商品资料', fragment)
        self.assertNotIn('引用资料格式或商品关联异常', fragment)


if __name__ == '__main__':
    unittest.main()
