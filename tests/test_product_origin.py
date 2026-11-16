import json
import os
import pathlib
import subprocess
import sys
import unittest


SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
RENDER = '''
import json, sys
sys.path.insert(0, sys.argv[1])
import service
result = {'context_documents': [{'kind': 'filtalgo.shopping.block:filtmall.product-card/v1',
    'value': {'block': {'schema': 'filtmall.product-card/v1', 'payload': {'product': {
        'goods_id': 'goods:1/中文?&', 'sku_id': 'sku:2/中文?&', 'title': '真实商品'}}}}}]}
outputs = {fmt: service.render(result, fmt, 0, True) for fmt in ('widget', 'html', 'md')}
for output in outputs.values():
    output.pop('_image_budget', None)
print(json.dumps(outputs))
'''


class ProductOrigin(unittest.TestCase):
    def render(self, origin):
        env = dict(os.environ)
        env.pop('FILTALGO_BUYER_MOBILE_ORIGIN', None)
        if origin is not None:
            env['FILTALGO_BUYER_MOBILE_ORIGIN'] = origin
        return subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c', RENDER, str(SCRIPTS)],
                              env=env, capture_output=True, text=True, encoding='utf8')

    def test_card_and_product_links_use_trusted_origin(self):
        for origin in (None, 'https://m.filtalgo.com', 'https://pre-m.filtalgo.com', 'https://dev-m.filtalgo.com'):
            with self.subTest(origin=origin):
                process = self.render(origin)
                self.assertEqual(process.returncode, 0, process.stderr)
                outputs = json.loads(process.stdout)
                url = (origin or 'https://m.filtalgo.com') + '/pages/goods/product/detail?goodsId=goods%3A1%2F%E4%B8%AD%E6%96%87%3F%26&skuId=sku%3A2%2F%E4%B8%AD%E6%96%87%3F%26'
                for fmt in ('widget', 'html'):
                    self.assertEqual(outputs[fmt]['widget_cards'][0]['url'], url)
                    self.assertEqual(outputs[fmt]['product_links'], [{'title': '真实商品', 'url': url}])
                self.assertIn('[查看商品](%s)' % url, outputs['md']['cards_markdown'])

    def test_invalid_origin_fails_without_product_output(self):
        for origin in ('', 'http://pre-m.filtalgo.com', 'https://evil.example',
                       'https://m.filtalgo.com.evil.example', 'https://user@m.filtalgo.com',
                       'https://m.filtalgo.com:443', 'https://m.filtalgo.com/',
                       'https://m.filtalgo.com/path', 'https://m.filtalgo.com?q=1',
                       'https://m.filtalgo.com#x', ' https://m.filtalgo.com',
                       'https://m.filtalgo.com\n', 'https://m.filtalgo.com\\evil'):
            with self.subTest(origin=origin):
                process = self.render(origin)
                self.assertNotEqual(process.returncode, 0)
                self.assertIn('FILTALGO_BUYER_MOBILE_ORIGIN', process.stderr)
                self.assertEqual(process.stdout, '')
