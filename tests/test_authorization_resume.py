import importlib.util
import json
import os
import sys
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('resume_client', SCRIPTS / 'client.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AuthorizationResumeTests(unittest.TestCase):
    def test_crash_after_challenge_save_leaves_one_recoverable_transition(self):
        writes = []
        now = time.time()
        def transport(method, path, body=None, token=None, headers=None):
            if path.endswith('/device'):
                return {'verification_uri_complete': 'https://buyer.example/code', 'exchange': 'fixture',
                        'expires_at': int((now + 120) * 1000), 'interval': 1}
            if path.endswith('/device/poll'):
                return self.completion()
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
                value = state['conversations']['a']; value.pop('authorization')
                value['pending'] = {'request_id': 'original', 'text': 'original text', 'mode': 'prompt', 'start_revision': 4}
                api.store.save(state)
            original_save = api.store.save
            def crash_after_save(state):
                original_save(state)
                if state['conversations']['a'].get('authorization'):
                    raise SystemExit('synthetic process exit immediately after atomic save')
            with patch.object(api.store, 'save', side_effect=crash_after_save), self.assertRaises(SystemExit):
                api.start_authorization('a', {'request_id': 'original', 'revision': 5,
                    'value': {'id': 'challenge', 'state': 'state-secret', 'provider': 'filtmall'}})
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

    def test_legacy_overlap_recovers_with_new_identity_before_reading_original_request(self):
        writes = []
        def transport(method, path, body=None, token=None, headers=None):
            if path.endswith('/device/poll'):
                return self.completion()
            self.assertEqual(token, 'new-platform-access')
            if path.endswith('/inputs/original/result'):
                return {'execution_result': {'operation_status': 'waiting'}}
            if 'after_revision=' in path:
                return {'revision': 9, 'next_cursor': None, 'documents': [{
                    'document_id': 'challenge-document', 'kind': 'filtalgo.commerce.authorization',
                    'schema_version': 1, 'request_id': 'original', 'revision': 5,
                    'value': {'id': 'challenge', 'state': 'state-secret'}}]}
            if '/documents?' in path:
                return {'revision': 9}
            if method == 'GET':
                raise module.ClientError('HTTP_404', 'not submitted')
            if path.endswith('/inputs'):
                writes.append(body); return {'status': 'accepted'}
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

    def test_crash_after_legacy_completion_identity_save_does_not_poll_or_need_guest_proof_again(self):
        def transport(method, path, body=None, token=None, headers=None):
            self.assertNotIn('/device/poll', path)
            self.assertNotIn('/completion', path)
            self.assertEqual(token, 'new-platform-access')
            if path.endswith('/inputs/original/result'):
                return {'execution_result': {'operation_status': 'waiting'}}
            if 'after_revision=' in path:
                return {'revision': 9, 'documents': [{'document_id': 'proof', 'kind': 'filtalgo.commerce.authorization',
                    'schema_version': 1, 'request_id': 'original', 'revision': 5,
                    'value': {'id': 'challenge', 'state': 'state-secret'}}]}
            if '/documents?' in path:
                return {'revision': 9}
            if method == 'GET':
                raise module.ClientError('HTTP_404', 'not submitted')
            return {'status': 'accepted'}
        with tempfile.TemporaryDirectory() as directory:
            api = self.setup_client(directory, transport)
            with api.store.locked() as state:
                state['conversations']['a']['pending'] = {'request_id': 'original', 'text': 'original', 'mode': 'prompt', 'start_revision': 4}
                api.store.save(state)
            save = api.store.save
            def crash(state):
                save(state)
                raise SystemExit('synthetic exit after identity and verified completion save')
            with patch.object(api.store, 'save', side_effect=crash), self.assertRaises(SystemExit):
                api.finish_authorization('a', 'challenge', self.completion())
            reopened = module.Client('https://control.example', 'agent', module.Store(directory), transport=transport)
            reopened.wait = lambda *a, **k: {'status': 'completed'}
            self.assertEqual(reopened.resume('a', timeout=0)['status'], 'completed')
            self.assertEqual(reopened.conversation('a')['delegation_id'], 'delegation')

    def test_legacy_overlap_does_not_discard_unrelated_pending_input(self):
        for bound, status in [(None, 'completed'), ('another-request', 'waiting')]:
            with self.subTest(bound=bound), tempfile.TemporaryDirectory() as directory:
                api = self.setup_client(directory, lambda method, path, body=None, **kwargs: self.completion() if path.endswith('/device/poll')
                                        else {'execution_result': {'operation_status': status}})
                pending = {'request_id': 'original', 'text': 'must remain', 'mode': 'prompt', 'start_revision': 4}
                with api.store.locked() as state:
                    value = state['conversations']['a']; value['pending'] = pending
                    if bound is not None: value['authorization']['for_request_id'] = bound
                    api.store.save(state)
                with self.assertRaises(module.ClientError) as error:
                    api.resume('a', timeout=0)
                self.assertEqual(error.exception.code, 'AUTHORIZATION_UNCERTAIN')
                self.assertEqual(api.conversation('a')['pending'], pending)
                self.assertIn('authorization', api.conversation('a'))

    def setup_client(self, directory, transport):
        store = module.Store(directory)
        api = module.Client('https://control.example', 'agent', store, transport=transport)
        with store.locked() as state:
            state['auth'] = {'access_token': 'old-platform-access', 'refresh_token': 'old-platform-refresh', 'access_expires_at': int(time.time() * 1000) + 60000}
            state['conversations']['a'] = {'id': 'session', 'last_request_id': 'original', 'last_start_revision': 4,
                'authorization': {'id': 'challenge', 'state': 'state-secret', 'exchange': 'exchange-secret',
                    'expires_at': int(time.time() * 1000) + 60000, 'url': 'https://buyer.example/code'}}
            store.save(state)
        return api

    @staticmethod
    def completion():
        return {'status': 'active', 'id': 'delegation', 'platform_tokens': {
            'access_token': 'new-platform-access', 'refresh_token': 'new-platform-refresh',
            'access_expires_at': int(time.time() * 1000) + 60000,
            'refresh_expires_at': int(time.time() * 1000) + 3600000,
            'principal_id': 'member-principal', 'credential_session_id': 'credential',
        }}

    def test_resume_saves_platform_tokens_then_submits_one_stable_continuation(self):
        calls = []
        def transport(method, path, body=None, token=None, headers=None):
            calls.append((method, path, body, token))
            if path.endswith('/device/poll'):
                return self.completion()
            if '/documents?' in path:
                return {'revision': 9, 'items': []}
            if method == 'GET':
                raise module.ClientError('HTTP_404', 'not yet submitted')
            if path.endswith('/inputs'):
                self.assertEqual(token, 'new-platform-access')
                return {'status': 'accepted'}
            self.fail(path)
        with tempfile.TemporaryDirectory() as directory:
            api = self.setup_client(directory, transport)
            api.wait = lambda key, timeout, **kwargs: {'status': 'completed'}
            self.assertEqual(api.resume('a')['status'], 'completed')
            submitted = [call for call in calls if call[1].endswith('/inputs')]
            self.assertEqual(len(submitted), 1)
            continuation = submitted[0][2]
            self.assertNotEqual(continuation['request_id'], 'original')
            self.assertNotIn('state-secret', json.dumps(continuation))
            self.assertNotIn('exchange-secret', json.dumps(continuation))
            saved = json.loads(api.store.path.read_text())
            self.assertEqual(saved['auth']['refresh_token'], 'new-platform-refresh')
            self.assertEqual(saved['conversations']['a']['pending']['start_revision'], 9)
            if os.name != 'nt':
                self.assertEqual(api.store.path.stat().st_mode & 0o777, 0o600)

    def test_lost_merge_response_recovers_using_original_proof_without_new_guest(self):
        calls = []
        def transport(method, path, body=None, token=None, headers=None):
            calls.append(path)
            if path.endswith('/device/poll'):
                raise module.ClientError('HTTP_401', 'original guest merged')
            if path.endswith('/completion'):
                self.assertEqual(token, 'old-platform-access')
                self.assertEqual(body, {'state': 'state-secret'})
                return self.completion()
            if '/documents?' in path:
                return {'revision': 9}
            if method == 'GET':
                raise module.ClientError('HTTP_404', 'not submitted')
            if path.endswith('/inputs'):
                return {'status': 'accepted'}
            self.fail(path)
        with tempfile.TemporaryDirectory() as directory:
            api = self.setup_client(directory, transport)
            api.wait = lambda *a, **k: {'status': 'completed'}
            self.assertEqual(api.resume('a')['status'], 'completed')
            self.assertEqual(len([p for p in calls if p.endswith('/completion')]), 1)
            self.assertFalse(any('/guests' in p for p in calls))

    def test_unknown_continuation_response_keeps_exact_id_and_payload_for_resume(self):
        writes = []
        def transport(method, path, body=None, token=None, headers=None):
            if path.endswith('/device/poll'):
                return self.completion()
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

    def test_malformed_platform_tokens_do_not_clear_authorization_or_replace_identity(self):
        result = self.completion()
        result['platform_tokens']['access_expires_at'] = True
        with tempfile.TemporaryDirectory() as directory:
            api = self.setup_client(directory, lambda *a, **k: result)
            with self.assertRaises(module.ClientError):
                api.complete_authorization('a')
            saved = json.loads(api.store.path.read_text())
            self.assertEqual(saved['auth']['access_token'], 'old-platform-access')
            self.assertIn('authorization', saved['conversations']['a'])

    def test_logout_failure_preserves_identity_and_conversations(self):
        def transport(*args, **kwargs):
            raise module.ClientError('HTTP_503', 'unavailable')
        with tempfile.TemporaryDirectory() as directory:
            api = self.setup_client(directory, transport)
            with self.assertRaises(module.ClientError):
                api.logout('a')
            saved = json.loads(api.store.path.read_text())
            self.assertEqual(saved['auth']['access_token'], 'old-platform-access')
            self.assertIn('a', saved['conversations'])

    def test_merged_guest_in_refresh_window_uses_original_proof_for_receipt(self):
        calls = []
        def transport(method, path, body=None, token=None, headers=None):
            calls.append(path)
            if path.endswith('/tokens:refresh'):
                raise module.ClientError('HTTP_401', 'guest merged')
            if path.endswith('/completion'):
                self.assertEqual(token, 'old-platform-access')
                return self.completion()
            if '/documents?' in path:
                return {'revision': 9}
            if method == 'GET':
                raise module.ClientError('HTTP_404', 'not submitted')
            if path.endswith('/inputs'):
                return {'status': 'accepted'}
            self.fail(path)
        with tempfile.TemporaryDirectory() as directory:
            api = self.setup_client(directory, transport)
            with api.store.locked() as state:
                state['auth']['access_expires_at'] = int(time.time() * 1000) + 10000
                api.store.save(state)
            api.wait = lambda *a, **k: {'status': 'completed'}
            self.assertEqual(api.resume('a')['status'], 'completed')
            self.assertEqual(calls.count('/api/v2/identity/tokens:refresh'), 1)
            self.assertEqual(len([p for p in calls if p.endswith('/completion')]), 1)
            self.assertFalse(any('/guests' in p for p in calls))

    def test_repoll_identity_expiry_also_recovers_and_saves_new_tokens(self):
        def transport(method, path, body=None, token=None, headers=None):
            self.assertTrue(path.endswith('/completion'))
            return self.completion()
        with tempfile.TemporaryDirectory() as directory:
            api = self.setup_client(directory, transport)
            api.api = lambda *a, **k: (_ for _ in ()).throw(module.ClientError('IDENTITY_EXPIRED', 'merged'))
            pending = api.conversation('a')['authorization']
            with patch.object(module.time, 'sleep'):
                self.assertTrue(api.poll_granted(pending, time.monotonic() + 10, key='a'))
            saved = json.loads(api.store.path.read_text())
            self.assertEqual(saved['auth']['access_token'], 'new-platform-access')
            self.assertTrue(saved['conversations']['a']['pending']['authorization_resume'])

    def test_logout_revokes_current_platform_session_before_dropping_local_state(self):
        calls = []
        def transport(method, path, body=None, token=None, headers=None):
            calls.append((method, path, token))
        with tempfile.TemporaryDirectory() as directory:
            api = self.setup_client(directory, transport)
            self.assertEqual(api.logout('a')['status'], 'logged_out')
            saved = json.loads(api.store.path.read_text())
            self.assertIsNone(saved['auth'])
            self.assertEqual(saved['conversations'], {})
        self.assertEqual(calls, [('POST', '/api/v2/identity/logout', 'old-platform-access')])

    def test_unlink_only_revokes_saved_delegation_and_preserves_platform_identity(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            api = self.setup_client(directory, lambda *a, **k: calls.append((a, k)))
            with api.store.locked() as state:
                state['conversations']['a']['delegation_id'] = 'saved-delegation'
                api.store.save(state)
            self.assertEqual(api.revoke_authorization('a')['status'], 'authorization_revoked')
            saved = json.loads(api.store.path.read_text())
            self.assertEqual(saved['auth']['access_token'], 'old-platform-access')
            self.assertNotIn('delegation_id', saved['conversations']['a'])
            self.assertEqual(calls[0][0][:2], ('DELETE', '/api/v2/delegations/saved-delegation'))


if __name__ == '__main__':
    unittest.main()
