import sys
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import service
import client

BINDING = 'a1' * 32


def snapshot(scene='address_book', way=None):
    return {'status': 'current', 'scene': scene, 'way': way,
            'selection_status': 'not_applicable' if scene == 'address_book' else 'known',
            'selected_address_id': None if scene == 'address_book' else 'second',
            'authorization_binding': BINDING, 'authorization_expires_at': int(time.time()*1000)+60000,
            'page': {'number': 1, 'has_more': None}, 'items': [
                {'address_id': 'first', 'recipient_name': '<姓名> [一]', 'mobile_display': '138****1234',
                 'region_path': '浙江省,杭州市,西湖区', 'detail': '详细门牌' * 200, 'is_default': True},
                {'address_id': 'second', 'recipient_name': '二', 'mobile_display': '139****5678',
                 'region_path': '上海市,上海市,浦东新区', 'detail': '示例路2号', 'is_default': False}]}


class AddressTests(unittest.TestCase):
    def test_shared_international_phone_corpus_in_all_fields_and_formats(self):
        cases = json.loads((Path(__file__).parent / 'fixtures/phone-privacy.json').read_text())
        for case in cases:
            for field in ('recipient_name', 'region_path', 'detail'):
                for fmt in ('md', 'html', 'widget'):
                    with self.subTest(case=case, field=field, fmt=fmt):
                        data = snapshot(); data['items'][0][field] = case['input']
                        expected = 'current' if case['input'] == case['redacted'] else 'unavailable'
                        self.assertEqual(self.render(data, fmt)['address_status'], expected)
                        data['items'][0][field] = case['redacted']
                        self.assertEqual(self.render(data, fmt)['address_status'], 'current')

    def render(self, value, fmt='md'):
        return service.render({'address_snapshots': [value]}, fmt, 0)

    def test_formats_private_files_and_independent_labels(self):
        for fmt in ('widget', 'html', 'md'):
            with self.subTest(fmt=fmt), tempfile.TemporaryDirectory() as directory:
                out = self.render(snapshot('checkout', 'delivery'), fmt)
                service.write_outputs(out, {'conversation': 'c'}, directory)
                self.assertEqual(out['address_status'], 'current')
                text = Path(out['address_file']).read_text(encoding='utf8')
                self.assertIn('默认地址', text)
                self.assertIn('本次已选中', text)
                self.assertIn('详细门牌' * 200, text)
                self.assertIn('&lt;姓名&gt;', text)
                for private in (BINDING, 'address_id', '<姓名>', '<script', '<button', '<input', 'callback'):
                    self.assertNotIn(private, text)
                if fmt == 'md':
                    self.assertTrue(out['address_file'].endswith('.addresses.md'))
                    self.assertIn('\\[一\\]', text)
                else:
                    self.assertIn('overflow-wrap:anywhere', text)
                    self.assertEqual(out['address_fragment_file' if fmt == 'widget' else 'address_page_file'], out['address_file'])
                    self.assertEqual(text.startswith('<!doctype html>'), fmt == 'html')

    def test_invalid_fields_fail_closed_without_private_content(self):
        changes = [('status', 'bad'), ('scene', 'bad'), ('way', 'bad'), ('selection_status', 'known'),
                   ('selected_address_id', 'first'), ('authorization_binding', ''), ('authorization_expires_at', 0),
                   ('page', {'number': True, 'has_more': None}), ('items', snapshot()['items'] * 2)]
        for key, value in changes:
            with self.subTest(key=key):
                data = snapshot(); data[key] = value
                out = self.render(data)
                self.assertEqual(out['address_status'], 'unavailable')
                self.assertNotIn('138', out['address_content'])
        for key, value in [('mobile_display', '13812341234'), ('recipient_name', ''), ('is_default', 1), ('detail', None)]:
            data = snapshot(); data['items'][0][key] = value
            self.assertEqual(self.render(data)['address_status'], 'unavailable')

    def test_free_text_phone_formats_never_reach_output(self):
        for field in ('recipient_name', 'region_path', 'detail'):
            for phone in ('13812345678', '138 1234 5678', '138-1234-5678', '138.1234.5678', '138\u00a01234\u00a05678', '138\u30001234\u30005678',
                          '１３８１２３４５６７８', '１３８ １２３４ ５６７８', '1３8１２3４5６7８', '١٣٨١٢٣٤٥٦٧٨', '𝟙𝟛𝟠𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠', '138\u202f1234\u202f5678'):
                for fmt in ('md', 'html', 'widget'):
                    with self.subTest(field=field, phone=phone, fmt=fmt):
                        data = snapshot()
                        data['items'][0][field] = '测试 ' + phone
                        out = self.render(data, fmt)
                        self.assertEqual(out['address_status'], 'unavailable')
                        self.assertNotIn(phone, out['address_content'])

    def test_states_pagination_and_selected_outside_page(self):
        for state in ('unavailable', 'authorization_required'):
            data = snapshot(); data.update(status=state, items=[])
            self.assertEqual(self.render(data)['address_status'], state)
            data['items'] = snapshot()['items']
            self.assertEqual(self.render(data)['address_status'], 'unavailable')
        data = snapshot('checkout', 'delivery'); data['selected_address_id'] = 'outside'
        self.assertIn('本页未列出', self.render(data)['address_content'])
        data = snapshot(); data['items'] = []
        self.assertIn('本页没有地址', self.render(data)['address_content'])
        data['page']['has_more'] = False
        self.assertIn('暂无收货地址', self.render(data)['address_content'])

    def test_address_only_handle_custom_path_and_default_unique(self):
        class Stub:
            def send(self, *args): return {'ok': True, 'status': 'completed', 'address_snapshots': [snapshot()]}
        with tempfile.TemporaryDirectory() as directory:
            req = {'op': 'send', 'conversation': 'c', 'text': '地址'}
            one = service.handle(Stub(), req, 'md', directory)
            two = service.handle(Stub(), req, 'md', directory)
            self.assertNotEqual(one['address_file'], two['address_file'])
            dest = str(Path(directory) / 'custom.md')
            for override in ({'address_path': dest}, {'out_dirs': {'address_path': dest}}):
                out = service.handle(Stub(), dict(req, **override), 'md', directory)
                self.assertEqual(out['address_file'], dest)

    def test_client_per_scene_revision_request_version_and_address_only(self):
        with tempfile.TemporaryDirectory() as directory:
            api = client.Client('https://test', 'a', client.Store(directory))
            def doc(revision, value, request='r', version=1):
                return {'kind': 'filtalgo.commerce.addresses', 'schema_version': version, 'request_id': request,
                        'revision': revision, 'value': value}
            status = {'kind': 'request.status', 'schema_version': 1, 'request_id': 'r', 'value': {'answer_document_id': None}}
            unavailable = dict(snapshot(), status='unavailable', items=[])
            api.documents = lambda *a: [status, doc(39, snapshot()), doc(41, snapshot()), doc(42, unavailable),
                doc(43, snapshot('checkout', 'delivery')), doc(44, snapshot('checkout', 'pickup')),
                doc(45, snapshot(), 'other'), doc(46, snapshot('checkout', 'delivery'), version=3)]
            result = api.settle('c', {'id': 's', 'pending': {'request_id': 'r', 'start_revision': 40}}, 'completed')
            self.assertTrue(result['ok'])
            self.assertEqual(len(result['address_snapshots']), 3)
            self.assertEqual([s['status'] for s in result['address_snapshots']], ['unavailable', 'unavailable', 'current'])
            self.assertNotIn(BINDING, str(result['address_snapshots'][:2]))

    def test_client_accepts_v2_with_provenance_without_rendering_internal_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            api = client.Client('https://test', 'a', client.Store(directory))
            data = snapshot(); data['publication'] = {'task_id': '123', 'call_id': 'call-v2'}
            api.documents = lambda *a: [{'kind': 'filtalgo.commerce.addresses', 'schema_version': 2,
                'request_id': 'r', 'revision': 41, 'value': data}]
            result = api.settle('c', {'id': 's', 'pending': {'request_id': 'r', 'start_revision': 40}}, 'completed')
            self.assertEqual(result['address_snapshots'][0]['status'], 'current')
            out = service.render(result, 'html', 0)
            self.assertNotIn('call-v2', out['address_content'])
            self.assertNotIn('publication', out['address_content'])

    def test_client_rejects_old_unmatched_and_missing_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            api = client.Client('https://test', 'a', client.Store(directory))
            for revision, request, baseline in ((39, 'r', 40), (41, None, 40), (41, 'other', 40), (41, 'r', None)):
                api.documents = lambda *a: [{'kind': 'filtalgo.commerce.addresses', 'schema_version': 1,
                    'request_id': request, 'revision': revision, 'value': snapshot()}]
                result = api.settle('c', {'id': 's', 'pending': {'request_id': 'r', 'start_revision': baseline}}, 'completed')
                self.assertNotIn('address_snapshots', result)
                self.assertEqual(result['error']['code'], 'NO_PUBLIC_RESPONSE')

    def test_mixed_products_cart_addresses_and_scene_labels(self):
        data = snapshot('checkout', 'delivery')
        for fmt in ('widget', 'html', 'md'):
            with tempfile.TemporaryDirectory() as directory, patch.object(service.cards, 'collect', return_value=[
                    {'title': '推荐商品', 'rank': 1, 'price': '1', 'url': None, 'thumbnail': ''}]):
                out = service.render({'address_snapshots': [snapshot(), data],
                    'cart': {'status': 'current', 'items': []}}, fmt, 0)
                service.write_outputs(out, {'conversation': 'c'}, directory)
                self.assertIn('html_file', out); self.assertIn('cart_file', out)
                content = Path(out['address_file']).read_text(encoding='utf8')
                self.assertEqual(content.count('本次已选中'), 1)
                self.assertEqual(content.count('默认地址'), 1)

    def test_all_required_fields_and_selection_are_validated(self):
        for field in snapshot():
            data = snapshot(); del data[field]
            self.assertEqual(self.render(data)['address_status'], 'unavailable', field)
        for changes in ({'selection_status': 'unknown', 'selected_address_id': 'first'},
                        {'selection_status': 'not_applicable'}, {'way': None},
                        {'way': 'x'*65}, {'authorization_expires_at': float('inf')}):
            data = snapshot('checkout', 'delivery'); data.update(changes)
            self.assertEqual(self.render(data)['address_status'], 'unavailable')
        data = snapshot('checkout', 'delivery'); data.update(selection_status='unknown', selected_address_id=None)
        out = self.render(data)
        self.assertEqual(out['address_status'], 'current')
        self.assertNotIn('本次已选中', out['address_content'])
        data['items'][0]['detail'] = '原文手机号13812341234'
        self.assertEqual(self.render(data)['address_status'], 'unavailable')

    def test_binding_requires_exact_lowercase_hex64(self):
        for binding in ('private-binding', 'a'*63, 'a'*65, 'g'*64, 'A'*64, 'a'*64+'\n', 123, None):
            with self.subTest(binding=binding):
                data = snapshot(); data['authorization_binding'] = binding
                out = self.render(data)
                self.assertEqual(out['address_status'], 'unavailable')
                self.assertNotIn('138', out['address_content'])
        self.assertEqual(self.render(snapshot())['address_status'], 'current')

    def test_huge_expiry_fails_closed_and_preserves_mixed_outputs(self):
        data = snapshot(); data['authorization_expires_at'] = 10**400
        for fmt in ('widget', 'html', 'md'):
            with tempfile.TemporaryDirectory() as directory, patch.object(service.cards, 'collect', return_value=[
                    {'title': '推荐商品', 'rank': 1, 'price': '1', 'url': None, 'thumbnail': ''}]):
                out = service.render({'address_snapshots': [data], 'cart': {'status': 'current', 'items': []}}, fmt, 0)
                service.write_outputs(out, {'conversation': 'c'}, directory)
                self.assertEqual(out['address_status'], 'unavailable')
                self.assertEqual(out['cart_status'], 'current')
                self.assertIn('推荐商品', Path(out['html_file']).read_text(encoding='utf8'))
                self.assertNotIn('138', Path(out['address_file']).read_text(encoding='utf8'))

    def test_latest_boolean_float_version_and_huge_expiry_never_reuse_old_address(self):
        with tempfile.TemporaryDirectory() as directory:
            api = client.Client('https://test', 'a', client.Store(directory))
            for version, expiry in ((True, int(time.time()*1000)+60000), (1.0, int(time.time()*1000)+60000), (1, 10**400)):
                with self.subTest(version=version, expiry=expiry):
                    def doc(revision, schema, data):
                        return {'kind': 'filtalgo.commerce.addresses', 'schema_version': schema,
                            'request_id': 'r', 'revision': revision, 'value': data}
                    data = snapshot(); data['authorization_expires_at'] = expiry
                    api.documents = lambda *a: [doc(41, 1, snapshot()), doc(42, version, data)]
                    result = api.settle('c', {'id': 's', 'pending': {'request_id': 'r', 'start_revision': 40}}, 'completed')
                    self.assertTrue(result['ok'])
                    self.assertEqual(result['address_snapshots'][0]['status'], 'unavailable')
                    self.assertNotIn('138', str(result['address_snapshots']))


if __name__ == '__main__': unittest.main()
