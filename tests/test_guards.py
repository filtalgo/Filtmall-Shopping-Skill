"""本地防误操作护栏的离线测试：不连网，用假传输模拟服务端。"""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import client as ca


class FakeHTTP:
    """最小可用的 Control 替身：会话、输入、结果、文档。"""

    def __init__(self):
        self.calls = []
        self.revision = 0
        self.fail_inputs = None
        self.fail_result = None
        self.fail_documents = None
        self.operation_status = 'running'

    def __call__(self, method, path, body=None, token=None, headers=None):
        self.calls.append((method, path, token, headers))
        if path == '/api/v2/identity/guests':
            return {'access_token': 'a', 'refresh_token': 'r', 'access_expires_at': time.time() * 1000 + 3_600_000}
        if method == 'POST' and path == '/api/v2/sessions':
            return {'id': 's1'}
        if '/documents?' in path and 'after_order=' not in path and 'after_revision=' not in path:
            return {'revision': self.revision}
        if '/documents?after_order=' in path or '/documents?after_revision=' in path:
            if self.fail_documents:
                raise ca.ClientError(self.fail_documents, '模拟文档查询失败')
            return {'revision': self.revision, 'documents': [], 'next_cursor': None}
        if path.endswith('/result'):
            if self.fail_result:
                raise ca.ClientError(self.fail_result, '模拟结果查询失败')
            return {'execution_result': {'operation_status': self.operation_status}}
        if method == 'POST' and path.endswith('/inputs'):
            if self.fail_inputs:
                raise ca.ClientError(self.fail_inputs, '模拟提交失败')
            return {'status': 'accepted'}
        raise ca.ClientError('HTTP_404', 'not found')


def make_client():
    directory = Path(tempfile.mkdtemp())
    return ca.Client('https://control.test', 'agent', ca.Store(directory), transport=FakeHTTP())


class GuardTests(unittest.TestCase):
    def test_fresh_conversation_sends(self):
        client = make_client()
        self.assertEqual(client.send('never-sent', 'x', wait=False)['status'], 'accepted')

    def test_repeat_input_refused(self):
        client = make_client()
        client.send('c', 'hello', wait=False)
        with self.assertRaises(ca.ClientError) as exc:
            client.send('c', 'hello', wait=False, force=True)
        self.assertEqual(exc.exception.code, 'PENDING_INPUT')

    def test_resume_required_after_unknown_ending(self):
        client = make_client()
        client.http.operation_status = 'completed'
        client.http.fail_documents = 'RESULT_UNKNOWN'
        with self.assertRaises(ca.ClientError) as first:
            client.send('c', 'first', timeout=2.5)
        self.assertEqual(first.exception.code, 'RESULT_UNKNOWN')
        client.http.fail_documents = None
        self.assertTrue(client._needs_resume(client.conversation('c')))
        with self.assertRaises(ca.ClientError) as exc:
            client.send('c', 'second', wait=False)
        self.assertEqual(exc.exception.code, 'RESUME_REQUIRED')
        # --force 只跳过终态未确认的拦截，不会绕过“未结算请求必须先 resume”
        with self.assertRaises(ca.ClientError) as still:
            client.send('c', 'second', wait=False, force=True)
        self.assertEqual(still.exception.code, 'PENDING_INPUT')
        self.assertEqual(client.resume('c', timeout=2.5)['status'], 'completed')
        self.assertEqual(client.send('c', 'second', wait=False)['status'], 'accepted')

    def test_resume_clears_guard(self):
        client = make_client()
        client.http.operation_status = 'completed'
        client.http.fail_documents = 'RESULT_UNKNOWN'
        with self.assertRaises(ca.ClientError):
            client.send('c', 'first', timeout=2.5)
        client.http.fail_documents = None
        client.http.operation_status = 'completed'
        self.assertEqual(client.resume('c', timeout=2.5)['status'], 'completed')
        self.assertNotIn('pending', client.conversation('c'))
        self.assertNotIn('last_error', client.conversation('c'))
        self.assertEqual(client.send('c', 'second', wait=False)['status'], 'accepted')

    def test_submit_failure_marks_unknown(self):
        client = make_client()
        client.http.fail_inputs = 'RESULT_UNKNOWN'
        with self.assertRaises(ca.ClientError) as exc:
            client.send('c', 'x', wait=False)
        self.assertEqual(exc.exception.code, 'RESULT_UNKNOWN')
        self.assertEqual(client.conversation('c')['last_error']['code'], 'RESULT_UNKNOWN')

    def test_timeout_marks_unknown(self):
        client = make_client()
        with self.assertRaises(ca.ClientError) as exc:
            client.send('c', 'x', timeout=0)
        self.assertEqual(exc.exception.code, 'PENDING_INPUT')
        self.assertEqual(client.conversation('c')['last_error']['code'], 'TIMEOUT_WAITING')

    def test_terminal_state_does_not_need_resume(self):
        client = make_client()
        with client.store.locked() as state:
            state['conversations']['c'] = {'id': 's1', 'last_status': 'completed'}
            client.store.save(state)
        self.assertFalse(ca.Client._needs_resume(client.conversation('c')))
        self.assertEqual(json.loads(json.dumps(client.conversation('c')))['last_status'], 'completed')


if __name__ == '__main__':
    unittest.main()
