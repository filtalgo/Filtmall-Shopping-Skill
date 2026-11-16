import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import client


class AuthorizationInputIntegrity(unittest.TestCase):
    def make_client(self, directory, transport):
        api = client.Client('https://control.example', 'agent', client.Store(directory), transport=transport)
        with api.store.locked() as state:
            state['auth'] = {'access_token': 'fixture-access', 'refresh_token': 'fixture-refresh',
                             'access_expires_at': int(time.time() * 1000) + 600000}
            state['conversations']['c'] = {'id': 'session', 'last_request_id': 'original',
                                           'last_payload': 'original task', 'authorization': self.challenge()}
            api.store.save(state)
        return api

    @staticmethod
    def challenge():
        return {'id': 'challenge', 'state': 'fixture-state', 'exchange': 'fixture-exchange',
                'url': 'https://buyer.example/authorize', 'interval': 1,
                'expires_at': int(time.time() * 1000) + 60000}

    def test_send_does_not_complete_authorization_or_run_old_task_for_new_input(self):
        calls = []
        def transport(*args, **kwargs):
            calls.append(args)
            return {'status': 'active', 'id': 'delegation'}
        with tempfile.TemporaryDirectory() as directory:
            api = self.make_client(directory, transport)
            before = json.loads(api.store.path.read_text())
            with self.assertRaises(client.ClientError) as caught:
                api.send('c', '不要继续下单，先取消', timeout=0)
            self.assertEqual(caught.exception.code, 'RESUME_REQUIRED')
            self.assertEqual(calls, [])
            self.assertEqual(json.loads(api.store.path.read_text()), before)

    def test_force_and_async_send_cannot_replace_an_authorization_continuation(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            api = self.make_client(directory, lambda *args, **kwargs: calls.append(args))
            with api.store.locked() as state:
                conversation = state['conversations']['c']
                conversation.pop('authorization')
                conversation['pending'] = {'request_id': 'stable-continuation', 'text': 'continue original',
                                           'mode': 'prompt', 'authorization_resume': True, 'baseline_pending': True}
                api.store.save(state)
            before = json.loads(api.store.path.read_text())
            with self.assertRaises(client.ClientError) as caught:
                api.send('c', 'new input', wait=False, force=True)
            self.assertEqual(caught.exception.code, 'RESUME_REQUIRED')
            self.assertEqual(calls, [])
            self.assertEqual(json.loads(api.store.path.read_text()), before)

    def test_new_message_after_resume_is_persisted_and_submitted_exactly_once(self):
        writes = []
        def transport(method, path, body=None, **kwargs):
            if method == 'GET' and path.endswith('/documents?limit=1'):
                return {'revision': 12}
            if method == 'POST' and path.endswith('/inputs'):
                writes.append(body.copy())
                return {'status': 'accepted'}
            self.fail(path)
        with tempfile.TemporaryDirectory() as directory:
            api = self.make_client(directory, transport)
            with api.store.locked() as state:
                state['conversations']['c'].pop('authorization')
                state['conversations']['c']['last_status'] = 'completed'
                api.store.save(state)
            text = '保留原文 & 中文\n第二行，先查询'
            response = api.send('c', text, wait=False)
            saved = json.loads(api.store.path.read_text())['conversations']['c']
            self.assertEqual(response['status'], 'accepted')
            self.assertEqual(len(writes), 1)
            self.assertEqual(writes[0]['text'], text)
            self.assertEqual(saved['pending']['request_id'], writes[0]['request_id'])
            self.assertEqual(saved['pending']['text'], text)
            self.assertEqual(saved['last_payload'], text)

    def test_authorization_appearing_during_identity_lookup_is_not_overwritten(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            api = self.make_client(directory, lambda *args, **kwargs: calls.append(args))
            with api.store.locked() as state:
                state['conversations']['c'].pop('authorization')
                api.store.save(state)
            def token():
                with api.store.locked() as state:
                    state['conversations']['c']['authorization'] = self.challenge()
                    api.store.save(state)
                return 'fixture-access'
            api.token = token
            with self.assertRaises(client.ClientError) as caught:
                api.send('c', 'new input', wait=False)
            self.assertEqual(caught.exception.code, 'RESUME_REQUIRED')
            self.assertEqual(calls, [])
            self.assertNotIn('pending', json.loads(api.store.path.read_text())['conversations']['c'])

    def test_completed_status_fallback_saves_delegation_before_clearing_challenge(self):
        for conflict in (True, False):
            with self.subTest(conflict=conflict), tempfile.TemporaryDirectory() as directory:
                polls, deleted = [], []
                def transport(method, path, body=None, **kwargs):
                    if path.endswith('/device/poll'):
                        polls.append(path)
                        if conflict and len(polls) > 1:
                            raise client.ClientError('HTTP_409', 'completed elsewhere')
                        return {'status': 'authorization_pending', 'interval': 1}
                    if path.endswith('/completion'):
                        raise client.ClientError('HTTP_404', 'legacy receipt unavailable')
                    if method == 'GET' and path.endswith('/challenge'):
                        return {'status': 'completed', 'delegation_id': 'authoritative-delegation'}
                    if method == 'DELETE':
                        deleted.append(path)
                        return {'status': 'revoked'}
                    self.fail(path)
                api = self.make_client(directory, transport)
                with patch.object(client.time, 'sleep'):
                    api.complete_authorization('c', time.monotonic() + 5)
                saved = json.loads(api.store.path.read_text())['conversations']['c']
                self.assertNotIn('authorization', saved)
                self.assertEqual(saved.get('delegation_id'), 'authoritative-delegation')
                self.assertEqual(api.revoke_authorization('c')['status'], 'authorization_revoked')
                self.assertEqual(deleted, ['/api/v2/delegations/authoritative-delegation'])
                self.assertNotIn('delegation_id', json.loads(api.store.path.read_text())['conversations']['c'])
