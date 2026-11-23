import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import client as c
import hosts
import service


class Stub:
    """最小 Client 替身：只提供 host 记忆能力。"""

    def __init__(self, saved=None):
        self.saved = saved
        self.remembered = []

    def locked_host(self, key):
        return self.saved

    def remember_host(self, key, host):
        self.remembered.append(host)
        self.saved = host


class NormalizeTests(unittest.TestCase):
    def test_enum_and_aliases(self):
        for value, expected in (
            ('workbuddy', 'workbuddy'),
            ('WorkBuddy', 'workbuddy'),
            ('  豆包工作  ', 'doubao'),
            ('豆包', 'doubao'),
            ('千问办公', 'qianwen'),
            ('灵光', 'lingguang'),
            ('Today', 'today'),
            ('default', 'default'),
        ):
            self.assertEqual(hosts.normalize(value), expected, value)

    def test_unknown_falls_back_to_none(self):
        for value in ('unknown-host', '', '  ', None, 42, 'chrome'):
            self.assertIsNone(hosts.normalize(value), repr(value))

    def test_profile_formats(self):
        self.assertEqual(hosts.profile('workbuddy')['format'], 'html')
        self.assertEqual(hosts.profile('doubao')['format'], 'md')
        self.assertEqual(hosts.profile('not-exist')['format'], 'md')
        self.assertEqual(hosts.profile('workbuddy')['cards'], 'required')


class ResolveHostTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop('FILTALGO_HOST', None)

    def test_request_wins_and_is_remembered(self):
        stub = Stub()
        host, source, _ = service.resolve_host({'host': '豆包工作'}, stub, 'c1')
        self.assertEqual((host, source), ('doubao', 'request'))
        self.assertEqual(stub.remembered, ['doubao'])

    def test_state_lock_overrides_request(self):
        stub = Stub(saved='today')
        host, source, _ = service.resolve_host({'host': 'workbuddy'}, stub, 'c1')
        self.assertEqual((host, source), ('today', 'state'))
        self.assertEqual(stub.remembered, [])

    def test_env_used_when_request_missing(self):
        os.environ['FILTALGO_HOST'] = 'lingguang'
        stub = Stub()
        host, source, _ = service.resolve_host({}, stub, 'c1')
        self.assertEqual((host, source), ('lingguang', 'env'))

    def test_default_when_nothing_known(self):
        stub = Stub()
        host, source, _ = service.resolve_host({}, stub, 'c1')
        self.assertEqual((host, source), ('default', 'default'))
        self.assertEqual(stub.remembered, [])

    def test_invalid_request_value_degrades_to_default(self):
        stub = Stub()
        host, source, raw = service.resolve_host({'host': 'safari'}, stub, 'c1')
        self.assertEqual((host, source), ('default', 'default'))
        self.assertEqual(raw, 'safari')


class HostStateTests(unittest.TestCase):
    def test_remember_and_lock_persist_across_clients(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        first = c.Client('https://control.test', 'agent', c.Store(tmp.name))
        self.assertIsNone(first.locked_host('conv'))
        first.remember_host('conv', 'workbuddy')
        self.assertEqual(first.locked_host('conv'), 'workbuddy')
        second = c.Client('https://control.test', 'agent', c.Store(tmp.name))
        self.assertEqual(second.locked_host('conv'), 'workbuddy')

    def test_remember_does_not_override(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        client = c.Client('https://control.test', 'agent', c.Store(tmp.name))
        client.remember_host('conv', 'today')
        client.remember_host('conv', 'workbuddy')
        self.assertEqual(client.locked_host('conv'), 'today')

    def test_conversation_state_untouched(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = c.Store(tmp.name)
        client = c.Client('https://control.test', 'agent', store)
        client.remember_host('conv', 'doubao')
        with store.locked() as state:
            self.assertEqual(state.get('hosts'), {'conv': 'doubao'})
            self.assertNotIn('conv', state.get('conversations', {}))


if __name__ == '__main__':
    unittest.main()
