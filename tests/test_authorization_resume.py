import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('resume_client', SCRIPTS / 'client.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def challenge_doc(session_id='session', doc_id='challenge', request_id='original', revision=5):
    base = f'/api/v2/sessions/{session_id}/oauth/filtmall'
    return {
        'document_id': doc_id,
        'kind': 'oauth_challenge',
        'schema_version': 1,
        'request_id': request_id,
        'revision': revision,
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


class AuthorizationResumeTests(unittest.TestCase):
    def setup_client(self, directory, transport):
        store = module.Store(directory)
        api = module.Client('https://control.example', 'agent', store, transport=transport)
        base = '/api/v2/sessions/session/oauth/filtmall'
        with store.locked() as state:
            state['auth'] = {
                'access_token': 'platform-access',
                'refresh_token': 'platform-refresh',
                'access_expires_at': int(time.time() * 1000) + 60000,
            }
            state['conversations']['a'] = {
                'id': 'session',
                'last_request_id': 'original',
                'last_start_revision': 4,
                'authorization': {
                    'id': 'challenge',
                    'provider_id': 'filtmall',
                    'device_path': base + '/device',
                    'poll_path': base + '/device/poll',
                    'revoke_path': base,
                    'exchange': 'exchange-secret',
                    'expires_at': int(time.time() * 1000) + 60000,
                    'url': 'https://buyer.example/code',
                },
            }
            store.save(state)
        return api

    def test_crash_after_challenge_save_leaves_one_recoverable_transition(self):
        writes = []
        now = time.time()

        def transport(method, path, body=None, token=None, headers=None):
            if path.endswith('/device'):
                return {
                    'verification_uri_complete': 'https://buyer.example/code',
                    'exchange': 'fixture',
                    'expires_at': int((now + 120) * 1000),
                    'interval': 1,
                }
            if path.endswith('/device/poll'):
                return {'status': 'active'}
            if '/documents?' in path:
                return {'revision': 9}
            if method == 'GET':
                raise module.ClientError('HTTP_404', 'not submitted')
            if path.endswith('/inputs'):
                writes.append(body)
                return {'status': 'accepted'}
            self.fail(path)

        with tempfile.TemporaryDirectory() as directory:
            api = self.setup_client(directory, transport)
            with api.store.locked() as state:
                value = state['conversations']['a']
                value.pop('authorization')
                value['pending'] = {'request_id': 'original', 'text': 'original text', 'mode': 'prompt', 'start_revision': 4}
                api.store.save(state)
            original_save = api.store.save

            def crash_after_save(state):
                original_save(state)
                if state['conversations']['a'].get('authorization'):
                    raise SystemExit('synthetic process exit immediately after atomic save')

            with patch.object(api.store, 'save', side_effect=crash_after_save), self.assertRaises(SystemExit):
                api.start_authorization('a', challenge_doc())
            reopened = module.Client('https://control.example', 'agent', module.Store(directory), transport=transport)
            saved = reopened.conversation('a')
            self.assertNotIn('pending', saved)
            self.assertEqual(saved['authorization']['for_request_id'], 'original')
            self.assertEqual(saved['last_request_id'], 'original')
            reopened.wait = lambda *a, **k: {'status': 'completed'}
            with patch.object(module.time, 'time', return_value=now + 5):
                self.assertEqual(reopened.resume('a', timeout=0)['status'], 'completed')
            self.assertEqual(len(writes), 1)
            self.assertNotEqual(writes[0]['request_id'], 'original')

    def test_overlap_reconciles_matching_waiting_challenge_and_rejects_unrelated_pending(self):
        writes = []

        def transport(method, path, body=None, token=None, headers=None):
            if path.endswith('/device/poll'):
                return {'status': 'active'}
            if path.endswith('/inputs/original/result'):
                return {'execution_result': {'operation_status': 'waiting'}}
            if 'after_revision=' in path:
                return {'revision': 9, 'next_cursor': None, 'documents': [challenge_doc()]}
            if '/documents?' in path:
                return {'revision': 9}
            if method == 'GET':
                raise module.ClientError('HTTP_404', 'not submitted')
            if path.endswith('/inputs'):
                writes.append(body)
                return {'status': 'accepted'}
            self.fail(path)

        with tempfile.TemporaryDirectory() as directory:
            api = self.setup_client(directory, transport)
            with api.store.locked() as state:
                state['conversations']['a']['pending'] = {'request_id': 'original', 'text': 'original', 'mode': 'prompt', 'start_revision': 4}
                api.store.save(state)
            api.wait = lambda *a, **k: {'status': 'completed'}
            self.assertEqual(api.resume('a', timeout=0)['status'], 'completed')
            self.assertEqual(len(writes), 1)
            self.assertNotIn('authorization', api.conversation('a'))
            self.assertEqual(api.conversation('a')['pending']['authorization_for_request_id'], 'original')

        for bound, status in [(None, 'completed'), ('another-request', 'waiting')]:
            with self.subTest(bound=bound), tempfile.TemporaryDirectory() as directory:
                api = self.setup_client(
                    directory,
                    lambda method, path, body=None, **kwargs: {'status': 'active'} if path.endswith('/device/poll') else {'execution_result': {'operation_status': status}},
                )
                pending = {'request_id': 'original', 'text': 'must remain', 'mode': 'prompt', 'start_revision': 4}
                with api.store.locked() as state:
                    value = state['conversations']['a']
                    value['pending'] = pending
                    if bound is not None:
                        value['authorization']['for_request_id'] = bound
                    api.store.save(state)
                with self.assertRaises(module.ClientError) as error:
                    api.resume('a', timeout=0)
                self.assertEqual(error.exception.code, 'AUTHORIZATION_UNCERTAIN')
                self.assertEqual(api.conversation('a')['pending'], pending)
                self.assertIn('authorization', api.conversation('a'))

    def test_unknown_continuation_response_keeps_exact_id_and_payload_for_resume(self):
        writes = []

        def transport(method, path, body=None, token=None, headers=None):
            if path.endswith('/device/poll'):
                return {'status': 'active'}
            if '/documents?' in path:
                return {'revision': 9}
            if method == 'GET':
                raise module.ClientError('HTTP_404', 'not submitted')
            if path.endswith('/inputs'):
                writes.append(dict(body))
                if len(writes) == 1:
                    raise module.ClientError('RESULT_UNKNOWN', 'lost reply')
                return {'status': 'accepted'}
            self.fail(path)

        with tempfile.TemporaryDirectory() as directory:
            api = self.setup_client(directory, transport)
            api.wait = lambda *a, **k: {'status': 'completed'}
            with self.assertRaises(module.ClientError):
                api.resume('a')
            api.resume('a')
            self.assertEqual(len(writes), 2)
            self.assertEqual(writes[0], writes[1])
            self.assertNotIn('exchange-secret', json.dumps(writes[0]))
            if os.name != 'nt':
                self.assertEqual(api.store.path.stat().st_mode & 0o777, 0o600)

    def test_logout_and_revoke_preserve_platform_invariants(self):
        with tempfile.TemporaryDirectory() as directory:
            api = self.setup_client(directory, lambda *a, **k: (_ for _ in ()).throw(module.ClientError('HTTP_503', 'unavailable')))
            with self.assertRaises(module.ClientError):
                api.logout('a')
            saved = json.loads(api.store.path.read_text())
            self.assertEqual(saved['auth']['access_token'], 'platform-access')

        calls = []
        with tempfile.TemporaryDirectory() as directory:
            api = self.setup_client(directory, lambda *a, **k: calls.append((a, k)))
            with api.store.locked() as state:
                state['conversations']['a']['oauth_revoke_path'] = '/api/v2/sessions/session/oauth/filtmall'
                api.store.save(state)
            self.assertEqual(api.revoke_authorization('a')['status'], 'authorization_revoked')
            saved = json.loads(api.store.path.read_text())
            self.assertEqual(saved['auth']['access_token'], 'platform-access')
            self.assertNotIn('oauth_revoke_path', saved['conversations']['a'])
            self.assertEqual(calls[0][0][:2], ('DELETE', '/api/v2/sessions/session/oauth/filtmall'))

            calls.clear()
            self.assertEqual(api.logout('a')['status'], 'logged_out')
            saved = json.loads(api.store.path.read_text())
            self.assertIsNone(saved['auth'])
            self.assertEqual(saved['conversations'], {})
            self.assertEqual(calls[0][0][:2], ('POST', '/api/v2/identity/logout'))


if __name__ == '__main__':
    unittest.main()
