import base64
import gzip
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import client
import cards
import service

class OutputTests(unittest.TestCase):
    def test_cart_and_products_follow_each_format(self):
        item = {'title': '推荐商品', 'rank': 1, 'price': '29.9', 'url': None, 'thumbnail': ''}
        cart = {'status': 'current', 'items': [{'sku_id': 's', 'title': '<script> & 面膜',
                                                 'quantity': 2, 'checked': False, 'price': 9.5}]}
        with tempfile.TemporaryDirectory() as d:
            for fmt in ('widget', 'html', 'md'):
                with self.subTest(format=fmt), patch.object(cards, 'collect', return_value=[item.copy()]):
                    output = service.render({'cart': cart}, fmt, 0, True)
                    service.write_outputs(output, {'conversation': 'c'}, d)
                    product = Path(output['html_file']).read_text(encoding='utf8')
                    cart_content = Path(output['cart_file']).read_text(encoding='utf8')
                    self.assertIn('推荐商品', product)
                    self.assertIn('&lt;script&gt; &amp; 面膜', cart_content)
                    self.assertNotIn('<script>', cart_content)
                    self.assertIn('2 件，单价 9.5 元（未选）', cart_content)
                    if fmt == 'widget':
                        self.assertEqual(output['cart_fragment_file'], output['cart_file'])
                        self.assertNotIn('<!doctype', cart_content)
                        self.assertNotIn('page_file', output)
                    elif fmt == 'html':
                        self.assertEqual(output['cart_page_file'], output['cart_file'])
                        self.assertTrue(cart_content.startswith('<!doctype html>'))
                        self.assertTrue(product.startswith('<!doctype html>'))
                        self.assertNotIn('fragment_file', output)
                    else:
                        self.assertTrue(output['cart_file'].endswith('.md'))
                        self.assertTrue(output['html_file'].endswith('.cards.md'))
                        self.assertNotIn('<section', cart_content)

    def test_cart_document_is_rendered_and_written_privately(self):
        class Stub:
            def send(self, *args):
                return {'ok': True, 'status': 'completed', 'cart': {'status': 'current', 'items': [
                    {'sku_id': 'sku', 'title': '<面膜> [特价]', 'quantity': 2, 'checked': True, 'price': 29.9},
                    {'sku_id': 'sku2', 'quantity': 1, 'checked': False}]}}
        with tempfile.TemporaryDirectory() as d:
            result = service.handle(Stub(), {'op': 'send', 'conversation': 'c', 'text': '查看购物车'}, 'md', d)
            self.assertEqual(result['cart_status'], 'current')
            path = Path(result['cart_file'])
            content = path.read_text(encoding='utf8')
            self.assertIn('&lt;面膜&gt; \\[特价\\]', content)
            self.assertIn('2 件，单价 29.9 元（已选）', content)
            self.assertIn('商品：1 件（未选）', content)
            self.assertNotIn('sku', content)
            if os.name != 'nt': self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_cart_empty_unavailable_and_invalid_do_not_look_alike(self):
        self.assertEqual(service.render_cart({'status': 'current', 'items': []}), ('current', '购物车为空。\n'))
        for value in ({'status': 'unavailable', 'items': []}, {'status': 'current', 'items': [{}]},
                      {'status': 'current', 'items': [{'sku_id': 's', 'quantity': True, 'checked': True}]}):
            status, text = service.render_cart(value)
            self.assertEqual(status, 'unavailable')
            self.assertIn('避免重复操作', text)
        for fmt in ('widget', 'html', 'md'):
            status, content = service.render_cart({'status': 'unavailable', 'items': []}, fmt)
            self.assertEqual(status, 'unavailable')
            self.assertIn('避免重复操作', content)
            self.assertNotIn('购物车为空', content)

    def test_old_format_parameters_are_rejected(self):
        class Stub: pass
        for fmt in ('markdown', 'text', 'json'):
            with self.subTest(format=fmt), self.assertRaises(service.ClientError) as error:
                service.handle(Stub(), {'op': 'send', 'conversation': 'c', 'text': 'x', 'format': fmt}, 'widget')
            self.assertEqual(error.exception.code, 'INVALID_FORMAT')
        self.assertEqual(service.handle(Stub(), {'op': 'ping'}, 'widget')['capabilities']['formats'],
                         ['widget', 'html', 'md'])

    def test_markdown_escapes_are_readable_in_answer_and_cards(self):
        result = {'answer': {'value': {'content': r'价格 29\.9，敷15\-20分钟，\* 和 29\\.9，\n'}},
                  'context_documents': [{'kind': 'filtalgo.shopping.block:filtmall.product-card/v2',
                      'value': {'block': {'schema': 'filtmall.product-card/v2', 'payload': {
                          'product': {'goods_id': '1', 'title': r'商品 29\.9', 'price_amount': r'29\.9'}}}}}]}
        rendered = service.render(result, 'widget', 0, True)
        self.assertEqual(rendered['answer'], r'价格 29.9，敷15-20分钟，* 和 29\\.9，\n')
        self.assertEqual(rendered['widget_cards'][0]['title'], '商品 29.9')
        self.assertEqual(rendered['widget_cards'][0]['price'], '29.9')

    def test_v2_card_preserves_text_and_escapes_html(self):
        title = '商品 <测试> & "规格"'
        block = {'schema': 'filtmall.product-card/v2', 'payload': {
            'rank': 1, 'product': {'goods_id': 'a&b', 'sku_id': 's', 'title': title,
                                    'price_amount': '12.00'}, 'recommendation_reason': '安全 <好>'}}
        result = {'context_documents': [{'kind': 'filtalgo.shopping.block:filtmall.product-card/v2',
                                         'value': {'block': block}}]}
        card = cards.collect(result, cards.DEFAULT_URL_BASE)[0]
        self.assertEqual(card['title'], title)
        self.assertEqual(card['url'], 'https://m.filtalgo.com/pages/goods/product/detail?goodsId=a%26b&skuId=s')
        rendered = cards.render_widget([card], {}, 'light', images=False)
        self.assertIn('商品 &lt;测试&gt; &amp; &quot;规格&quot;', rendered)
        self.assertIn('安全 &lt;好&gt;', rendered)

    def test_once_reads_one_request_and_exits(self):
        with tempfile.TemporaryDirectory() as d:
            proc = subprocess.run([sys.executable, str(Path(service.__file__)), '--once', '--state-dir', d],
                                  input='{"op":"ping"}\n{"op":"ping"}\n', text=True, capture_output=True, timeout=10)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            lines = proc.stdout.splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])['status'], 'idle')

    def test_once_defaults_to_send(self):
        with tempfile.TemporaryDirectory() as d:
            proc = subprocess.run([sys.executable, str(Path(service.__file__)), '--once', '--state-dir', d],
                                  input='{"conversation":"test","text":""}\n', text=True, capture_output=True, timeout=10)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)['error']['code'], 'INVALID_TEXT')

    def test_data_uri_must_fit_thumbnail_limits(self):
        def png(w, h, extra=b''):
            return b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + w.to_bytes(4, 'big') + h.to_bytes(4, 'big') + extra
        def uri(data): return 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')
        self.assertIsNotNone(cards.thumbnail_data(uri(png(160, 160)), 1))
        self.assertIsNone(cards.thumbnail_data(uri(png(400, 400)), 1))
        self.assertIsNone(cards.thumbnail_data(uri(png(10, 10, b'x' * 16000)), 1))

    def test_fragment_page_are_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            out = {'_format': 'widget', 'cards_html': '<div><a href="https://example.test">商品</a></div>'}
            page_out = {'_format': 'html', 'cards_html': out['cards_html']}
            service.write_outputs(out, {'conversation': 'c'}, d)
            service.write_outputs(page_out, {'conversation': 'c'}, d)
            fragment = Path(out['fragment_file']).read_text(encoding='utf8')
            page = Path(page_out['page_file']).read_text(encoding='utf8')
            self.assertFalse(fragment.startswith('<!doctype'))
            self.assertIn(fragment, page)
            self.assertTrue(page.startswith('<!doctype html>'))
            self.assertEqual(out['html_file'], out['fragment_file'])
            self.assertEqual(page_out['html_file'], page_out['page_file'])
            self.assertNotIn('page_file', out)
            self.assertNotIn('fragment_file', page_out)

    def test_widget_embeds_compressed_image(self):
        data = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/aXsAAAAASUVORK5CYII=')
        item = {'title': '商品', 'url': 'https://example.test', 'thumbnail': 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')}
        with tempfile.TemporaryDirectory() as d:
            with patch.object(cards, 'collect', return_value=[item]), patch.object(cards, 'attach_answer_reasons'), patch.object(cards, 'attach_answer_analysis'):
                result = service.render({}, 'widget', 0)
                service.write_outputs(result, {'conversation': 'c'}, d)
            fragment = Path(result['fragment_file']).read_text(encoding='utf8')
            self.assertNotIn('page_file', result)
            import re
            match = re.search(r'src="data:image/png;base64,([^"]+)"', fragment)
            self.assertIsNotNone(match)
            compressed = base64.b64decode(match.group(1))
            self.assertLessEqual(len(compressed), cards.IMAGE_MAX_BYTES)
            self.assertLessEqual(max(cards.image_dimensions(compressed)), cards.IMAGE_MAX_SIDE)
            self.assertFalse(Path(result['fragment_file']).parent.joinpath('images').exists())

    def test_invalid_image_uses_placeholder(self):
        items = [{'thumbnail': 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\ninvalid').decode()}]
        cards.inline_images(items, 1)
        self.assertEqual(items[0]['thumbnail'], '')

    def test_normal_repeat_after_completion(self):
        from test_guards import make_client
        api = make_client()
        api.http.operation_status = 'completed'
        api.send('c', '相同问题', timeout=1)
        self.assertEqual(api.send('c', '相同问题', wait=False)['status'], 'accepted')

    def test_async_send_preserves_authorization(self):
        class Fake:
            def send(self, *args): return {'ok': True, 'status': 'authorization_required', 'authorization_url': 'https://example.test/auth'}
        result = service.handle(Fake(), {'op': 'send', 'conversation': 'c', 'text': 'x', 'wait': False}, 'md')
        self.assertEqual(result['status'], 'authorization_required')
        self.assertIn('authorization_url', result)

    def test_private_output_permissions(self):
        if os.name == 'nt': self.skipTest('Unix permissions')
        with tempfile.TemporaryDirectory() as d:
            out = {'answer': 'private'}
            service.write_outputs(out, {'conversation': 'c'}, d)
            path = Path(out['answer_file'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_untrusted_thumbnail_never_fetches(self):
        with patch('urllib.request.build_opener', side_effect=AssertionError('network')):
            for url in ('http://127.0.0.1/private', 'https://evil.example/x', 'data:image/svg+xml,x'):
                self.assertIsNone(cards.thumbnail_data(url, 1))

    def test_heartbeat_updates_during_wait(self):
        class Fake:
            def resume(self, *args):
                time.sleep(0.7)
                return {'ok': True, 'status': 'completed'}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'heartbeat.json'
            service.run_request(Fake(), {'op': 'resume', 'conversation': 'c'}, 'md', heartbeat_path=path)
            self.assertTrue(path.exists())

    def test_invalid_timeout_does_not_submit(self):
        class Fake:
            def send(self, *args): raise AssertionError('must not submit')
        with self.assertRaises(client.ClientError):
            service.handle(Fake(), {'op': 'send', 'conversation': 'c', 'text': 'x', 'timeout': 'bad'}, 'json')
    def test_region_roundtrip(self):
        nodes = [['11', '0', '北京市', 'province']]
        value = {'schema': 'filtmall.region-selector/v1', 'encoding': 'gzip+base64', 'columns': ['id', 'parent_id', 'name', 'level'], 'root_id': '0', 'group_id': 'a', 'count': 1, 'data': base64.b64encode(gzip.compress(json.dumps(nodes).encode())).decode()}
        selector = client.decode_region_selector({'value': value})
        class Fake:
            def send(self, *args): return {'ok': True, 'status': 'completed', 'region_selector': selector}
        with tempfile.TemporaryDirectory() as d:
            result = service.handle(Fake(), {'op': 'send', 'conversation': 'c', 'text': '创建地址'}, 'md', d)
            self.assertTrue(result['region_selection_required'])
            self.assertNotIn('region_selector_fragment_file', result)
            self.assertNotIn('region_selector_file', result)

    def test_region_lookup_checks_complete_parent_path(self):
        import region_lookup
        data = json.loads(region_lookup.DATA_PATH.read_text(encoding='utf8'))
        result = region_lookup.lookup({'environment': 'pre', 'op': 'resolve', 'names': ['北京市', '北京市', '东城区']}, data)
        self.assertEqual(result['ids'], ['11', '1101', '110101'])
        self.assertEqual(region_lookup.lookup({'environment': 'pre', 'op': 'resolve', 'ids': result['ids']}, data)['names'], result['names'])
        self.assertFalse(region_lookup.lookup({'environment': 'pre', 'op': 'resolve', 'ids': ['11', '1101', '999999']}, data)['ok'])
        self.assertIn('东城区', [x['name'] for x in region_lookup.lookup({'environment': 'pre', 'op': 'children', 'parent_id': '1101'}, data)['regions']])
        self.assertEqual(region_lookup.lookup({'op': 'children', 'parent_id': '0'}, data)['error'], 'ENVIRONMENT_MISMATCH')
        self.assertEqual(region_lookup.lookup({'environment': 'prod', 'op': 'children', 'parent_id': '0'}, data)['error'], 'ENVIRONMENT_MISMATCH')

    def test_no_public_response_propagated(self):
        class Fake:
            def resume(self, *args): return {'ok': False, 'status': 'completed', 'error': {'code': 'NO_PUBLIC_RESPONSE', 'message': '无结果'}}
        result = service.handle(Fake(), {'op': 'resume', 'conversation': 'c'}, 'md')
        self.assertEqual(result['error']['code'], 'NO_PUBLIC_RESPONSE')
        self.assertFalse(result['ok'])

    def test_invalid_format_before_send(self):
        class Fake:
            def send(self, *args): raise AssertionError('must not submit')
        with self.assertRaises(client.ClientError) as exc:
            service.handle(Fake(), {'op': 'send', 'conversation': 'c', 'text': 'x', 'format': 'bad'}, 'md')
        self.assertEqual(exc.exception.code, 'INVALID_FORMAT')

    def test_output_files_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = {'answer': 'first'}, {'answer': 'second'}
            service.write_outputs(a, {'conversation': 'c'}, d)
            service.write_outputs(b, {'conversation': 'c'}, d)
            self.assertNotEqual(a['answer_file'], b['answer_file'])
            self.assertEqual(Path(a['answer_file']).read_text(encoding='utf8'), 'first')

    def test_custom_output_paths(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            out = {'cards_html': '<div>卡</div>', 'answer': '正文'}
            request = {'conversation': 'c',
                       'out_dirs': {'fragment_path': str(root / 'vis' / 'cards.html'),
                                    'page_path': str(root / 'vis' / 'page.html'),
                                    'answer_path': str(root / 'vis' / 'answer.md')}}
            service.write_outputs(out, request, str(root / 'default'))
            self.assertEqual(Path(out['fragment_file']).read_text(encoding='utf8'), '<div>卡</div>')
            self.assertEqual(Path(out['answer_file']).read_text(encoding='utf8'), '正文')
            self.assertEqual(Path(out['fragment_file']), (root / 'vis' / 'cards.html').resolve())
            self.assertFalse((root / 'default').exists())
            again = {'cards_html': '<div>新</div>', 'answer': '新正文'}
            service.write_outputs(again, request, str(root / 'default'))
            self.assertEqual(Path(again['fragment_file']).read_text(encoding='utf8'), '<div>新</div>')

    def test_rejects_bad_output_paths(self):
        for bad in ({'out_dirs': {'fragment_path': ''}},
                    {'out_dirs': {'unknown': 'x'}},
                    {'out_dirs': ['x']},
                    {'page_path': '   '}):
            request = {'conversation': 'c', **bad}
            with self.assertRaises(service.ClientError) as ctx:
                service.handle(None, {'op': 'send', 'text': 'hi', **request}, 'widget')
            self.assertEqual(ctx.exception.code, 'INVALID_REQUEST')


    def test_payment_links_extracted_from_answer(self):
        answer = ('订单已提交，订单号 O1，状态待付款。\n'
                  '支付链接：https://pre-buyer.filtalgo.com/payment/cashier?orderSn=T1&paymentScene=TRADE\n'
                  '商品页：https://filtalgo.com/pages/goods/product/detail?goodsId=1\n'
                  '钱包：https://example.test/pay/1。')
        self.assertEqual(service.extract_payment_links(answer),
                         ['https://pre-buyer.filtalgo.com/payment/cashier?orderSn=T1&paymentScene=TRADE',
                          'https://example.test/pay/1'])
        self.assertEqual(service.extract_payment_links('订单已提交，待付款。'), [])

    def test_payment_links_in_payload(self):
        self.assertEqual(service.extract_payment_links(None), [])
        result = {'answer': {'value': {'content': '收银台：https://a.test/cashier?x=1'}}}
        payload = service.render(result, 'markdown', 0)
        links = service.extract_payment_links(payload['answer'])
        self.assertEqual(links, ['https://a.test/cashier?x=1'])


if __name__ == '__main__': unittest.main()
