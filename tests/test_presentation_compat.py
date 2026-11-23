import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cards
import client
import service


def sample_turn():
    return {
        'ok': True,
        'status': 'completed',
        'answer': {'kind': 'message', 'schema_version': 2, 'value': {
            'role': 'assistant',
            'content': '为您找到百元内的温和保湿面膜：',
        }},
        'context_documents': [{
            'document_id': 'card-1',
            'revision': 5,
            'kind': 'filtalgo.shopping.block:filtmall.product-card/v2',
            'value': {'block': {'schema': 'filtmall.product-card/v2', 'payload': {
                'rank': 1,
                'product': {
                    'goods_id': 'G900',
                    'sku_id': 'S900',
                    'title': '温和补水面膜',
                    'price_amount': '49.00',
                    'spec_summary': '8片/盒',
                    'thumbnail': 'https://filtering-tech-product-data.oss-cn-beijing.aliyuncs.com/mask.png',
                },
                'recommendation_reason': '适合日常保湿补水。',
            }}},
        }],
        'cart': {
            'status': 'current',
            'items': [{'sku_id': 'S900', 'title': '温和补水面膜', 'quantity': 1, 'checked': True, 'price': 49.0}],
            'cart_url': 'https://buyer.filtalgo.com/cart',
        },
    }


