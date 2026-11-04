import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import client as c

class IncrementalTests(unittest.TestCase):
    def make(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        return c.Client('https://control.test', 'agent', c.Store(tmp.name))

    def test_revision_pages_and_deletion(self):
        api = self.make(); paths = []
        def read(method, path, *args, **kwargs):
            paths.append(path)
            if 'after_revision=40' in path:
                return {'revision': 43, 'documents': [{'document_id': 'x', 'revision': 41, 'deleted': False}], 'next_cursor': 41}
            return {'revision': 43, 'documents': [{'document_id': 'x', 'revision': 42, 'deleted': True}, {'document_id': 'y', 'revision': 43, 'deleted': False}], 'next_cursor': None}
        api.api = read
        self.assertEqual([d['document_id'] for d in api.documents('s', 'r', 40)], ['y'])
        self.assertIn('after_revision=41', paths[1])

    def test_missing_canonical_answer_falls_back(self):
        api = self.make(); calls = []
        status = {'kind': 'request.status', 'request_id': 'r', 'schema_version': 1, 'value': {'status': 'completed', 'answer_document_id': 'answer'}}
        answer = {'kind': 'message', 'schema_version': 1, 'document_id': 'answer', 'request_id': 'r', 'value': {'role': 'assistant', 'content': 'ok'}}
        def docs(session, request, *baseline):
            calls.append(baseline)
            return [status] if baseline else [status, answer]
        api.documents = docs
        result = api.settle('c', {'id': 's', 'pending': {'request_id': 'r', 'start_revision': 40}}, 'completed')
        self.assertEqual(result['answer']['value']['content'], 'ok')
        self.assertEqual(calls, [(40,), ()])

    def test_cursor_reset_falls_back(self):
        api = self.make(); calls = []
        def docs(session, request, *baseline):
            calls.append(baseline)
            if baseline: raise c.ClientError('INVALID_CURSOR', 'reset')
            return []
        api.documents = docs
        result = api.settle('c', {'id': 's', 'pending': {'request_id': 'r', 'start_revision': 40}}, 'completed')
        self.assertEqual(result['error']['code'], 'NO_PUBLIC_RESPONSE')
        self.assertEqual(calls, [(40,), ()])

    def test_invalid_cursor_is_rejected(self):
        api = self.make()
        api.api = lambda *a, **k: {'revision': 8, 'documents': [], 'next_cursor': 5}
        with self.assertRaises(c.ClientError) as error: api.documents('s', 'r', 5)
        self.assertEqual(error.exception.code, 'INVALID_CURSOR')

if __name__ == '__main__': unittest.main()
