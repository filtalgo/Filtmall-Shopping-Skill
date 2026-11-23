import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import link_response as links
import service

SOURCE = 'https://m.filtalgo.com/pages/goods/product/detail?goodsId=1&skuId=2'
RESOLVED = {'h5_url': 'https://m.filtalgo.com/h5/open?id=1', 'mp_url': 'https://wxmpurl.cn/example'}
MARKDOWN = '[查看商品](' + SOURCE + ')'


class LinkResponseTests(unittest.TestCase):
    def test_shared_cache_and_repeat(self):
        calls = []
        def resolve(url):
            calls.append(url)
            return RESOLVED
        payload = {'display_content': MARKDOWN, 'answer': MARKDOWN}
        links.finalize_payload(payload, resolve)
        self.assertEqual(calls, [SOURCE])
        self.assertEqual(payload['display_content'], payload['answer'])
        self.assertIn('[手机端](https://wxmpurl.cn/example)', payload['display_content'])
        self.assertIn('[电脑端](https://m.filtalgo.com/h5/open?id=1)', payload['display_content'])
        first = dict(payload)
        links.finalize_payload(payload, resolve)
        self.assertEqual(payload, first)
        self.assertEqual(calls, [SOURCE])

    def test_exclusions(self):
        text = ('!'+MARKDOWN + '\n`'+MARKDOWN+'`\n```md\n'+MARKDOWN+'\n```\n'
                '[授权](https://m.filtalgo.com/pages/oauth/device/?code=1)\n'
                '[授权](https://m.filtalgo.com/oauth/device)\n'
                '[预发](https://pre-m.filtalgo.com/path)\n'
                '[伪域名](https://m.filtalgo.com.evil/path)')
        def fail(url):
            self.fail('Unexpected resolver call: ' + url)
        self.assertEqual(links.rewrite_markdown(text, fail), text)

    def test_mixed_finalized_and_new_links(self):
        first = links.rewrite_markdown(MARKDOWN, lambda _: RESOLVED)
        calls = []
        result = links.rewrite_markdown(first + '\n' + MARKDOWN,
                                       lambda url: calls.append(url) or RESOLVED)
        self.assertEqual(result, first + '\n' + first)
        self.assertEqual(calls, [SOURCE])

    def test_fallback_and_limit(self):
        for value in (None, {'h5_url': SOURCE, 'mp_url': 'https://evil.com/x'}):
            self.assertEqual(links.rewrite_markdown(MARKDOWN, lambda _: value), MARKDOWN)
        def fail(_):
            raise OSError('offline')
        self.assertEqual(links.rewrite_markdown(MARKDOWN, fail), MARKDOWN)
        calls = []
        text = '\n'.join('[商品](https://m.filtalgo.com/item?id=%d)' % n for n in range(11))
        links.rewrite_markdown(text, lambda url: calls.append(url))
        self.assertEqual(len(calls), 10)

    def test_service_artifacts_keep_product_and_html(self):
        payload = service.render({'answer': {'value': {'content': '商品 A · ¥99\n'+MARKDOWN}}}, 'html', 0)
        payload['cart_content'] = '<a href="'+SOURCE+'">商品</a>'
        original_html = payload['cart_content']
        links.finalize_payload(payload, lambda _: RESOLVED)
        self.assertIn('商品 A · ¥99', payload['display_content'])
        self.assertIn(RESOLVED['mp_url'], payload['display_content'])
        self.assertEqual(payload['cart_content'], original_html)

    def test_gateway_contract_without_credentials(self):
        captured = []
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                req = captured[0]
                body = json.loads(req.data)
                return json.dumps({'jsonrpc': '2.0', 'id': body['id'], 'result': {
                    'content': [{'type': 'text', 'text': json.dumps(RESOLVED)}]}}).encode()
        class Opener:
            def open(self, req, timeout):
                captured.append(req)
                return Response()
        with patch.object(links, 'build_opener', return_value=Opener()):
            self.assertEqual(links.resolve_url(SOURCE), RESOLVED)
        req = captured[0]
        self.assertEqual(req.full_url, 'https://filtalgo.com/gateway/mcp')
        self.assertNotIn('Authorization', req.headers)
        body = json.loads(req.data)
        self.assertEqual(body['params']['arguments'], {'url': SOURCE})
        self.assertEqual(body['params']['name'], 'shopping.navigation.resolve_url_link')


if __name__ == '__main__':
    unittest.main()
