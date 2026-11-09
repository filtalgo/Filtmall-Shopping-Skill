import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import time
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cards
import client
import commerce_render
import service


def checkout(identifier='CS1'):
    return {'value': {'status': 'current', 'mode': 'session', 'checkout_id': identifier,
            'checkout_status': 'in_progress', 'payment_status': 'unpaid', 'items': [
                {'title': '<script>商品</script>', 'quantity': 1, 'unit_price': {'currency': 'CNY', 'minor_units': '15900'}}],
            'amounts': {'total': {'currency': 'CNY', 'minor_units': '14900'}, 'shipping': {'currency': 'CNY', 'minor_units': '0'}},
            'links': [{'rel': 'payment', 'href': 'https://buyer.test/cashier?orderSn=T1&scene=TRADE'}]}}


class CommerceTests(unittest.TestCase):
    def test_terminal_checkout_keeps_payment_fact_without_payment_action_or_body_fallback(self):
        for state in ('canceled', 'cancelled', 'completed'):
            for fmt in ('widget', 'html', 'md'):
                document = checkout()
                document['value']['checkout_status'] = state
                document['value']['links'].append({'rel': 'checkout', 'href': 'https://buyer.test/checkout/CS1'})
                class Fake:
                    def resume(self, *args):
                        return {'ok': True, 'status': 'completed', 'checkouts': [document], 'answer': {
                            'value': {'content': '旧正文链接：https://buyer.test/cashier?orderSn=T1'}}}
                with tempfile.TemporaryDirectory() as directory:
                    output = service.handle(Fake(), {'op': 'resume', 'conversation': 'c'}, fmt, directory)
                    content = Path(output['checkout_file']).read_text()
                    self.assertIn('支付状态：未支付', content)
                    self.assertNotIn('请前往收银台完成付款', content)
                    self.assertNotIn('打开收银台', content)
                    self.assertNotIn('https://buyer.test/cashier', content)
                    self.assertIn('查看结算', content)
                    self.assertEqual(output['payment_links'], [])
                document['value']['links'] = [document['value']['links'][0]]
                content, links = commerce_render.render([document], 'checkout', fmt, cards.ImageBudget())
                self.assertEqual(links, [])
                self.assertIn('该结算已结束，暂无可用的详情入口', content)

    def test_after_sale_detail_and_list_follow_shared_display_order(self):
        for detail_order, list_order in ((1, 2), (2, 1)):
            result = {'after_sales': [{'display_order': detail_order, 'value': {'status': 'current',
                      'after_sale_id': 'AS1', 'items': [], 'links': []}}],
                      'after_sale_lists': [{'display_order': list_order, 'value': {'status': 'current', 'records': []}}]}
            for fmt in ('widget', 'html', 'md'):
                content = service.render(result, fmt, 0)['after_sale_content']
                self.assertEqual(content.index('AS1') < content.index('售后列表'), detail_order < list_order)

    def test_three_formats_need_no_answer_and_preserve_all_entities(self):
        class Fake:
            def resume(self, *args):
                return {'ok': True, 'status': 'completed', 'checkouts': [checkout(), checkout('CS2')],
                        'after_sales': [{'value': {'status': 'current', 'service_status': 'COMPLETE', 'after_sale_id': 'AS1',
                                        'requested_refund': {'currency': 'CNY', 'minor_units': '14900'}, 'items': [], 'links': []}}]}
        with tempfile.TemporaryDirectory() as directory:
            for fmt in ('widget', 'html', 'md'):
                output = service.handle(Fake(), {'op': 'resume', 'conversation': 'c'}, fmt, directory)
                self.assertEqual(output['checkout_count'], 2)
                self.assertNotIn('answer_file', output)
                content = Path(output['checkout_file']).read_text()
                sale = Path(output['after_sale_file']).read_text()
                for text in ('结算 · CS1', '结算 · CS2', '149.00', '0.00', '待付款'):
                    self.assertIn(text, content)
                self.assertNotIn('<script>', content)
                self.assertIn('实际到账', sale)
                self.assertIn('尚未确认', sale)
                if fmt == 'widget':
                    self.assertNotIn('<html', content)
                    self.assertEqual(output['checkout_fragment_file'], output['checkout_file'])
                elif fmt == 'html':
                    self.assertTrue(content.startswith('<!doctype html>'))
                    self.assertEqual(content.count('<html'), 1)
                    self.assertEqual(output['checkout_page_file'], output['checkout_file'])
                else:
                    self.assertTrue(output['checkout_file'].endswith('.md'))
                    self.assertNotIn('<details', content)
                    self.assertNotIn('checkout_page_file', output)
                    self.assertNotIn('checkout_fragment_file', output)
                self.assertEqual(output['payment_links'], ['https://buyer.test/cashier?orderSn=T1&scene=TRADE'])
                if os.name != 'nt': self.assertEqual(Path(output['checkout_file']).stat().st_mode & 0o777, 0o600)

    def test_cart_retains_all_rows_and_formats_zero_missing_prices(self):
        cart = {'status': 'current', 'items': [{'sku_id': str(i), 'title': '商品%s' % i, 'quantity': i + 1,
                'checked': i < 2, **({'price': 0} if i == 0 else {})} for i in range(5)]}
        for fmt in ('widget', 'html', 'md'):
            status, content = commerce_render.render_cart(cart, fmt)
            self.assertEqual(status, 'current')
            for text in ('商品4', '已选 2 款 / 3 件', '全车 5 款 · 15 件', '价格待确认'):
                self.assertIn(text, content)
            self.assertIn('0.00' if fmt != 'md' else r'0\.00', content)
            self.assertNotIn('合计', content)
            if fmt != 'md': self.assertIn('展开另外 2 款商品', content)
            else: self.assertNotIn('<details', content)

    def test_current_turn_latest_per_entity_unknown_versions_and_empty_lists(self):
        with tempfile.TemporaryDirectory() as directory:
            api = client.Client('https://control.test', 'agent', client.Store(directory))
            def doc(identity, revision, state='current', version=1, request='r', deleted=False):
                return {'document_id': identity, 'revision': revision, 'kind': 'filtalgo.commerce.checkout',
                        'schema_version': version, 'request_id': request, 'deleted': deleted, 'value': {'status': state}}
            docs = [doc('old', 40), doc('a', 41), doc('a', 43, 'unavailable'), doc('b', 44, version=2),
                    doc('other', 45, request='other'), doc('gone', 41), doc('gone', 46, deleted=True)]
            api.documents = lambda *args: docs
            value = {'id': 's', 'pending': {'request_id': 'r', 'start_revision': 40}}
            result = api.settle('c', value, 'completed')
            self.assertTrue(result['ok'])
            self.assertEqual([d['document_id'] for d in result['checkouts']], ['a', 'b'])
            self.assertEqual([d['value']['status'] for d in result['checkouts']], ['unavailable', 'unavailable'])
            api.documents = lambda *args: []
            result = api.settle('c', value, 'completed')
            self.assertNotIn('checkouts', result)
            self.assertEqual(result['error']['code'], 'NO_PUBLIC_RESPONSE')

    def test_output_failure_preserves_business_status_other_files_and_original_request(self):
        class Fake:
            calls = 0
            def resume(self, *args):
                self.calls += 1
                return {'ok': True, 'status': 'completed', 'checkouts': [checkout()], 'answer': {'value': {'content': '正文'}}}
        fake = Fake()
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / 'directory'
            invalid.mkdir()
            output = service.handle(fake, {'op': 'resume', 'conversation': 'c', 'checkout_path': str(invalid)}, 'widget', directory)
            self.assertEqual(output['status'], 'completed')
            self.assertEqual(output['presentation_status'], 'failed')
            self.assertNotIn('checkout_file', output)
            self.assertTrue(Path(output['answer_file']).is_file())
            recovered = service.handle(fake, {'op': 'resume', 'conversation': 'c'}, 'widget', directory)
            self.assertTrue(Path(recovered['checkout_file']).is_file())
            self.assertEqual(fake.calls, 2)
            with self.assertRaises(client.ClientError):
                service.handle(fake, {'op': 'send', 'conversation': 'c', 'text': 'x', 'out_dirs': {
                    'checkout_path': str(invalid), 'answer_path': str(invalid)}}, 'md', directory)

    def test_render_failure_isolated_and_unknown_state_not_promoted(self):
        value = checkout()
        value['value']['items'] = 'invalid'
        with tempfile.TemporaryDirectory() as directory:
            output = service.render({'checkouts': [value], 'cart': {'status': 'current', 'items': []}}, 'widget', 0)
            service.write_outputs(output, {'conversation': 'c'}, directory)
            self.assertEqual(output['presentation_status'], 'failed')
            self.assertTrue(Path(output['cart_file']).exists())
        value = checkout(); value['value']['payment_status'] = 'unknown'
        for fmt in ('widget', 'html', 'md'):
            content, _ = commerce_render.render([value], 'checkout', fmt, cards.ImageBudget())
            self.assertIn('支付待核实', content)
            self.assertNotIn('请前往收银台完成付款', content)
        with tempfile.TemporaryDirectory() as directory, patch.object(cards, 'render_widget', side_effect=RuntimeError('failed')):
            output = {'_format': 'widget', 'widget_cards': [], 'cart_content': '购物车', 'answer': '正文'}
            service.write_outputs(output, {'conversation': 'c'}, directory)
            self.assertEqual(output['presentation_status'], 'failed')
            self.assertEqual(Path(output['cart_file']).read_text(), '购物车')
            self.assertEqual(Path(output['answer_file']).read_text(), '正文')

    def test_image_budget_deduplicates_and_exhaustion_uses_placeholder(self):
        rows = [{'thumbnail': 'https://allowed.test/same'} for _ in range(4)]
        budget = cards.ImageBudget()
        with patch.object(cards, 'thumbnail_data', return_value=(b'image', 'image/png')) as fetch:
            cards.inline_images(rows, 5, budget)
            self.assertEqual(fetch.call_count, 1)
            self.assertTrue(all(r['thumbnail'].startswith('data:') for r in rows))
        exhausted = cards.ImageBudget(seconds=-1)
        with patch.object(cards, 'thumbnail_data', side_effect=AssertionError('network')):
            cards.inline_images([{'thumbnail': 'https://allowed.test/new'}], 5, exhausted)
        self.assertEqual(exhausted.cache['https://allowed.test/new'], '')
        self.assertEqual(commerce_render.navigation([{'rel': 'payment', 'href': 'javascript:alert(1)'}]), [])

    def test_slow_download_cannot_hold_render_beyond_shared_deadline(self):
        def slow(*args):
            time.sleep(0.2)
            return b'image', 'image/png'
        budget = cards.ImageBudget(seconds=0.02)
        started = time.monotonic()
        rows = [{'thumbnail': 'https://allowed.test/slow'}, {'thumbnail': 'https://allowed.test/next'}]
        with patch.object(cards, 'thumbnail_data', side_effect=slow) as fetch:
            cards.inline_images(rows, 5, budget)
            self.assertLess(time.monotonic() - started, 0.15)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual([r['thumbnail'] for r in rows], ['', ''])


if __name__ == '__main__': unittest.main()
