"""更新入口离线契约：不调用真实购物接口或 GitHub。"""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import service
import update_check


UPDATE = {'status': 'available', 'notify': True, 'release_tag': 'v99.0.0'}
SEND = {'op': 'send', 'conversation': 'c', 'text': '查询', 'wait': False}


class Stream(io.StringIO):
    def reconfigure(self, **kwargs):
        pass


class Input:
    def __init__(self, text):
        self.buffer = io.BytesIO(text.encode('utf8'))


def run_main(args, text='', api=None, checker=None, forbid_input=False):
    stdout, stderr = Stream(), Stream()
    stdin = Mock() if forbid_input else Input(text)
    if forbid_input:
        type(stdin).buffer = property(lambda _: (_ for _ in ()).throw(AssertionError('stdin read')))
    with patch.object(sys, 'argv', ['service.py', *args]), patch.object(sys, 'stdin', stdin), \
            patch.object(sys, 'stdout', stdout), patch.object(sys, 'stderr', stderr), \
            patch.object(service, 'build_client', return_value=api) as build, \
            patch.object(service, 'UpdateChecker', return_value=checker) as factory, \
            patch.object(service, 'write_heartbeat') as heartbeat:
        try:
            service.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    return code, lines, build, factory, heartbeat


class SendUpdateTests(unittest.TestCase):
    def test_each_send_checks_before_single_business_send(self):
        events = []
        api = Mock()
        api.send.side_effect = lambda *a: events.append('send') or {'status': 'accepted'}
        checker = Mock()
        checker.check.side_effect = lambda c: events.append(('check', c)) or dict(UPDATE)
        for _ in range(2):
            result = service.handle(api, SEND, 'md', update_checker=checker)
            self.assertEqual(result['skill_update'], UPDATE)
            self.assertTrue(result['ok'])
            self.assertEqual(result['status'], 'accepted')
        self.assertEqual(events, [('check', 'c'), 'send', ('check', 'c'), 'send'])
        self.assertEqual(api.send.call_count, 2)

    def test_no_checker_is_offline(self):
        api = Mock()
        api.send.return_value = {'status': 'accepted'}
        with patch.object(update_check.UpdateChecker, 'check', side_effect=AssertionError('network')):
            self.assertNotIn('skill_update', service.handle(api, SEND, 'md'))

    def test_check_failure_is_unknown_and_does_not_change_business(self):
        api, checker = Mock(), Mock()
        api.send.return_value = {'ok': False, 'status': 'failed', 'error': {'code': 'BUSINESS'}}
        checker.check.side_effect = RuntimeError('private exception')
        result = service.handle(api, SEND, 'md', update_checker=checker)
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['skill_update']['status'], 'unknown')
        self.assertFalse(result['skill_update']['notify'])
        self.assertNotIn('private', json.dumps(result))
        api.send.assert_called_once()

    def test_known_error_preserves_update_and_unknown_error_drops_it(self):
        api, checker = Mock(), Mock()
        checker.check.return_value = dict(UPDATE)
        api.send.side_effect = service.ClientError('BUSINESS', '原业务错误')
        with patch.object(sys, 'stderr', Stream()), self.assertRaises(service.ClientError) as error:
            service.run_request(api, SEND, 'md', update_checker=checker)
        self.assertEqual((error.exception.code, str(error.exception)), ('BUSINESS', '原业务错误'))
        self.assertEqual(error.exception.skill_update, UPDATE)
        api.send.side_effect = RuntimeError('unknown')
        with patch.object(sys, 'stderr', Stream()), self.assertRaises(service.ClientError) as error:
            service.run_request(api, SEND, 'md', update_checker=checker)
        self.assertEqual(error.exception.code, 'INTERNAL_ERROR')
        self.assertIn('resume', str(error.exception))
        self.assertFalse(hasattr(error.exception, 'skill_update'))

    def test_known_error_reused_by_resume_has_no_previous_sidecar(self):
        api, checker = Mock(), Mock()
        checker.check.return_value = dict(UPDATE)
        error = service.ClientError('BUSINESS', '原错误')
        api.send.side_effect = error
        api.resume.side_effect = error
        with self.assertRaises(service.ClientError):
            service.handle(api, SEND, 'md', update_checker=checker)
        with self.assertRaises(service.ClientError) as resumed:
            service.handle(api, {'op': 'resume', 'conversation': 'c'}, 'md', update_checker=checker)
        self.assertFalse(hasattr(resumed.exception, 'skill_update'))
        checker.check.assert_called_once_with('c')

    def test_unknown_check_result_preserves_success(self):
        api, checker = Mock(), Mock()
        api.send.return_value = {'status': 'accepted'}
        unknown = {'status': 'unknown', 'notify': False, 'reason': 'timeout'}
        checker.check.return_value = unknown
        result = service.handle(api, SEND, 'md', update_checker=checker)
        self.assertTrue(result['ok'])
        self.assertEqual(result['skill_update'], unknown)

    def test_invalid_parameters_never_check_or_send(self):
        api, checker = Mock(), Mock()
        overrides = [{'text': ''}, {'conversation': ''}, {'format': 'bad'}, {'timeout': float('nan')},
                     {'max': True}, {'wait': 1}, {'all': 'yes'}, {'allow_repeat': 1}, {'force': 1},
                     {'answer_path': ''}, {'out_dirs': {'bad': 'x'}},
                     {'out_dirs': {'answer_path': 'same', 'page_path': 'same'}}]
        for override in overrides:
            with self.subTest(override=override), self.assertRaises(service.ClientError):
                service.handle(api, dict(SEND, **override), 'md', update_checker=checker)
        checker.check.assert_not_called()
        api.send.assert_not_called()

    def test_other_ops_never_check(self):
        api, checker = Mock(), Mock()
        for name in ('resume', 'cancel', 'clear', 'reset_authorization'):
            getattr(api, name).return_value = {'status': 'idle'}
        api.conversation.return_value = {}
        for op in ('resume', 'cancel', 'clear', 'auth-reset', 'status', 'ping'):
            self.assertTrue(service.handle(api, {'op': op, 'conversation': 'c'}, 'md', update_checker=checker)['ok'])
        checker.check.assert_not_called()


