import importlib.util
import tempfile
import time
import threading
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('client', Path(__file__).parents[1] / 'scripts/client.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AuthorizationTests(unittest.TestCase):
    def test_resume_reuses_link_without_starting_again(self):
        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            client = module.Client('https://control.example', 'agent', store)
            with store.locked() as state:
                state['conversations']['a'] = {'id': 'session', 'authorization': {'url': 'https://buyer.example/code', 'expires_at': int(time.time() * 1000) + 60000}}
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
            doc = {'value': {'id': 'request', 'provider': 'filtmall', 'state': 'state'}}
            threads = [threading.Thread(target=lambda: results.append(client.start_authorization('a', doc))) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]['authorization_url'], results[1]['authorization_url'])

    def test_uncertain_authorization_is_preserved_until_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            client = module.Client('https://control.example', 'agent', store)
            with store.locked() as state:
                state['conversations']['a'] = {'id': 'session', 'authorization': {'id': 'req', 'state': 'state', 'exchange': 'sealed', 'url': 'https://buyer.example/', 'expires_at': int(time.time() * 1000) + 60000}}
                store.save(state)
            def api(method, path, body=None, headers=None):
                if method == 'POST': raise module.ClientError('HTTP_409', 'denied')
                return {'status': 'pending'}
            client.api = api
            with self.assertRaises(module.ClientError): client.complete_authorization('a')
            self.assertIn('authorization', client.conversation('a'))
            client.reset_authorization('a')
            self.assertNotIn('authorization', client.conversation('a'))

    def test_incomplete_authorization_status_preserves_exchange(self):
        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            client = module.Client('https://control.example', 'agent', store)
            with store.locked() as state:
                state['conversations']['a'] = {'id': 'session', 'authorization': {'id': 'req', 'state': 'state', 'exchange': 'sealed', 'url': 'https://buyer.example/', 'expires_at': int(time.time() * 1000) + 60000}}
                store.save(state)
            def api(method, path, body=None, headers=None):
                if method == 'POST': raise module.ClientError('HTTP_409', 'conflict')
                return {}
            client.api = api
            with self.assertRaises(module.ClientError) as error: client.complete_authorization('a')
            self.assertEqual(error.exception.code, 'AUTHORIZATION_UNCERTAIN')
            self.assertIn('authorization', client.conversation('a'))

    def test_completed_exchange_recovers_after_unknown_response(self):
        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            client = module.Client('https://control.example', 'agent', store)
            with store.locked() as state:
                state['conversations']['a'] = {'id': 'session', 'authorization': {'id': 'req', 'state': 'state', 'exchange': 'sealed', 'url': 'https://buyer.example/', 'expires_at': int(time.time() * 1000) + 60000}}
                store.save(state)
            def api(method, path, body=None, headers=None):
                if method == 'POST':
                    raise module.ClientError('HTTP_409', 'already consumed')
                return {'status': 'completed', 'delegation_id': 'delegation'}
            client.api = api
            self.assertIsNone(client.complete_authorization('a'))
            self.assertNotIn('authorization', client.conversation('a'))

    def test_other_user_cannot_read_pending_link(self):
        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            owner = module.Client('https://control.example', 'agent', store, user_key='owner')
            other = module.Client('https://control.example', 'agent', store, user_key='other')
            with store.locked() as state:
                state['target'] = {'origin': owner.origin, 'agent_id': owner.agent_id, 'subject': owner.subject}
                state['conversations']['a'] = {'id': 'session', 'authorization': {'id': 'x', 'expires_at': int(time.time() * 1000) + 60000, 'next_poll_at': int(time.time() * 1000) + 5000, 'url': 'https://buyer.example/private'}}
                store.save(state)
            with self.assertRaises(module.ClientError) as error:
                other.complete_authorization('a')
            self.assertEqual(error.exception.code, 'STATE_TARGET_MISMATCH')

    def test_rejects_insecure_verification_link(self):
        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            client = module.Client('https://control.example', 'agent', store)
            with store.locked() as state:
                state['conversations']['a'] = {'id': 'session'}
                store.save(state)
            client.api = lambda *args, **kwargs: {'verification_uri_complete': 'http://attacker.example/', 'exchange': 'secret', 'expires_at': int(time.time() * 1000) + 60000}
            with self.assertRaises(module.ClientError):
                client.start_authorization('a', {'value': {'id': 'request', 'provider': 'filtmall', 'state': 'state'}})
            self.assertNotIn('authorization', client.conversation('a'))

    def test_expired_authorization_is_cleared_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            client = module.Client('https://control.example', 'agent', store)
            with store.locked() as state:
                state['conversations']['a'] = {'id': 'session', 'authorization': {'id': 'x', 'expires_at': 1}}
                store.save(state)
            with self.assertRaises(module.ClientError) as error:
                client.complete_authorization('a')
            self.assertEqual(error.exception.code, 'AUTHORIZATION_EXPIRED')
            self.assertNotIn('authorization', client.conversation('a'))

    def test_wait_accepts_current_revision_document_without_request_id(self):
        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            client = module.Client('https://control.example', 'agent', store)
            with store.locked() as state:
                state['conversations']['a'] = {'id': 'session', 'pending': {'request_id': 'request', 'start_revision': 3}}
                store.save(state)
            client.result = lambda value: {'execution_result': {'operation_status': 'waiting'}}
            client.documents = lambda session, request, *args: [
                {'kind': 'filtalgo.commerce.authorization', 'schema_version': 1, 'revision': 4, 'request_id': None,
                 'value': {'id': 'challenge', 'provider': 'filtmall', 'state': 'secret'}},
            ]
            client.api = lambda method, path, body=None, headers=None: {
                'verification_uri_complete': 'https://buyer.example/oauth/device?user_code=abc',
                'exchange': 'secret-exchange', 'expires_at': int(time.time() * 1000) + 60000,
            }
            result = client.wait('a', 1)
            self.assertEqual(result['status'], 'authorization_required')
            self.assertNotIn('secret', str(result))
            self.assertNotIn('pending', client.conversation('a'))

    def test_pending_then_completed_without_exposing_exchange(self):
        calls = []
        def transport(method, path, body=None, token=None, headers=None):
            calls.append((method, path))
            if path.endswith('/device'):
                return {'verification_uri_complete': 'https://buyer.example/oauth/device?user_code=abc', 'exchange': 'secret-exchange', 'expires_at': int(time.time() * 1000) + 60000}
            if path.endswith('/device/poll'):
                return {'status': 'active' if len(calls) == 3 else 'authorization_pending'}
            raise AssertionError(path)
        with tempfile.TemporaryDirectory() as directory:
            store = module.Store(directory)
            client = module.Client('https://control.example', 'agent', store, transport=transport)
            with store.locked() as state:
                state['auth'] = {'access_token': 'platform', 'refresh_token': 'refresh', 'access_expires_at': int(time.time() * 1000) + 60000}
                state['conversations']['a'] = {'id': 'session'}
                store.save(state)
            result = client.start_authorization('a', {'value': {'id': 'request', 'provider': 'filtmall', 'state': 'private-state'}})
            self.assertEqual(result['status'], 'authorization_required')
            self.assertNotIn('secret-exchange', str(result))
            self.assertEqual(client.complete_authorization('a')['status'], 'authorization_required')
            self.assertEqual(len(calls), 1)
            with store.locked() as state:
                state['conversations']['a']['authorization']['next_poll_at'] = 0
                store.save(state)
            self.assertEqual(client.complete_authorization('a')['status'], 'authorization_required')
            with store.locked() as state:
                state['conversations']['a']['authorization']['next_poll_at'] = 0
                store.save(state)
            self.assertIsNone(client.complete_authorization('a'))
            self.assertIsNone(client.complete_authorization('a'))
            self.assertEqual(len(calls), 3)


if __name__ == '__main__':
    unittest.main()
