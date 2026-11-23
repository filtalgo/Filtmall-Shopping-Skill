import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import address_cards
import cards
import client
import customer_service_cards
import logistics_cards
import service


FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'presentation-baseline.json'


def card_doc(goods_id, title, rank=1, price='59.00', spec='10片/盒', schema='filtmall.product-card/v2',
             sku_id='S1', revision=15, request_id=None, reason='温和补水'):
    return {
        'document_id': 'doc-' + str(goods_id or rank),
        'revision': revision,
        'request_id': request_id,
        'kind': 'filtalgo.shopping.block:' + schema,
        'value': {
            'block': {
                'schema': schema,
                'payload': {
                    'rank': rank,
                    'product': {
                        'goods_id': goods_id,
                        'sku_id': sku_id,
                        'title': title,
                        'price_amount': price,
                        'spec_summary': spec,
                        'availability': 'in_stock',
                    },
                    'recommendation_reason': reason,
                },
            },
        },
    }


class DisplayMarkdownTests(unittest.TestCase):
    def test_baseline_fixtures_produce_complete_single_column_display_markdown(self):
        baseline = json.loads(FIXTURES.read_text(encoding='utf8'))
        with tempfile.TemporaryDirectory() as directory:
            for case in baseline['cases']:
                with self.subTest(case=case['id']):
                    class Stub:
                        def send(self, *args):
                            return case['result']

                    output = service.handle(
                        Stub(),
                        {'op': 'send', 'conversation': case['id'], 'text': '测试请求'},
                        'md',
                        directory,
                    )
                    self.assertIn('display_file', output)
                    display_path = Path(output['display_file'])
                    self.assertTrue(display_path.is_file())
                    if os.name != 'nt':
                        self.assertEqual(display_path.stat().st_mode & 0o777, 0o600)
                    content = display_path.read_text(encoding='utf8')
                    self.assertNotIn('| --- |', content)
                    self.assertNotIn('<article', content)
                    self.assertNotIn('<script', content)
                    for expected_url in case['expected_urls']:
                        self.assertIn(expected_url, content)
                    if case['id'] == 'commerce_snapshot_without_answer':
                        self.assertNotIn('answer_file', output)
                        self.assertIn('购物车', content)
                    if case['id'] == 'zero_candidates_empty_search':
                        self.assertEqual(output['card_count'], 0)
                        self.assertNotIn('https://m.filtalgo.com/pages/goods/product/detail', content)
                    elif case['expected_urls'] and case['result'].get('context_documents'):
                        self.assertGreater(output['card_count'], 0)

    def test_short_answer_keeps_published_product_cards_without_leaking_unselected_or_old_items(self):
        # 1) 简短导语未逐一点名：保留本轮发布的 product-card/v2，但过滤历史 revision 与异请求卡片。
        result_short = {
            'start_revision': 10,
            'request_id': 'req-current',
            'answer': {'value': {'content': '已按您的预算筛选出以下两款保湿面膜：'}},
            'context_documents': [
                card_doc('OLD1', '上一轮旧面膜', rank=1, revision=9, request_id=None),
                card_doc('FOREIGN1', '其他请求面膜', rank=1, revision=12, request_id='req-other'),
                card_doc('G1', '玻尿酸补水面膜', rank=1, revision=11, request_id='req-current'),
                card_doc('G2', '积雪草舒缓面膜', rank=2, revision=12, request_id=None),
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            rendered = service.render(result_short, 'md', 0)
            service.write_outputs(rendered, {'conversation': 'short'}, directory)
            self.assertEqual(rendered['card_count'], 2)
            text = Path(rendered['display_file']).read_text(encoding='utf8')
            self.assertIn('玻尿酸补水面膜', text)
            self.assertIn('积雪草舒缓面膜', text)
            self.assertNotIn('上一轮旧面膜', text)
            self.assertNotIn('其他请求面膜', text)

            # 2) 答复明确点名其中一款时：未点名的候选不得进入 display_file。
            result_subset = {
                'answer': {'value': {'content': '更推荐玻尿酸补水面膜，日常保湿足够。'}},
                'context_documents': [
                    card_doc('G1', '玻尿酸补水面膜', rank=1),
                    card_doc('G2', '积雪草舒缓面膜', rank=2),
                ],
            }
            subset_out = service.render(result_subset, 'md', 0)
            service.write_outputs(subset_out, {'conversation': 'subset'}, directory)
            subset_text = Path(subset_out['display_file']).read_text(encoding='utf8')
            self.assertEqual(subset_out['card_count'], 1)
            self.assertIn('玻尿酸补水面膜', subset_text)
            self.assertNotIn('积雪草舒缓面膜', subset_text)

            # 3) 原始候选列表 filtmall.products/v2 未被答复点名时不得外泄；明确无结果答复时也不展示卡片。
            unselected_pool = {
                'answer': {'value': {'content': '请先补充您的肤质偏好。'}},
                'context_documents': [{
                    'document_id': 'pool-1',
                    'revision': 20,
                    'kind': 'filtalgo.shopping.block:filtmall.products/v2',
                    'value': {'block': {'schema': 'filtmall.products/v2', 'payload': {
                        'products': [{'goods_id': 'P1', 'sku_id': 'S1', 'title': '未选中候选商品', 'price_amount': '99'}]
                    }}},
                }],
            }
            pool_out = service.render(unselected_pool, 'md', 0)
            self.assertEqual(pool_out['card_count'], 0)
            self.assertNotIn('未选中候选商品', pool_out['display_content'])

            empty_reply = {
                'answer': {'value': {'content': '抱歉，未找到符合预算 5 元以内的面膜商品。'}},
                'context_documents': [card_doc('G1', '玻尿酸补水面膜', rank=1)],
            }
            empty_out = service.render(empty_reply, 'md', 0)
            self.assertEqual(empty_out['card_count'], 0)
            self.assertNotIn('玻尿酸补水面膜', empty_out['display_content'])

    def test_missing_price_spec_and_link_are_explicit_without_fabrication(self):
        result = {
            'context_documents': [
                card_doc(None, '无链接测试商品', rank=1, price=None, spec='', sku_id=None, reason=''),
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            out = service.render(result, 'md', 0, True)
            service.write_outputs(out, {'conversation': 'missing-fields'}, directory)
            text = Path(out['display_file']).read_text(encoding='utf8')
            self.assertIn('价格未提供', text)
            self.assertIn('规格未提供', text)
            self.assertIn('商品链接：当前未提供详情入口', text)
            self.assertNotIn('https://', text)

    def test_complete_remote_answer_avoids_duplicate_product_block_while_partial_answer_supplements(self):
        url = 'https://m.filtalgo.com/pages/goods/product/detail?goodsId=G1&skuId=S1'
        image_url = 'https://filtering-tech-product-data.oss-cn-beijing.aliyuncs.com/test-mask.jpg'
        complete_answer = (
            '1. 玻尿酸补水面膜\n'
            '价格：59 元 · 规格：10片/盒\n'
            '**推荐理由**：温和补水。\n'
            '![玻尿酸补水面膜](' + image_url + ')\n'
            '[打开商品页](' + url + ')'
        )
        doc = card_doc('G1', '玻尿酸补水面膜', rank=1, price='59.00', spec='10片/盒', sku_id='S1', reason='')
        doc['value']['block']['payload']['product']['thumbnail'] = image_url
        full = service.render({'answer': {'value': {'content': complete_answer}}, 'context_documents': [doc]}, 'md', 0)
        self.assertEqual(full['display_content'].count(url), 1)
        self.assertNotIn('## 商品信息与入口', full['display_content'])
        self.assertIn(url, full['cards_markdown'])
        self.assertIn(image_url, full['cards_markdown'])

        # 即使文字、规格与详情完整，缺图也不能被去重逻辑当作完整展示。
        missing_image = complete_answer.replace('![玻尿酸补水面膜](' + image_url + ')\n', '')
        repaired = service.render({'answer': {'value': {'content': missing_image}}, 'context_documents': [doc]}, 'md', 0)
        self.assertIn('![玻尿酸补水面膜](' + image_url + ')', repaired['display_content'])

        unsafe = dict(cards.collect({'context_documents': [doc]}, cards.DEFAULT_URL_BASE)[0], thumbnail='https://untrusted.invalid/image.jpg')
        unsafe_md = cards.render_markdown([unsafe], {})
        self.assertNotIn('untrusted.invalid', unsafe_md)
        self.assertIn('商品图片暂不可用', unsafe_md)

        # 远端答复漏掉链接时，自动补充“商品信息与入口”段，且不把正文中已有的推荐理由重复贴第二遍。
        no_link_answer = '1. 玻尿酸补水面膜\n**商品分析**：日常补水。\n**推荐理由**：温和补水。'
        supplemented = service.render({'answer': {'value': {'content': no_link_answer}}, 'context_documents': [doc]}, 'md', 0)
        self.assertEqual(supplemented['display_content'].count(url), 1)
        self.assertIn('## 商品信息与入口', supplemented['display_content'])
        self.assertEqual(supplemented['display_content'].count('温和补水'), 1)

    def test_markdown_image_destination_preserves_url_with_parentheses_without_angle_wrapper(self):
        url = 'https://filtering-tech-product-data.oss-cn-beijing.aliyuncs.com/mask(front).jpg?x-oss-process=style/400X400'
        card = {'title': '补水[面膜]', 'thumbnail': url, 'url': 'https://m.filtalgo.com/pages/goods/product/detail?goodsId=G1&skuId=S1'}
        encoded = url.replace('(', '%28').replace(')', '%29')
        markdown = cards.markdown_image(card)
        self.assertEqual(markdown, '![补水\\[面膜\\]](' + encoded + ')')
        self.assertTrue(cards.answer_covers_card(card, '补水[面膜]\n' + markdown + '\n[查看商品详情](' + card['url'] + ')'))
        self.assertTrue(cards.answer_covers_card(card, '补水[面膜]\n![商品](<' + url + '>)\n[查看商品详情](' + card['url'] + ')'))

    def test_all_commerce_families_and_privacy_boundaries_in_display_file(self):
        now_ms = int(time.time() * 1000)
        binding = 'cd' * 32
        address_snap = {
            'status': 'current', 'scene': 'address_book', 'way': None,
            'selection_status': 'not_applicable', 'selected_address_id': None,
            'authorization_binding': binding, 'authorization_expires_at': now_ms + 60000,
            'page': {'number': 1, 'has_more': False},
            'items': [{
                'address_id': 'ADDR-SECRET-1', 'recipient_name': '张三',
                'mobile_display': '138****1234', 'region_path': '浙江省,杭州市,西湖区',
                'detail': '文三路 100 号', 'is_default': True,
            }],
        }
        logistics_snap = {
            'status': 'current',
            'query': {'order_sn': 'ORD-100', 'package_no': None, 'include_items': True, 'include_traces': True},
            'fetched_at': now_ms, 'empty_reason': None, 'reason': None,
            'authorization_binding': binding, 'authorization_expires_at': now_ms + 60000,
            'packages': [{
                'package_no': 'PKG-1', 'logistics_name': '顺丰速运', 'logistics_no': 'SF10001',
                'logistics_time': '2026-11-16 10:00',
                'items': [{'goods_name': '修护面膜', 'sku_name': '10片/盒', 'deliver_number': 1}],
                'trace_status': 'available', 'trace_order': 'source',
                'traces': [{'time': '2026-11-16 12:00', 'occurred_at': None, 'description': '快件已发出', 'location': '杭州', 'status': '运输中'}],
            }],
        }
        cs_snap = {
            'status': 'current',
            'query': {'scene': 'order', 'store_id': 'STORE-INTERNAL', 'goods_id': None, 'sku_id': None, 'order_sn': 'ORD-100', 'after_sale_sn': None},
            'fetched_at': now_ms, 'reason': None,
            'authorization_binding': binding, 'authorization_expires_at': now_ms + 60000,
            'link_origins': ['https://m.filtalgo.com'],
            'entry': {
                'scene': 'order', 'store_id': 'STORE-INTERNAL', 'goods_id': '', 'sku_id': '',
                'order_sn': 'ORD-100', 'after_sale_sn': '', 'store_name': '筛电官方旗舰店',
                'default_channel': 'mobile_h5',
                'channels': {'mobile_h5': {'url': 'https://m.filtalgo.com/pages/chat/index?orderSn=ORD-100'}},
            },
        }
        checkout_doc = {
            'value': {
                'status': 'current', 'mode': 'preview', 'checkout_id': 'CHK-INTERNAL',
                'checkout_status': 'ready_for_payment', 'payment_status': 'unpaid',
                'items': [{'title': '修护面膜', 'quantity': 1, 'unit_price': {'currency': 'CNY', 'minor_units': '6900'}}],
                'amounts': {'total': {'currency': 'CNY', 'minor_units': '6900'}},
                'links': [{'rel': 'payment', 'href': 'https://buyer.filtalgo.com/payment/cashier?orderSn=TR1&paymentScene=TRADE'}],
            }
        }
        after_sale_doc = {
            'value': {
                'status': 'current', 'after_sale_id': 'AS-200', 'service_type': 'RETURN_MONEY',
                'service_status': 'COMPLETE',
                'requested_refund': {'currency': 'CNY', 'minor_units': '6900'},
                'items': [{'title': '修护面膜', 'quantity': 1}],
                'links': [],
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            class Stub:
                def send(self, *args):
                    return {
                        'ok': True, 'status': 'completed', 'answer': None,
                        'cart': {'status': 'unavailable', 'items': []},
                        'address_snapshots': [address_snap],
                        'checkouts': [checkout_doc],
                        'logistics_snapshots': [logistics_snap],
                        'after_sales': [after_sale_doc],
                        'customer_service_snapshots': [cs_snap],
                    }

            output = service.handle(Stub(), {'op': 'send', 'conversation': 'all-commerce', 'text': '汇总查看'}, 'md', directory)
            self.assertNotIn('answer_file', output)
            text = Path(output['display_file']).read_text(encoding='utf8')
            self.assertIn('避免重复操作', text)
            self.assertNotIn('购物车为空', text)
            self.assertIn('138\\*\\*\\*\\*1234', text)
            self.assertIn('https://m.filtalgo.com/pages/mine/payment/payOrder?trade_sn=TR1', text)
            self.assertIn('未支付', text)
            self.assertIn('实际到账：尚未确认', text)
            self.assertIn('[联系客服](https://m.filtalgo.com/pages/chat/index?orderSn=ORD-100)', text)
            self.assertNotIn('<a ', text)
            for secret in (binding, 'ADDR-SECRET-1', 'CHK-INTERNAL', 'STORE-INTERNAL'):
                self.assertNotIn(secret, text)

    def test_non_completed_and_error_states_do_not_fabricate_display_file(self):
        with tempfile.TemporaryDirectory() as directory:
            class AuthStub:
                def send(self, *args):
                    return {'ok': True, 'status': 'authorization_required', 'authorization_url': 'https://m.filtalgo.com/auth'}

            auth_out = service.handle(AuthStub(), {'op': 'send', 'conversation': 'auth', 'text': '看订单'}, 'md', directory)
            self.assertEqual(auth_out['status'], 'authorization_required')
            self.assertNotIn('display_file', auth_out)

            class EmptyStub:
                def resume(self, *args):
                    return {'ok': False, 'status': 'completed', 'error': {'code': 'NO_PUBLIC_RESPONSE', 'message': '无结果'}}

            empty_out = service.handle(EmptyStub(), {'op': 'resume', 'conversation': 'empty'}, 'md', directory)
            self.assertFalse(empty_out['ok'])
            self.assertNotIn('display_file', empty_out)


if __name__ == '__main__':
    unittest.main()
