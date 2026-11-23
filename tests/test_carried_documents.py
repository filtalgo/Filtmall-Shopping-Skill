import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import client as c


def block(document_id, request_id, revision, order=0, title='商品'):
    return {
        'document_id': document_id,
        'kind': 'filtalgo.shopping.block:filtmall.product-card/v1',
        'schema_version': 1,
        'request_id': request_id,
        'revision': revision,
        'display_order': order,
        'value': {'block': {'payload': {'title': title, 'price': 9.9}}},
    }


class CarriedTests(unittest.TestCase):
    def make(self, documents):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        api = c.Client('https://control.test', 'agent', c.Store(tmp.name))
        api.documents = lambda session_id, request_id, after_revision=None: list(documents)
        return api

    def test_returns_latest_group(self):
        api = self.make([
            block('a1', 'old', 11), block('a2', 'old', 13),
            block('b1', 'new', 21), block('b2', 'new', 22),
        ])
        result = api.carried_product_documents('s', 'r', 30)
        self.assertEqual([d['document_id'] for d in result], ['b1', 'b2'])

    def test_excludes_documents_after_baseline(self):
        api = self.make([block('a1', 'old', 5), block('a2', 'old', 40)])
        self.assertEqual([d['document_id'] for d in api.carried_product_documents('s', 'r', 10)], ['a1'])

    def test_limits_members(self):
        api = self.make([block('a%d' % i, 'old', 10 + i, order=i) for i in range(8)])
        self.assertEqual(len(api.carried_product_documents('s', 'r', 30)), 5)

    def test_ignores_non_product_blocks(self):
        api = self.make([{'document_id': 'x', 'kind': 'filtalgo.shopping.text', 'revision': 3, 'request_id': 'old'}])
        self.assertEqual(api.carried_product_documents('s', 'r', 10), [])

    def test_ignores_documents_without_request_id(self):
        item = block('a1', 'old', 5)
        item['request_id'] = None
        api = self.make([item])
        self.assertEqual(api.carried_product_documents('s', 'r', 10), [])

    def test_bad_baseline_returns_empty(self):
        api = self.make([block('a1', 'old', 5)])
        self.assertEqual(api.carried_product_documents('s', 'r', None), [])

    def test_documents_failure_is_silent(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        api = c.Client('https://control.test', 'agent', c.Store(tmp.name))

        def boom(*args, **kwargs):
            raise c.ClientError('INVALID_CURSOR', 'x')

        api.documents = boom
        self.assertEqual(api.carried_product_documents('s', 'r', 10), [])


if __name__ == '__main__':
    unittest.main()