class PresentationCompatTests(unittest.TestCase):
    def test_cli_defaults_to_md_format_and_emits_display_file(self):
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory) / 'state'
            state_dir.mkdir()
            out_dir = Path(directory) / 'out'
            api = unittest.mock.Mock()
            api.send.return_value = sample_turn()
            checker = unittest.mock.Mock()
            checker.check.return_value = {'status': 'up_to_date', 'notify': False}
            stdin_payload = json.dumps({'conversation': 'conv-default', 'text': '推荐面膜'}) + '\n'
            with patch.object(sys, 'argv', ['service.py', '--once', '--state-dir', str(state_dir), '--out-dir', str(out_dir)]), \
                    patch.object(service, 'build_client', return_value=api), \
                    patch.object(service, 'UpdateChecker', return_value=checker), \
                    patch('sys.stdin', new=type('In', (), {'buffer': __import__('io').BytesIO(stdin_payload.encode('utf8'))})()), \
                    patch('sys.stdout', new=type('Out', (__import__('io').StringIO,), {'reconfigure': lambda self, **k: None})()) as out_stream, \
                    patch('sys.stderr', new=type('Err', (__import__('io').StringIO,), {'reconfigure': lambda self, **k: None})()):
                service.main()
            response = json.loads(out_stream.getvalue().strip())
            self.assertTrue(response['ok'])
            self.assertIn('display_file', response)
            self.assertIn('answer_file', response)
            self.assertTrue(response['html_file'].endswith('.cards.md'))
            self.assertTrue(response['cart_file'].endswith('.md'))
            self.assertNotIn('fragment_file', response)
            self.assertNotIn('page_file', response)
            display_text = Path(response['display_file']).read_text(encoding='utf8')
            self.assertIn('温和补水面膜', display_text)
            self.assertIn('https://m.filtalgo.com/pages/goods/product/detail?goodsId=G900&skuId=S900', display_text)
            self.assertIn('https://m.filtalgo.com/pages/tabbar/cart', display_text)

    def test_explicit_widget_and_html_keep_legacy_fields_plus_display_file(self):
        png = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc`\xf8\xcf'
            b'\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        with tempfile.TemporaryDirectory() as directory, patch.object(cards, 'thumbnail_data', return_value=(png, 'image/png')):
            class Stub:
                def send(self, *args):
                    return sample_turn()

            widget_out = service.handle(Stub(), {'op': 'send', 'conversation': 'w', 'text': '查询', 'format': 'widget'}, 'md', directory)
            self.assertIn('display_file', widget_out)
            self.assertEqual(widget_out['fragment_file'], widget_out['html_file'])
            self.assertEqual(widget_out['cart_fragment_file'], widget_out['cart_file'])
            self.assertNotIn('page_file', widget_out)
            self.assertIn('温和补水面膜', Path(widget_out['display_file']).read_text(encoding='utf8'))
            self.assertIn('data:image/png;base64,', Path(widget_out['fragment_file']).read_text(encoding='utf8'))

            html_out = service.handle(Stub(), {'op': 'send', 'conversation': 'h', 'text': '查询', 'format': 'html'}, 'md', directory)
            self.assertIn('display_file', html_out)
            self.assertEqual(html_out['page_file'], html_out['html_file'])
            self.assertEqual(html_out['cart_page_file'], html_out['cart_file'])
            self.assertNotIn('fragment_file', html_out)
            self.assertTrue(Path(html_out['page_file']).read_text(encoding='utf8').startswith('<!doctype html>'))
            self.assertIn('温和补水面膜', Path(html_out['display_file']).read_text(encoding='utf8'))

    def test_html_and_image_failures_preserve_display_file_without_extra_requests(self):
        calls = []

        class Stub:
            def send(self, *args):
                calls.append(args)
                return sample_turn()

        with tempfile.TemporaryDirectory() as directory:
            # 1) 图片下载返回空时，文字和链接完整保留。
            with patch.object(cards, 'thumbnail_data', return_value=None):
                no_img = service.handle(Stub(), {'op': 'send', 'conversation': 'no-img', 'text': '查询', 'format': 'widget'}, 'md', directory)
            self.assertNotIn('presentation_errors', no_img)
            self.assertIn('https://m.filtalgo.com/pages/goods/product/detail?goodsId=G900&skuId=S900',
                          Path(no_img['display_file']).read_text(encoding='utf8'))

            # 2) HTML 卡片渲染抛异常时，display_file 仍可用，错误可观测，且不重发业务请求。
            with patch.object(cards, 'render_widget', side_effect=RuntimeError('html boom')):
                html_fail = service.handle(Stub(), {'op': 'send', 'conversation': 'html-fail', 'text': '查询', 'format': 'widget'}, 'md', directory)
            self.assertEqual(html_fail['status'], 'completed')
            self.assertEqual(html_fail['presentation_status'], 'failed')
            self.assertIn('product_render_failed', html_fail['presentation_errors'])
            self.assertNotIn('fragment_file', html_fail)
            self.assertTrue(Path(html_fail['display_file']).is_file())
            self.assertIn('温和补水面膜', Path(html_fail['display_file']).read_text(encoding='utf8'))
            self.assertEqual(len(calls), 2)

    def test_display_write_failure_never_returns_nonexistent_display_file(self):
        class Stub:
            def send(self, *args):
                return sample_turn()

        with tempfile.TemporaryDirectory() as directory:
            blocked = Path(directory) / 'blocked-dir'
            blocked.mkdir()
            out = service.handle(
                Stub(),
                {'op': 'send', 'conversation': 'write-fail', 'text': '查询', 'display_path': str(blocked)},
                'md',
                directory,
            )
            self.assertEqual(out['status'], 'completed')
            self.assertEqual(out['presentation_status'], 'failed')
            self.assertIn('output_write_failed', out['presentation_errors'])
            self.assertNotIn('display_file', out)
            self.assertTrue(Path(out['answer_file']).is_file())

            # 自定义 display_path 正常写入与重复路径拦截
            custom_display = Path(directory) / 'custom-display.md'
            ok_out = service.handle(
                Stub(),
                {'op': 'send', 'conversation': 'custom-ok', 'text': '查询', 'out_dirs': {'display_path': str(custom_display)}},
                'md',
                directory,
            )
            self.assertEqual(Path(ok_out['display_file']), custom_display.resolve())
            if os.name != 'nt':
                self.assertEqual(custom_display.stat().st_mode & 0o777, 0o600)

            with self.assertRaises(client.ClientError) as duplicate_err:
                service.handle(
                    Stub(),
                    {'op': 'send', 'conversation': 'dup', 'text': '查询',
                     'display_path': str(custom_display), 'answer_path': str(custom_display)},
                    'md',
                    directory,
                )
            self.assertEqual(duplicate_err.exception.code, 'INVALID_REQUEST')

    def test_resume_switches_format_to_widget_without_resubmitting_business_input(self):
        submissions = []

        def transport(method, path, body=None, token=None, headers=None):
            if path == '/api/v2/identity/guests':
                return {'access_token': 'guest-token', 'refresh_token': 'refresh-token', 'access_expires_at': time.time() * 1000 + 600000}
            if method == 'POST' and path == '/api/v2/sessions':
                return {'id': 'session-1'}
            if path.endswith('/inputs'):
                submissions.append(body)
                return {'status': 'accepted'}
            if path.endswith('/result'):
                return {'status': 'completed', 'execution_result': {'status': 'applied', 'operation_status': 'completed'}}
            if '/documents?' in path:
                rid = submissions[-1]['request_id']
                return {
                    'revision': 8,
                    'next_cursor': None,
                    'documents': [
                        {'document_id': 'st', 'kind': 'request.status', 'schema_version': 1, 'request_id': rid, 'revision': 6,
                         'value': {'status': 'completed', 'answer_document_id': 'ans'}},
                        {'document_id': 'ans', 'kind': 'message', 'schema_version': 2, 'request_id': rid, 'revision': 7,
                         'value': {'role': 'assistant', 'content': '为您推荐温和补水面膜：'}},
                        {**sample_turn()['context_documents'][0], 'revision': 8, 'request_id': rid},
                    ],
                }
            raise AssertionError((method, path))

        with tempfile.TemporaryDirectory() as directory, patch.object(cards, 'thumbnail_data', return_value=None):
            api = client.Client('https://control.example', 'shopping', client.Store(Path(directory) / 'state'), transport)
            first = service.handle(api, {'op': 'send', 'conversation': 'rerender', 'text': '推荐面膜'}, 'md', Path(directory) / 'out')
            self.assertEqual(len(submissions), 1)
            self.assertIn('display_file', first)
            self.assertNotIn('fragment_file', first)

            second = service.handle(api, {'op': 'resume', 'conversation': 'rerender', 'format': 'widget'}, 'md', Path(directory) / 'out')
            self.assertEqual(len(submissions), 1)
            self.assertIn('display_file', second)
            self.assertIn('fragment_file', second)
            self.assertIn('温和补水面膜', Path(second['display_file']).read_text(encoding='utf8'))


if __name__ == '__main__':
    unittest.main()
