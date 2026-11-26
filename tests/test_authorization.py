import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('client', SCRIPTS / 'client.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def challenge_doc(session_id='session', doc_id='doc-oauth-1', request_id=None, revision=4):
    base = f'/api/v2/sessions/{session_id}/oauth/filtmall'
    return {
        'document_id': doc_id,
        'kind': 'oauth_challenge',
        'schema_version': 1,
        'revision': revision,
        'request_id': request_id,
        'value': {
            'provider_id': 'filtmall',
            'tool_name': 'address_list',
            'scopes': ['address:read'],
            'authorize_path': base + '/authorize',
            'complete_path': base + '/complete',
            'device_path': base + '/device',
            'poll_path': base + '/device/poll',
            'revoke_path': base,
        },
    }


def pending_record(session_id='session', expires_offset_ms=60000, **extra):
    base = f'/api/v2/sessions/{session_id}/oauth/filtmall'
    return {
        'id': 'doc-oauth-1',
        'provider_id': 'filtmall',
        'device_path': base + '/device',
        'poll_path': base + '/device/poll',
        'revoke_path': base,
        'exchange': 'sealed',
        'url': 'https://buyer.example/code',
        'interval': 2,
        'expires_at': int(time.time() * 1000) + expires_offset_ms,
        **extra,
    }


class AuthorizationTests(unittest.TestCase):
    def test_repoll_respects_server_slow_down_interval(self):
        for payload in ({'status': 'slow_down', 'interval': 7}, {'status': 'slow_down'}):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as directory:
                client = module.Client('https://control.example', 'agent', module.Store(directory))
                pending = pending_record()
                clock, waits, polls = [0], [], []

                def sleep(seconds):
                    waits.append(seconds)
                    clock[0] += seconds

                def api(method, path, body=None):
                    polls.append(1)
                    return payload if len(polls) == 1 else {'status': 'active'}

                client.api = api
                with patch.object(module.time, 'sleep', side_effect=sleep), patch.object(module.time, 'monotonic', side_effect=lambda: clock[0]):
                    self.assertTrue(client.poll_granted(pending, 20))
                self.assertEqual(waits, [2, 7])
                self.assertEqual(pending['interval'], 7)

    def test_resume_reuses_link_without_starting_again(self):
        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            client = module.Client('https://control.example', 'agent', store)
            with store.locked() as state:
                state['conversations']['a'] = {'id': 'session', 'authorization': pending_record(next_poll_at=int(time.time() * 1000) + 30000)}
                store.save(state)
            client.api = lambda *args, **kwargs: self.fail('must not call device endpoint')
            self.assertEqual(client.resume('a')['authorization_url'], 'https://buyer.example/code')

    def test_parallel_start_reuses_one_device_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            client = module.Client('https://control.example', 'agent', store)
            with store.locked() as state:
                state['conversations']['a'] = {'id': 'session'}
                store.save(state)
            calls, results = [], []

            def api(*args, **kwargs):
                calls.append(1)
                time.sleep(0.05)
                return {'verification_uri_complete': 'https://buyer.example/code', 'exchange': 'secret', 'expires_at': int(time.time() * 1000) + 60000}

            client.api = api
            doc = challenge_doc()
            threads = [threading.Thread(target=lambda: results.append(client.start_authorization('a', doc))) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]['authorization_url'], results[1]['authorization_url'])

    def test_terminal_poll_errors_clear_authorization_while_transient_errors_preserve_it(self):
        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            client = module.Client('https://control.example', 'agent', store)
            with store.locked() as state:
                state['conversations']['a'] = {'id': 'session', 'authorization': pending_record()}
                store.save(state)
            client.api = lambda *args, **kwargs: (_ for _ in ()).throw(module.ClientError('HTTP_503', 'unavailable'))
            with self.assertRaises(module.ClientError):
                client.complete_authorization('a')
            self.assertIn('authorization', client.conversation('a'))

            client.api = lambda *args, **kwargs: (_ for _ in ()).throw(module.ClientError('HTTP_403', 'denied'))
            with self.assertRaises(module.ClientError) as err:
                client.complete_authorization('a')
            self.assertEqual(err.exception.code, 'AUTHORIZATION_FAILED')
            self.assertNotIn('authorization', client.conversation('a'))

    def test_other_user_cannot_read_pending_link(self):
        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            owner = module.Client('https://control.example', 'agent', store, user_key='owner')
            other = module.Client('https://control.example', 'agent', store, user_key='other')
            with store.locked() as state:
                state['target'] = {'origin': owner.origin, 'agent_id': owner.agent_id, 'subject': owner.subject}
                state['conversations']['a'] = {'id': 'session', 'authorization': pending_record(next_poll_at=int(time.time() * 1000) + 5000)}
                store.save(state)
            with self.assertRaises(module.ClientError) as error:
                other.complete_authorization('a')
            self.assertEqual(error.exception.code, 'STATE_TARGET_MISMATCH')

    def test_rejects_insecure_verification_link_and_mismatched_session_path(self):
        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            client = module.Client('https://control.example', 'agent', store)
            with store.locked() as state:
                state['conversations']['a'] = {'id': 'session'}
                store.save(state)
            client.api = lambda *args, **kwargs: {'verification_uri_complete': 'http://attacker.example/', 'exchange': 'secret', 'expires_at': int(time.time() * 1000) + 60000}
            with self.assertRaises(module.ClientError):
                client.start_authorization('a', challenge_doc())
            with self.assertRaises(module.ClientError):
                client.start_authorization('a', challenge_doc(session_id='other-session'))
            self.assertNotIn('authorization', client.conversation('a'))

    def test_expired_authorization_rechecks_if_polled_else_clears_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            client = module.Client('https://control.example', 'agent', store)
            with store.locked() as state:
                state['conversations']['a'] = {'id': 'session', 'authorization': pending_record(expires_offset_ms=-1000)}
                store.save(state)
            with self.assertRaises(module.ClientError) as error:
                client.complete_authorization('a')
            self.assertEqual(error.exception.code, 'AUTHORIZATION_EXPIRED')
            self.assertNotIn('authorization', client.conversation('a'))

    def test_v3_oauth_challenge_device_flow_and_revoke(self):
        calls = []

        def transport(method, path, body=None, token=None, headers=None):
            calls.append((method, path, body))
            if path == '/api/v2/sessions/ses-1/oauth/filtmall/device':
                return {
                    'verification_uri_complete': 'https://m.filtalgo.com/pages/oauth/device?user_code=ABCD-EFGH',
                    'user_code': 'ABCD-EFGH',
                    'exchange': 'sealed-v3-exchange',
                    'expires_at': int(time.time() * 1000) + 60000,
                    'interval': 3,
                }
            if path == '/api/v2/sessions/ses-1/oauth/filtmall/device/poll':
                poll_count = sum(1 for _, p, _ in calls if p.endswith('/device/poll'))
                return {'status': 'active' if poll_count >= 2 else 'authorization_pending', 'interval': 3}
            if method == 'DELETE' and path == '/api/v2/sessions/ses-1/oauth/filtmall':
                return None
            raise AssertionError((method, path))

        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            client = module.Client('https://control.example', 'agent', store, transport=transport)
            with store.locked() as state:
                state['auth'] = {'access_token': 'plat-jwt', 'refresh_token': 'plat-rt', 'access_expires_at': int(time.time() * 1000) + 60000}
                state['conversations']['a'] = {'id': 'ses-1', 'pending': {'request_id': 'req-1', 'start_revision': 2}}
                store.save(state)
            client.result = lambda value: {'execution_result': {'operation_status': 'waiting'}}
            client.documents = lambda session, request_id, *args: [challenge_doc(session_id='ses-1', request_id='req-1', revision=3)]
            waited = client.wait('a', 1)
            self.assertEqual(waited['status'], 'authorization_required')
            self.assertNotIn('sealed-v3-exchange', str(waited))

            with store.locked() as state:
                state['conversations']['a']['authorization']['next_poll_at'] = 0
                store.save(state)
            self.assertEqual(client.complete_authorization('a')['status'], 'authorization_required')

            with store.locked() as state:
                state['conversations']['a']['authorization']['next_poll_at'] = 0
                store.save(state)
            self.assertIsNone(client.complete_authorization('a'))
            conv = client.conversation('a')
            self.assertNotIn('authorization', conv)
            self.assertEqual(conv['oauth_revoke_path'], '/api/v2/sessions/ses-1/oauth/filtmall')
            self.assertTrue(conv['pending']['authorization_resume'])

            revoked = client.revoke_authorization('a')
            self.assertEqual(revoked['status'], 'authorization_revoked')
            self.assertNotIn('oauth_revoke_path', client.conversation('a'))


if __name__ == '__main__':
    unittest.main()
