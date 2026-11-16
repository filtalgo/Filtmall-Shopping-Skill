import base64
import gzip
import importlib.util
import json
import pathlib
import unittest

spec = importlib.util.spec_from_file_location('control_agent', pathlib.Path(__file__).parents[1] / 'scripts' / 'control_agent.py')
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)

class RegionSelectorTest(unittest.TestCase):
    def test_decode_and_reject_invalid_count(self):
        nodes = [['11', '0', '北京市', 'province'], ['1101', '11', '北京市', 'city'], ['110108', '1101', '海淀区', 'district']]
        payload = base64.b64encode(gzip.compress(json.dumps(nodes, ensure_ascii=False).encode())).decode()
        doc = {'value': {'schema': 'filtmall.region-selector/v1', 'columns': ['id', 'parent_id', 'name', 'level'], 'root_id': '0', 'encoding': 'gzip+base64', 'count': 3, 'data': payload, 'group_id': 'selector-1'}}
        self.assertEqual(client.decode_region_selector(doc)['nodes'], nodes)
        doc['value']['count'] = 4
        with self.assertRaises(client.ClientError):
            client.decode_region_selector(doc)
        doc['value']['count'] = 3
        doc['value']['data'] = base64.b64encode(b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03\xff\xff\xff\xff').decode()
        with self.assertRaises(client.ClientError):
            client.decode_region_selector(doc)

if __name__ == '__main__':
    unittest.main()

class WaitRegionSelectorTest(unittest.TestCase):
    def _run(self, document):
        from contextlib import contextmanager
        state = {'conversations': {'example': {'pending': {'request_id': 'request', 'start_revision': 0}}}}
        class Store:
            @contextmanager
            def locked(self):
                yield state
            def save(self, value):
                pass
        class Fake:
            store = Store()
            def result(self, value):
                return {'execution_result': {'operation_status': 'completed'}}
            def documents(self, session_id, request_id):
                return [document]
        value = {'id': 'session', 'pending': {'request_id': 'request', 'start_revision': 0}}
        return lambda: client.Client.wait(Fake(), 'example', 1, value=value), state

    def test_structured_error_is_returned_without_model_answer(self):
        run, state = self._run({'kind': 'filtalgo.commerce.region_selector_error', 'schema_version': 1, 'request_id': 'request', 'revision': 1, 'value': {'code': 'region_selector_unavailable', 'message': '地区选择器暂时不可用，请稍后重试。'}})
        result = run()
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'REGION_SELECTOR_UNAVAILABLE')
        self.assertNotIn('pending', state['conversations']['example'])
        self.assertEqual(state['conversations']['example']['last_status'], 'completed')

    def test_incomplete_selector_keeps_pending_for_resume(self):
        run, state = self._run({'kind': 'filtalgo.commerce.region_selector', 'schema_version': 1, 'request_id': 'request', 'revision': 1, 'value': {'group_id': 'selector', 'part_count': 2, 'part_index': 0, 'data': 'partial'}})
        with self.assertRaises(client.ClientError):
            run()
        self.assertIn('pending', state['conversations']['example'])

    def test_missing_public_response_is_not_success(self):
        run, state = self._run({'kind': 'request.status', 'schema_version': 1, 'request_id': 'request', 'revision': 1, 'value': {'status': 'completed', 'answer_document_id': None}})
        result = run()
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'NO_PUBLIC_RESPONSE')
        self.assertEqual(state['conversations']['example']['last_status'], 'completed')

class DocumentPaginationTest(unittest.TestCase):
    def test_large_selector_documents_are_fetched_in_bounded_pages(self):
        from urllib.parse import parse_qs, urlparse
        docs = [{'revision': i + 1, 'value': {'data': 'a' * 180000}} for i in range(55)]
        sizes = []

        class Fake:
            def path(self, session_id, suffix):
                return '/sessions/' + session_id + suffix
            def api(self, method, path):
                query = parse_qs(urlparse(path).query)
                after = int(query['after_order'][0])
                limit = int(query['limit'][0])
                self.assert_limit(limit)
                page = docs[after:after + limit]
                result = {'documents': page, 'next_cursor': after + len(page) if after + len(page) < len(docs) else None}
                sizes.append(len(json.dumps(result).encode()))
                return result
            def assert_limit(self, limit):
                assert limit == 20

        actual = client.Client.documents(Fake(), 'session', 'request')
        self.assertEqual(actual, docs)
        self.assertEqual(len(sizes), 3)
        self.assertLess(max(sizes), 8 * 1024 * 1024)
