import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import client as c
import service


class FakeClient:
    def __init__(self, directory):
        self.store = c.Store(directory)


class CallLogTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = tmp.name

    def tearDown(self):
        os.environ.pop('FILTALGO_NO_LOG', None)

    def read(self):
        path = Path(self.directory) / 'calls.jsonl'
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line.strip()]

    def test_writes_one_line_with_expected_fields(self):
        payload = {'status': 'completed', 'card_count': 3, 'card_source': 'new'}
        service.record_call(FakeClient(self.directory), payload, 'workbuddy', 'request', 'html')
        lines = self.read()
        self.assertEqual(len(lines), 1)
        record = lines[0]
        self.assertEqual(record['host'], 'workbuddy')
        self.assertEqual(record['host_source'], 'request')
        self.assertEqual(record['format'], 'html')
        self.assertEqual(record['card_count'], 3)
        self.assertEqual(record['card_source'], 'new')
        self.assertEqual(record['status'], 'completed')
        self.assertIn('ts', record)
        self.assertNotIn('text', record)

    def test_card_source_defaults_to_none(self):
        service.record_call(FakeClient(self.directory), {'status': 'completed', 'card_count': 0}, 'today', 'state', 'md')
        self.assertEqual(self.read()[0]['card_source'], 'none')

    def test_error_code_recorded(self):
        payload = {'status': 'failed', 'error': {'code': 'NO_PUBLIC_RESPONSE'}}
        service.record_call(FakeClient(self.directory), payload, 'today', 'default', 'md')
        self.assertEqual(self.read()[0]['error_code'], 'NO_PUBLIC_RESPONSE')

    def test_appends_across_calls(self):
        client = FakeClient(self.directory)
        for host in ('today', 'doubao'):
            service.record_call(client, {'status': 'completed'}, host, 'request', 'md')
        self.assertEqual([row['host'] for row in self.read()], ['today', 'doubao'])

    def test_switch_disables_logging(self):
        os.environ['FILTALGO_NO_LOG'] = '1'
        service.record_call(FakeClient(self.directory), {'status': 'completed'}, 'today', 'request', 'md')
        self.assertEqual(self.read(), [])

    def test_client_without_store_is_ignored(self):
        service.record_call(object(), {'status': 'completed'}, 'today', 'request', 'md')
        self.assertEqual(self.read(), [])


class ClientIdentifierTests(unittest.TestCase):
    def test_identifier_format(self):
        self.assertEqual(c.Client.client_identifier('workbuddy'), 'filtalgo.skill.workbuddy')
        self.assertEqual(c.Client.client_identifier(''), 'filtalgo.skill.default')
        self.assertEqual(c.Client.client_identifier(None), 'filtalgo.skill.default')

    def test_identifier_constraints(self):
        value = c.Client.client_identifier('x' * 80)
        self.assertLessEqual(len(value), 64)
        self.assertRegex(value, r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')

    def test_identifier_strips_unsupported_characters(self):
        value = c.Client.client_identifier('豆包 工作!')
        self.assertRegex(value, r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')


if __name__ == '__main__':
    unittest.main()
