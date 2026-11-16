import copy
import pathlib
import sys
import time
import unittest
import tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import customer_service_cards as cards
import client
import service


def fixture(scene='general'):
    q = dict(scene=scene, store_id='store', goods_id='goods', sku_id=None, order_sn='order', after_sale_sn='after')
    e = dict(q, store_name='<店铺>', default_channel='mobile_h5', channels={'pc_web': {'url': 'https://buyer.example/chat?a=1&b=2'}, 'mobile_h5': {'url': 'https://buyer.example/mobile'}})
    e['sku_id'] = ''
    return dict(status='current', query=q, fetched_at=1, reason=None, entry=e, authorization_binding='a'*64, authorization_expires_at=int(time.time()*1000)+60000, link_origins=['https://buyer.example'])


class CustomerService(unittest.TestCase):
    def test_public_no_body_files(self):
        for fmt in ('md', 'widget', 'html'):
            with tempfile.TemporaryDirectory() as directory:
                class API:
                    def send(self, *args):
                        return {'ok': True, 'status': 'completed', 'customer_service_snapshots': [fixture()]}
                output = service.handle(API(), {'op': 'send', 'conversation': 'c', 'text': '客服'}, fmt, directory)
                self.assertEqual(output['customer_service_count'], 1)
                content = pathlib.Path(output['customer_service_file']).read_text(encoding='utf8')
                self.assertNotIn('authorization_binding', content)
                self.assertIn('https://buyer.example/mobile', content)

    def test_actual_settle_latest_and_request_isolation(self):
        for invalid in ('version', 'expiry', 'key', 'failure'):
            with tempfile.TemporaryDirectory() as directory:
                store = client.Store(directory)
                value = {'id': 'session', 'pending': {'request_id': 'r', 'start_revision': 40}}
                other = {'id': 'other'}
                with store.locked() as state:
                    state['conversations'] = {'conversation': copy.deepcopy(value), 'other': copy.deepcopy(other)}
                    store.save(state)
                api = client.Client('https://test', 'a', store)
                doc = dict(kind='filtalgo.commerce.customer_service', schema_version=1, revision=41, request_id='r', value=fixture())
                latest = copy.deepcopy(doc); latest['revision'] = 42
                if invalid == 'version': latest['schema_version'] = 2
                if invalid == 'expiry': latest['value']['authorization_expires_at'] = 1
                if invalid == 'key': latest['value']['query'] = None
                if invalid == 'failure': latest['value'] = dict(cards.unavailable(reason='query_failed'), query=fixture()['query'])
                foreign = copy.deepcopy(doc); foreign.update(request_id='foreign', revision=99)
                api.documents = lambda *args: [doc, latest, foreign]
                result = api.settle('conversation', value, 'completed')
                self.assertEqual(result['customer_service_snapshots'][0]['status'], 'unavailable')
                with store.locked() as state:
                    self.assertEqual(state['conversations']['other'], other)
                    self.assertNotIn('pending', state['conversations']['conversation'])

    def test_scenes_formats(self):
        for scene in cards.SCENES:
            for fmt in ('md', 'widget', 'html'):
                v = fixture(scene)
                self.assertTrue(cards.validate(v))
                status, count, content = cards.render([v], fmt)
                self.assertEqual((status, count), ('current', 1))
                self.assertLess(content.index('https://buyer.example/mobile'), content.index('https://buyer.example/chat'))
                self.assertNotIn('authorization_binding', content)
                self.assertNotIn('<店铺>', content)

    def test_rejections(self):
        for url in ('http://buyer.example/', 'https://evil.example/', 'https://u:p@buyer.example/', 'https://buyer.example/#x', 'https://buyer.example/?token=x', 'https://buyer.example/?a=%zz', 'https://buyer.example/\\evil'):
            v = fixture(); v['entry']['channels']['pc_web']['url'] = url
            self.assertFalse(cards.validate(v), url)
        v = fixture(); v['authorization_expires_at'] = 1
        self.assertFalse(cards.validate(v))
        v = fixture(); v['entry']['store_id'] = 'other'
        self.assertFalse(cards.validate(v))
        self.assertEqual(cards.render([cards.unavailable(reason='no_entry')])[1], 0)

    def test_deduplicate(self):
        v = fixture(); v['entry']['channels']['pc_web'] = copy.deepcopy(v['entry']['channels']['mobile_h5'])
        self.assertEqual(cards.render([v], 'widget')[2].count('<a '), 1)

    def test_shared_card_layout_and_primary_action(self):
        content = cards.render([fixture('order')], 'widget')[2]
        self.assertIn('class="fm-service-card"', content)
        self.assertIn('border:1px solid var(--fm-line)', content)
        self.assertIn('订单客服</h2>', content)
        self.assertIn('关联订单</dt>', content)
        self.assertIn('class="fm-primary"', content)
        self.assertIn('>联系客服</a>', content)
        self.assertIn('>电脑页面入口</a>', content)
        self.assertNotIn('store_id：', content)
        self.assertNotIn('<script', content)

    def test_internal_product_identifiers_are_not_displayed(self):
        value = fixture('product')
        for key, identifier in (('store_id', 'INTERNAL-STORE-9281'), ('goods_id', 'INTERNAL-GOODS-7462'), ('sku_id', 'INTERNAL-SKU-5320')):
            value['query'][key] = value['entry'][key] = identifier
        original = copy.deepcopy(value)
        for fmt in ('md', 'widget', 'html'):
            status, count, content = cards.render([value], fmt)
            self.assertEqual((status, count), ('current', 1))
            for key in ('store_id', 'goods_id', 'sku_id'):
                self.assertNotIn(value['entry'][key], content)
            for label in ('店铺编号', '商品编号', '规格编号'):
                self.assertNotIn(label, content)
            self.assertIn('https://buyer.example/mobile', content)
            self.assertIn('关联订单', content)
        self.assertEqual(value, original)

    def test_malformed_json_values_fail_closed(self):
        for key in ('scene', 'store_id', 'goods_id', 'sku_id', 'order_sn', 'after_sale_sn'):
            for bad in ([], {}, True, 3):
                v = fixture(); v['query'][key] = bad
                self.assertFalse(cards.validate(v))
                self.assertEqual(cards.render([v])[0], 'unavailable')
        for key in ('status', 'reason', 'entry', 'link_origins', 'publication'):
            v = fixture(); v[key] = {'bad': []}
            self.assertFalse(cards.validate(v))

    def test_url_origin_and_percent_parity(self):
        v = fixture(); v['entry']['channels']['pc_web']['url'] = 'https://BUYER.example:443/chat?a=1'
        self.assertTrue(cards.validate(v))
        for url in ('https://buyer.example/%zz', 'https://buyer.example/%', 'https://%62uyer.example/chat'):
            v['entry']['channels']['pc_web']['url'] = url
            self.assertFalse(cards.validate(v))
        self.assertFalse(cards.safe_url('https://faß.de/chat', ['https://fass.de']))

if __name__ == '__main__': unittest.main()
