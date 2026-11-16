import copy
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import client
import service
import logistics_cards


def snapshot():
    return {'status': 'current', 'query': {'order_sn': 'O-test', 'package_no': None, 'include_items': True, 'include_traces': True},
            'fetched_at': int(time.time()*1000), 'empty_reason': None, 'reason': None,
            'authorization_binding': 'ab'*32, 'authorization_expires_at': int(time.time()*1000)+600000,
            'packages': [{'package_no': 'P-test', 'logistics_name': '示例快递', 'logistics_no': 'TEST001',
                          'logistics_time': '2026-11-09 12:00', 'items': [{'goods_name': '<防晒>', 'sku_name': '50g', 'deliver_number': 1}],
                          'trace_status': 'available', 'trace_order': 'source', 'traces': [
                              {'time': '', 'description': '完整节点'+str(i), 'location': '', 'status': '', 'occurred_at': None} for i in range(12)]}]}


class LogisticsOutputs(unittest.TestCase):
    def test_payload_limit_uses_compact_utf8_json_without_raising_the_limit(self):
        for target, expected in ((260000, True), (256*1024+1, False)):
            with self.subTest(bytes=target):
                data = snapshot()
                nodes = [{'time': '', 'occurred_at': None, 'description': '', 'location': '', 'status': ''}
                         for _ in range(1000)]
                data['packages'][0]['traces'] = nodes
                compact_size = lambda: len(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf8'))
                length, remainder = divmod(target-compact_size(), len(nodes))
                for index, node in enumerate(nodes):
                    node['description'] = 'x'*(length+(index < remainder))
                self.assertEqual(compact_size(), target)
                self.assertGreater(len(json.dumps(data, ensure_ascii=False).encode('utf8')), 256*1024)
                self.assertEqual(logistics_cards.validate(data), expected)

    def test_readable_dates_hide_available_badge_and_query_hint(self):
        data = snapshot()
        data['fetched_at'] = logistics_cards.timestamp('2026-11-10T20:24:05+08:00')
        pkg = data['packages'][0]
        pkg.update(logistics_time='2026-11-10T19:30:00+08:00', trace_order='time_desc')
        pkg['traces'] = [{'time': '2026-11-10T19:45:00+08:00', 'occurred_at': logistics_cards.timestamp('2026-11-10T19:45:00+08:00'),
                          'description': '模拟签收', 'location': '示例收货点', 'status': '模拟事件'}]
        before = copy.deepcopy(data)
        for fmt in ('widget', 'html', 'md'):
            with self.subTest(format=fmt):
                status, count, content = logistics_cards.render([data], fmt)
                visible = content.replace('\\-', '-')
                self.assertEqual((status, count), ('current', 1))
                self.assertIn('2026-11-10 19:45', visible)
                self.assertIn('发货时间：2026-11-10 19:30', visible)
                self.assertIn('查询时间：2026-11-10 20:24', visible)
                self.assertNotIn('已有物流轨迹', content)
                self.assertNotIn('非轨迹发生时间', content)
                self.assertNotIn('T19:45', content)
                self.assertNotIn('+08:00', content)
                self.assertIn('状态：模拟事件', content)
        self.assertEqual(data, before)

    def test_time_presentation_preserves_instants_local_wall_clock_and_unknown_values(self):
        cases = [('2026-11-10T11:45:00Z', '2026-11-10 19:45'),
                 ('2026-11-10T06:45:00-05:00', '2026-11-10 19:45'),
                 ('2026-11-10T23:45:59.123-05:00', '2026-11-11 12:45'),
                 ('2026-11-10 19:45:59', '2026-11-10 19:45'),
                 ('2026-11-10T19:45:00+02:60', '2026-11-10T19:45:00+02:60'),
                 ('时间待核实', '时间待核实'), ('2026-11-10', '2026-11-10')]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                data = snapshot()
                data['packages'][0]['trace_order'] = 'time_desc' if logistics_cards.timestamp(raw) is not None else 'source'
                data['packages'][0]['traces'] = [{'time': raw, 'occurred_at': logistics_cards.timestamp(raw),
                                                  'description': '节点', 'location': '', 'status': ''}]
                _, _, content = logistics_cards.render([data], 'widget')
                self.assertIn('>' + expected + '</p>', content)

    def test_public_entry_writes_logistics_when_the_response_has_no_text(self):
        for fmt in ('widget', 'html', 'md'):
            for data in (snapshot(), logistics_cards.unavailable(reason='query_failed')):
                with self.subTest(format=fmt, status=data['status']), tempfile.TemporaryDirectory() as directory:
                    class API:
                        def send(self, *args):
                            return {'ok': True, 'status': 'completed', 'logistics_snapshots': [data]}
                    output = service.handle(API(), {'op': 'send', 'conversation': 'c', 'text': '查看物流'}, fmt, directory)
                    self.assertEqual(output.get('logistics_status'), data['status'])
                    self.assertEqual(output.get('logistics_count'), 1 if data['status'] == 'current' else 0)
                    content = Path(output['logistics_file']).read_text(encoding='utf8')
                    self.assertIn('完整节点11' if data['status'] == 'current' else '物流信息暂不可用', content)

    def test_settlement_updates_only_the_original_conversation_after_logistics(self):
        for order in ('O-test', 'other-conversation', None):
            with self.subTest(order=order), tempfile.TemporaryDirectory() as directory:
                store = client.Store(directory)
                value = {'id': 'session-c', 'pending': {'request_id': 'r', 'start_revision': 40}, 'last_error': 'TIMEOUT_WAITING'}
                other = {'id': 'session-other', 'pending': {'request_id': 'r', 'start_revision': 30}}
                with store.locked() as state:
                    state['conversations'] = {'conversation-c': copy.deepcopy(value), 'other-conversation': copy.deepcopy(other)}
                    store.save(state)
                api = client.Client('https://test', 'a', store)
                data = snapshot() if order is not None else logistics_cards.unavailable()
                if order is not None:
                    data['query']['order_sn'] = order
                api.documents = lambda *a: [{'kind': 'filtalgo.commerce.logistics', 'schema_version': 1,
                                              'revision': 41, 'request_id': 'r', 'value': data}]
                result = api.settle('conversation-c', value, 'completed')
                self.assertEqual(result['status'], 'completed')
                with store.locked() as state:
                    current = state['conversations']['conversation-c']
                    self.assertNotIn('pending', current)
                    self.assertNotIn('last_error', current)
                    self.assertEqual(current['last_status'], 'completed')
                    self.assertEqual(current['last_request_id'], 'r')
                    self.assertEqual(current['last_start_revision'], 40)
                    self.assertEqual(state['conversations']['other-conversation'], other)

    def test_missing_contract_fields_never_crash_validation_render_or_settlement(self):
        for field in ('query', 'fetched_at', 'empty_reason', 'reason', 'packages'):
            data = snapshot(); del data[field]
            self.assertFalse(logistics_cards.validate(data))
            self.assertEqual(logistics_cards.render([data], 'widget')[:2], ('unavailable', 0))
        self.assertFalse(logistics_cards.validate({'status': 'unavailable', 'packages': []}))

    def test_invalid_timezone_preserves_nodes_and_does_not_guess_a_comparable_time(self):
        for zone in ('+02:60', '+24:00', '-00:99'):
            data = snapshot()
            data['packages'][0]['traces'][0]['time'] = '2026-11-10T10:00:00' + zone
            self.assertIsNone(logistics_cards.timestamp(data['packages'][0]['traces'][0]['time']))
            status, count, content = logistics_cards.render([data], 'widget')
            self.assertEqual((status, count), ('current', 1))
            self.assertIn('完整节点11', content)

    def test_order_and_tracking_identifiers_are_not_treated_as_phone_numbers(self):
        data = snapshot(); data['query']['order_sn'] = 'O13812345678'
        data['packages'][0]['logistics_no'] = '13812345678'
        content = logistics_cards.render([data], 'widget')[2]
        self.assertIn('O13812345678', content)
        self.assertIn('13812345678', content)

    def test_all_nodes_three_formats_and_private_output_paths(self):
        for fmt in ('widget', 'html', 'md'):
            data = snapshot(); before = copy.deepcopy(data)
            with tempfile.TemporaryDirectory() as directory:
                out = service.render({'logistics_snapshots': [data]}, fmt, 0)
                service.write_outputs(out, {'conversation': 'c'}, directory)
                self.assertEqual(out['logistics_count'], 1)
                self.assertEqual(out['logistics_status'], 'current')
                content = Path(out['logistics_file']).read_text(encoding='utf8')
                for i in range(12): self.assertIn('完整节点'+str(i), content)
                self.assertIn('时间顺序待核实', content)
                self.assertNotIn('最新动态', content)
                for private in ('ab'*32, 'authorization_', 'publication', '<button', '<script', '<防晒>'):
                    self.assertNotIn(private, content)
                self.assertEqual(content.startswith('<!doctype html>'), fmt == 'html')
                if fmt == 'md': self.assertTrue(out['logistics_file'].endswith('.logistics.md'))
                else: self.assertEqual(out['logistics_'+('page' if fmt == 'html' else 'fragment')+'_file'], out['logistics_file'])
            self.assertEqual(data, before)

    def test_client_uses_only_latest_same_request_order_and_never_falls_back_from_unknown_version(self):
        with tempfile.TemporaryDirectory() as directory:
            api = client.Client('https://test', 'a', client.Store(directory))
            def doc(rev, value, req='r', version=1):
                return {'kind': 'filtalgo.commerce.logistics', 'schema_version': version, 'revision': rev, 'request_id': req, 'value': value}
            api.documents = lambda *a: [doc(39, snapshot()), doc(41, snapshot()), doc(42, snapshot(), version=2), doc(43, snapshot(), req='other')]
            result = api.settle('c', {'id': 's', 'pending': {'request_id': 'r', 'start_revision': 40}}, 'completed')
            self.assertEqual(result['logistics_snapshots'][0]['status'], 'unavailable')
            self.assertNotIn('TEST001', str(result['logistics_snapshots']))

    def test_expired_or_invalid_result_cannot_render_stale_packages(self):
        for mutate in (lambda x: x.update(authorization_expires_at=1),
                       lambda x: x['packages'].append(x['packages'][0]),
                       lambda x: x['packages'][0]['items'][0].update(deliver_number=True)):
            data = snapshot(); mutate(data)
            status, count, content = logistics_cards.render([data], 'widget')
            self.assertEqual((status, count), ('unavailable', 0))
            self.assertNotIn('TEST001', content)

    def test_empty_filter_and_not_requested_are_distinct(self):
        data = snapshot(); data.update(packages=[], empty_reason='no_packages')
        self.assertIn('暂无包裹信息', logistics_cards.render([data], 'md')[2])
        data['query']['package_no'] = 'P-none'; data['empty_reason'] = 'package_not_found'
        self.assertIn('未找到指定包裹', logistics_cards.render([data], 'md')[2])
        data = snapshot(); data['query']['include_traces'] = False
        data['packages'][0].update(trace_status='not_requested', traces=[])
        self.assertIn('本次未查询物流轨迹', logistics_cards.render([data], 'md')[2])


if __name__ == '__main__': unittest.main()