class MainUpdateTests(unittest.TestCase):
    def test_once_and_daemon_keep_one_json_per_request(self):
        for once in (False, True):
            with self.subTest(once=once), tempfile.TemporaryDirectory() as directory:
                api, checker = Mock(), Mock()
                api.send.return_value = {'status': 'accepted'}
                checker.check.return_value = dict(UPDATE)
                requests = [{k: v for k, v in SEND.items() if k != 'op'}] if once else [SEND, SEND]
                args = ['--state-dir', directory, '--user-key', 'user', '--update-timeout', '0.5']
                code, lines, build, factory, _ = run_main(args + (['--once'] if once else []),
                    '\n'.join(json.dumps(r) for r in requests), api, checker)
                self.assertEqual(code, 0)
                self.assertEqual([r['id'] for r in lines], list(range(1, len(requests) + 1)))
                self.assertTrue(all(r['skill_update'] == UPDATE for r in lines))
                self.assertEqual(api.send.call_count, len(requests))
                build.assert_called_once()
                factory.assert_called_once_with(service.SKILL_DIR, Path(directory), 'user', 0.5)

    def test_known_error_has_sidecar_next_resume_and_unknown_have_none(self):
        api, checker = Mock(), Mock()
        checker.check.return_value = dict(UPDATE)
        api.send.side_effect = [service.ClientError('ORIGINAL', '原错误'), RuntimeError('boom')]
        api.resume.return_value = {'status': 'completed'}
        requests = [SEND, {'op': 'resume', 'conversation': 'c'}, SEND]
        with tempfile.TemporaryDirectory() as directory:
            code, lines, build, _, _ = run_main(['--state-dir', directory],
                '\n'.join(json.dumps(r) for r in requests), api, checker)
        self.assertEqual(code, 0)
        self.assertEqual(lines[0]['error'], {'code': 'ORIGINAL', 'message': '原错误'})
        self.assertEqual(lines[0]['skill_update'], UPDATE)
        self.assertTrue(all('skill_update' not in r for r in lines[1:]))
        self.assertEqual(lines[2]['error']['code'], 'INTERNAL_ERROR')
        self.assertEqual(checker.check.call_count, 2)
        build.assert_called_once()

    def test_management_never_builds_business_client_reads_stdin_or_heartbeats(self):
        for action in ('check', 'shown', 'later', 'ignore', 'reset'):
            checker = Mock()
            checker.check.return_value = dict(UPDATE)
            checker.record.return_value = {'ok': True, 'action': action}
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory:
                code, lines, build, factory, heartbeat = run_main([
                    '--state-dir', directory, '--user-key', 'user', '--control-url', 'https://control.test',
                    '--agent-id', 'agent', '--update-action', action,
                    '--update-version', 'v99.0.0', '--update-conversation', 'c'], checker=checker, forbid_input=True)
                self.assertEqual(code, 0)
                self.assertEqual(lines, [{'ok': True, 'skill_update': UPDATE}] if action == 'check' else [{'ok': True, 'action': action}])
                factory.assert_called_once_with(service.SKILL_DIR, Path(directory), 'user', 2.0)
                build.assert_not_called()
                heartbeat.assert_not_called()
                if action != 'check':
                    checker.record.assert_called_once_with(action, 'v99.0.0', 'c')

    def test_management_errors_are_one_json_and_nonzero(self):
        for fail in ('record', 'check', 'target'):
            checker = Mock()
            checker.record.return_value = {'ok': False, 'action': 'shown', 'error': 'reminder_not_saved'}
            checker.check.side_effect = RuntimeError('secret')
            args = ['--update-action', 'check' if fail == 'check' else 'shown']
            if fail == 'target':
                args += ['--control-url', 'https://control.test']
            code, lines, build, _, heartbeat = run_main(args, checker=checker, forbid_input=True)
            self.assertNotEqual(code, 0)
            self.assertEqual(len(lines), 1)
            self.assertFalse(lines[0]['ok'])
            self.assertNotIn('secret', json.dumps(lines))
            build.assert_not_called()
            heartbeat.assert_not_called()

    def test_real_management_command_never_creates_business_state(self):
        for action, extra, expected in [('shown', [], 1), ('later', ['--update-version', 'v99.0.0', '--update-conversation', 'c'], 0)]:
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory:
                proc = subprocess.run([sys.executable, str(Path(service.__file__)), '--state-dir', directory,
                    '--update-action', action, *extra], input='not-json\n', capture_output=True,
                    encoding='utf8', timeout=5)
                self.assertEqual(proc.returncode, expected)
                self.assertEqual(len(proc.stdout.splitlines()), 1)
                self.assertEqual(json.loads(proc.stdout)['ok'], expected == 0)
                self.assertFalse((Path(directory) / 'service-heartbeat.json').exists())
                self.assertTrue(all(p.name == 'skill-update-reminders' for p in Path(directory).iterdir()))

    def test_reminder_management_and_send_share_actual_state(self):
        release = subprocess.CompletedProcess([], 0, json.dumps({'tag_name': 'v99.0.0', 'draft': False, 'prerelease': False}), '')
        for action in ('shown', 'later', 'ignore'):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory:
                checker = update_check.UpdateChecker(service.SKILL_DIR, directory, 'user')
                code, lines, _, _, _ = run_main(['--state-dir', directory, '--user-key', 'user',
                    '--update-action', action, '--update-version', 'v99.0.0', '--update-conversation', 'c'], checker=checker)
                self.assertEqual(code, 0)
                api = Mock()
                api.send.return_value = {'status': 'accepted'}
                with patch.object(update_check.subprocess, 'run', return_value=release) as network:
                    _, lines, _, _, _ = run_main(['--state-dir', directory, '--user-key', 'user', '--once'], json.dumps(SEND), api, checker)
                    self.assertEqual(lines[0]['skill_update']['status'], 'available')
                    self.assertFalse(lines[0]['skill_update']['notify'])
                    network.assert_called_once()

    def test_invalid_timeout_and_orphan_flags_are_rejected_without_client(self):
        for args in ([ '--update-timeout', value] for value in ('nan', 'inf', '-inf', '0', '-1', '30.1', 'bad')):
            code, _, build, _, _ = run_main(args, forbid_input=True)
            self.assertNotEqual(code, 0)
            build.assert_not_called()
        for flag in ('--update-version', '--update-conversation'):
            code, _, build, _, _ = run_main([flag, 'v1.0.0'], forbid_input=True)
            self.assertNotEqual(code, 0)
            build.assert_not_called()


if __name__ == '__main__':
    unittest.main()
