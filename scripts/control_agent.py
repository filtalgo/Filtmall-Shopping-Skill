#!/usr/bin/env python3
"""Public Control guest client. Standard library only; no channel secrets."""
import argparse
import base64
import gzip
import io
from contextlib import contextmanager
import hashlib
import json
import zlib
import os
from pathlib import Path
import sys
import tempfile
import time
from urllib import error, parse, request
import uuid


class ClientError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def decode_region_selector(document):
    value = document.get('value')
    if not isinstance(value, dict) or value.get('schema') != 'filtmall.region-selector/v1' or value.get('encoding') != 'gzip+base64' or value.get('columns') != ['id', 'parent_id', 'name', 'level'] or value.get('root_id') != '0':
        raise ClientError('INVALID_REGION_SELECTOR', '地区选择器数据无效。')
    data = value.get('data')
    try:
        if not isinstance(data, str) or len(data) > 1800000:
            raise ValueError('invalid size')
        compressed = base64.b64decode(data, validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as source:
            raw = source.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError('directory too large')
        nodes = json.loads(raw)
        if not isinstance(nodes, list) or len(nodes) != value.get('count') or len(nodes) > 200000:
            raise ValueError('invalid node count')
        if any(not isinstance(row, list) or len(row) != 4 or any(not isinstance(x, str) or not x for x in row) for row in nodes):
            raise ValueError('invalid node')
    except (ValueError, TypeError, OSError, EOFError, zlib.error):
        raise ClientError('INVALID_REGION_SELECTOR', '地区选择器数据无效。') from None
    return {'schema': value['schema'], 'selector_id': value['group_id'], 'columns': value['columns'], 'root_id': '0', 'nodes': nodes}


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HTTP:
    def __init__(self, origin):
        self.origin = origin
        self.opener = request.build_opener(NoRedirect())

    def __call__(self, method, path, body=None, token=None, headers=None):
        merged = {'Content-Type': 'application/json', 'Accept': 'application/json', **(headers or {})}
        if token:
            merged['Authorization'] = 'Bearer ' + token
        data = json.dumps(body).encode() if body is not None else None
        try:
            with self.opener.open(request.Request(self.origin + path, data, merged, method=method), timeout=20) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise ClientError('RESPONSE_TOO_LARGE', '响应过大，保留原请求并使用 resume 核对。')
                try:
                    return json.loads(raw) if raw else None
                except ValueError:
                    raise ClientError('INVALID_RESPONSE', '响应不是 JSON，保留原请求并使用 resume 核对。') from None
        except error.HTTPError as exc:
            raise ClientError('HTTP_' + str(exc.code), 'Control 返回 HTTP ' + str(exc.code) + '；未自动重试或切换环境。') from None
        except (error.URLError, TimeoutError, OSError):
            raise ClientError('RESULT_UNKNOWN', '连接中断或超时；结果未知，使用同一会话的 resume，不要重发新消息。') from None


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.is_symlink():
            raise ClientError('UNSAFE_STATE', '状态目录不能是符号链接。')
        if os.name != 'nt':
            self.directory.chmod(0o700)
        self.path = self.directory / 'state.json'

    @contextmanager
    def locked(self):
        lockpath = self.directory / 'state.lock'
        if lockpath.is_symlink() or self.path.is_symlink():
            raise ClientError('UNSAFE_STATE', '状态文件不能是符号链接。')
        with open(lockpath, 'a+b') as lock:
            if os.name == 'nt':
                import msvcrt
                lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                os.chmod(lockpath, 0o600)
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                if self.path.exists():
                    if os.name != 'nt':
                        self.path.chmod(0o600)
                    state = json.loads(self.path.read_text())
                else:
                    state = {'auth': None, 'conversations': {}}
                yield state
            finally:
                if os.name == 'nt':
                    lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def save(self, state):
        fd, name = tempfile.mkstemp(dir=self.directory, prefix='.state-')
        try:
            with os.fdopen(fd, 'w', encoding='utf8') as stream:
                json.dump(state, stream, ensure_ascii=False)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    @contextmanager
    def authorization_lock(self, key):
        path = self.directory / ('auth-' + hashlib.sha256(key.encode()).hexdigest() + '.lock')
        if path.is_symlink():
            raise ClientError('UNSAFE_STATE', '授权锁不能是符号链接。')
        with open(path, 'a+b') as lock:
            if os.name == 'nt':
                import msvcrt
                lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                os.chmod(path, 0o600)
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == 'nt':
                    lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock, fcntl.LOCK_UN)


class Client:
    def __init__(self, origin, agent_id, store, transport=None, user_key='local'):
        url = parse.urlsplit(origin)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
            raise ClientError('INVALID_ORIGIN', 'Control 地址必须是明确的 HTTPS 根地址。')
        if not agent_id or not agent_id.strip():
            raise ClientError('INVALID_AGENT', '需要明确的目标 Agent。')
        self.origin = origin.rstrip('/')
        self.agent_id = agent_id
        self.subject = hashlib.sha256(user_key.encode()).hexdigest()
        self.store = store
        self.http = transport or HTTP(self.origin)

    def token(self):
        with self.store.locked() as state:
            identity = {'origin': self.origin, 'agent_id': self.agent_id, 'subject': self.subject}
            if state.get('target', identity) != identity:
                raise ClientError('STATE_TARGET_MISMATCH', '不能将另一环境或 Agent 的身份用于当前请求。')
            state['target'] = identity
            auth = state.get('auth')
            if not auth:
                auth = self.http('POST', '/api/v2/identity/guests', {})
            elif auth['access_expires_at'] <= time.time() * 1000 + 30000:
                try:
                    auth = self.http('POST', '/api/v2/identity/tokens:refresh', {'refresh_token': auth['refresh_token']})
                except ClientError:
                    raise ClientError('IDENTITY_EXPIRED', '原身份刷新失败，保留原会话；不要自动换身份或重发任务。') from None
            if not isinstance(auth, dict) or not auth.get('access_token') or not auth.get('refresh_token') or not isinstance(auth.get('access_expires_at'), (int, float)):
                raise ClientError('INVALID_IDENTITY', '身份接口未返回完整凭据。')
            state['auth'] = auth
            self.store.save(state)
            return auth['access_token']

    def api(self, method, path, body=None, headers=None):
        return self.http(method, path, body, token=self.token(), headers=headers)

    def conversation(self, key):
        with self.store.locked() as state:
            target = {'origin': self.origin, 'agent_id': self.agent_id, 'subject': self.subject}
            if state.get('target', target) != target:
                raise ClientError('STATE_TARGET_MISMATCH', '不能将另一用户或环境的身份用于当前请求。')
            value = state['conversations'].get(key)
            if not value:
                raise ClientError('NO_CONVERSATION', '该本地会话不存在，请先 send。')
            return json.loads(json.dumps(value))

    @staticmethod
    def path(session_id, suffix=''):
        return '/api/v2/sessions/' + parse.quote(session_id, safe='') + suffix

    def send(self, key, text, wait=True, timeout=120):
        if not text.strip() or len(text.encode()) > 1024 * 1024:
            raise ClientError('INVALID_TEXT', '消息不能为空或超过 1 MiB。')
        authorization = self.complete_authorization(key)
        if authorization is not None:
            return authorization
        token = self.token()
        with self.store.locked() as state:
            value = state['conversations'].get(key)
            if value and value.get('pending'):
                raise ClientError('PENDING_INPUT', '当前会话仍有未核对请求，请先 resume 或 cancel。')
            if not value:
                result = self.http('POST', '/api/v2/sessions', {'agent_id': self.agent_id, 'title': '外部 Agent 会话', 'client_id': 'filtalgo-public-skill'}, token=token)
                session_id = result.get('id') or result.get('session_id')
                if not isinstance(session_id, str) or not session_id:
                    raise ClientError('INVALID_SESSION', '创建会话未返回有效 ID。')
                value = {'id': session_id}
                state['conversations'][key] = value
                start_revision = 0
            else:
                snapshot = self.http('GET', self.path(value['id'], '/documents?limit=1'), token=token)
                start_revision = snapshot.get('revision')
                if not isinstance(start_revision, int) or start_revision < 0:
                    raise ClientError('INVALID_CURSOR', '无法取得本轮开始前的文档边界。')
            value['pending'] = {'request_id': 'skill-' + uuid.uuid4().hex, 'text': text, 'mode': 'prompt', 'start_revision': start_revision}
            self.store.save(state)  # persist the exact identity and payload BEFORE submission
        self.submit(key)
        return self.wait(key, timeout) if wait else {'ok': True, 'status': 'accepted', 'conversation': key}

    def submit(self, key):
        value = self.conversation(key)
        payload = {k: value['pending'][k] for k in ('request_id', 'text', 'mode')}
        return self.api('POST', self.path(value['id'], '/inputs'), payload, {'Prefer': 'respond-async'})

    def resume(self, key, timeout=120):
        value = self.conversation(key)
        if not value.get('pending'):
            if value.get('authorization'):
                return {'ok': True, 'status': 'authorization_required', 'conversation': key, 'authorization_url': value['authorization']['url'], 'message': '请打开链接完成商城授权，然后发送新消息。'}
            if value.get('last_status') == 'authorization_completed':
                return {'ok': True, 'status': 'idle', 'conversation': key}
            if not value.get('last_request_id'):
                return {'ok': True, 'status': 'idle', 'conversation': key}
            value['pending'] = {'request_id': value['last_request_id'], 'start_revision': value.get('last_start_revision', 0)}
            return self.wait(key, timeout, value=value)
        try:
            self.result(value)
        except ClientError as exc:
            if exc.code != 'HTTP_404':
                raise
            self.submit(key)  # ONLY the stored request id and identical payload
        return self.wait(key, timeout)

    def result(self, value):
        rid = parse.quote(value['pending']['request_id'], safe='')
        return self.api('GET', self.path(value['id'], '/inputs/' + rid + '/result'))

    def documents(self, session_id, request_id):
        documents = []; cursor = 0
        while True:
            page = self.api('GET', self.path(session_id, '/documents?after_order=' + str(cursor) + '&limit=20'))
            documents.extend(d for d in page['documents'] if not d.get('deleted'))
            next_cursor = page.get('next_cursor')
            if next_cursor is None:
                return documents
            if not isinstance(next_cursor, int) or next_cursor <= cursor:
                raise ClientError('INVALID_CURSOR', '会话文档分页游标无效。')
            cursor = next_cursor

    def complete_authorization(self, key):
        with self.store.authorization_lock(key):
            return self._complete_authorization_locked(key)

    def _complete_authorization_locked(self, key):
        with self.store.locked() as state:
            target = {'origin': self.origin, 'agent_id': self.agent_id, 'subject': self.subject}
            if state.get('target', target) != target:
                raise ClientError('STATE_TARGET_MISMATCH', '不能将另一用户或环境的身份用于当前请求。')
            conversation = state['conversations'].get(key) or {}
            pending = conversation.get('authorization')
            if not pending:
                return None
            pending = dict(pending)
        if pending['expires_at'] <= time.time() * 1000:
            if pending.get('poll_attempted'):
                path = '/api/v2/delegations/authorization-requests/' + parse.quote(pending['id'], safe='')
                status = self.api('GET', path)
                if isinstance(status, dict) and status.get('status') == 'completed' and status.get('delegation_id'):
                    with self.store.locked() as state:
                        conversation = state['conversations'].get(key) or {}
                        if conversation.get('authorization', {}).get('id') == pending['id']:
                            conversation.pop('authorization', None)
                            conversation['last_status'] = 'authorization_completed'
                            self.store.save(state)
                    return None
            with self.store.locked() as state:
                conversation = state['conversations'].get(key) or {}
                if conversation.get('authorization', {}).get('id') == pending['id']:
                    conversation.pop('authorization', None)
                    self.store.save(state)
            raise ClientError('AUTHORIZATION_EXPIRED', '授权已过期，请重新发起业务请求获取新链接。')
        if pending.get('next_poll_at', 0) > time.time() * 1000:
            return {'ok': True, 'status': 'authorization_required', 'conversation': key, 'authorization_url': pending['url'], 'message': '请先完成商城授权，再发送消息。'}
        path = '/api/v2/delegations/authorization-requests/' + parse.quote(pending['id'], safe='')
        with self.store.locked() as state:
            current = (state['conversations'].get(key) or {}).get('authorization')
            if current and current.get('id') == pending['id']:
                current['poll_attempted'] = True
                self.store.save(state)
        try:
            result = self.api('POST', path + '/device/poll', {'state': pending['state'], 'exchange': pending['exchange']})
        except ClientError as exc:
            if exc.code != 'HTTP_409':
                raise
            status = self.api('GET', path)
            if not isinstance(status, dict) or status.get('status') != 'completed' or not status.get('delegation_id'):
                if not isinstance(status, dict) or status.get('status') not in ('expired', 'denied', 'revoked', 'cancelled'):
                    raise ClientError('AUTHORIZATION_UNCERTAIN', '授权状态尚未确认，请稍后重试；如已明确拒绝授权，可执行 auth-reset 后重新发起。') from None
                with self.store.locked() as state:
                    conversation = state['conversations'].get(key) or {}
                    if conversation.get('authorization', {}).get('id') == pending['id']:
                        conversation.pop('authorization', None)
                        self.store.save(state)
                raise ClientError('AUTHORIZATION_FAILED', '授权已失效或被拒绝，请重新发起业务请求。') from None
            result = {'status': 'active'}
        if not isinstance(result, dict):
            raise ClientError('INVALID_RESPONSE', '授权状态响应无效。')
        if result.get('status') in ('authorization_pending', 'slow_down'):
            interval = result.get('interval', pending.get('interval', 5))
            if not isinstance(interval, int) or isinstance(interval, bool) or not 1 <= interval <= 300:
                interval = 5
            with self.store.locked() as state:
                conversation = state['conversations'].get(key) or {}
                current = conversation.get('authorization')
                if current and current.get('id') == pending['id']:
                    current['interval'] = interval
                    current['next_poll_at'] = int(time.time() * 1000) + interval * 1000
                    self.store.save(state)
            return {'ok': True, 'status': 'authorization_required', 'conversation': key, 'authorization_url': pending['url'], 'message': '请先完成商城授权，再发送消息。'}
        if result.get('status') != 'active':
            raise ClientError('AUTHORIZATION_FAILED', '授权未完成，请重新发起业务请求。')
        with self.store.locked() as state:
            conversation = state['conversations'].get(key) or {}
            if conversation.get('authorization', {}).get('id') == pending['id']:
                conversation.pop('authorization', None)
                conversation['last_status'] = 'authorization_completed'
                self.store.save(state)
        return None

    def start_authorization(self, key, doc):
        with self.store.authorization_lock(key):
            return self._start_authorization_locked(key, doc)

    def _start_authorization_locked(self, key, doc):
        with self.store.locked() as local:
            existing = (local['conversations'].get(key) or {}).get('authorization')
            if existing and existing.get('expires_at', 0) > time.time() * 1000:
                return {'ok': True, 'status': 'authorization_required', 'conversation': key, 'authorization_url': existing['url'], 'message': '请打开链接完成商城授权，然后发送新消息。'}
        value = doc.get('value')
        if not isinstance(value, dict) or value.get('provider') != 'filtmall':
            raise ClientError('INVALID_AUTHORIZATION', '授权请求无效。')
        identifier, state_value = value.get('id'), value.get('state')
        if not isinstance(identifier, str) or not identifier or not isinstance(state_value, str) or not state_value:
            raise ClientError('INVALID_AUTHORIZATION', '授权请求不完整。')
        path = '/api/v2/delegations/authorization-requests/' + parse.quote(identifier, safe='') + '/device'
        result = self.api('POST', path, {'state': state_value})
        if not isinstance(result, dict):
            raise ClientError('INVALID_AUTHORIZATION', '授权接口响应无效。')
        url = result.get('verification_uri_complete'); parsed = parse.urlsplit(url) if isinstance(url, str) else None
        if not parsed or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ClientError('INVALID_AUTHORIZATION', '授权链接无效。')
        if not isinstance(result.get('exchange'), str) or not result['exchange'] or not isinstance(result.get('expires_at'), int):
            raise ClientError('INVALID_AUTHORIZATION', '授权接口响应不完整。')
        with self.store.locked() as local:
            conversation = local['conversations'].get(key)
            if not conversation:
                raise ClientError('NO_CONVERSATION', '会话不存在。')
            interval = result.get('interval', 5)
            if not isinstance(interval, int) or isinstance(interval, bool) or not 1 <= interval <= 300:
                interval = 5
            conversation['authorization'] = {'id': identifier, 'state': state_value, 'exchange': result['exchange'], 'expires_at': result['expires_at'], 'url': url, 'interval': interval, 'next_poll_at': int(time.time() * 1000) + interval * 1000}
            self.store.save(local)
        return {'ok': True, 'status': 'authorization_required', 'conversation': key, 'authorization_url': url, 'message': '请打开链接完成商城授权，然后发送新消息。'}

    def wait(self, key, timeout, value=None):
        value = value or self.conversation(key); deadline = time.monotonic() + timeout
        while True:
            result = self.result(value); execution = result.get('execution_result') or {}
            status = execution.get('operation_status')
            if status is None and result.get('status') == 'cancelled':
                status = 'cancelled'  # accepted input cancelled by Control before execution
            if status in ('completed', 'cancelled', 'waiting', 'failed'):
                docs = self.documents(value['id'], value['pending']['request_id'])
                request_id = value['pending']['request_id']
                status_doc = next((d for d in docs if d.get('kind') == 'request.status' and d.get('request_id') == request_id), {})
                status_value = status_doc.get('value')
                valid_status = status_doc.get('schema_version') == 1 and isinstance(status_value, dict) and 'answer_document_id' in status_value
                answer_id = status_value.get('answer_document_id') if valid_status else None
                answer = next((d for d in docs if isinstance(answer_id, str) and answer_id and d.get('document_id') == answer_id), None)
                if answer is not None:
                    content = answer.get('value')
                    if answer.get('kind') != 'message' or answer.get('schema_version') != 1 or answer.get('request_id') not in (None, request_id) or not isinstance(content, dict) or content.get('role') != 'assistant' or not isinstance(content.get('content'), str):
                        answer = None
                if valid_status and answer_id is None and status == 'completed':
                    # The deployed Shopping release can publish public text without a
                    # canonical message. Never recover such text from an older turn.
                    baseline = value['pending'].get('start_revision')
                    texts = []
                    if isinstance(baseline, int):
                        for document in sorted(docs, key=lambda d: d.get('display_order', 0)):
                            public = document.get('value')
                            if document.get('kind') == 'filtalgo.shopping.text' and document.get('schema_version') == 1 and document.get('request_id') in (None, request_id) and isinstance(document.get('revision'), int) and document['revision'] > baseline and isinstance(public, dict) and isinstance(public.get('content'), str) and public['content'].strip() and public['content'] not in texts:
                                texts.append(public['content'])
                    if texts:
                        answer = {'kind': 'filtalgo.shopping.text', 'schema_version': 1, 'source': 'current-turn-public-text', 'value': {'content': '\n\n'.join(texts)}}
                context = [d for d in docs if str(d.get('kind', '')).startswith('filtalgo.shopping.block:') or d.get('kind') in ('filtalgo.shopping.authorization', 'filtalgo.commerce.authorization')]
                baseline = value['pending'].get('start_revision')
                challenges = [d for d in context if d.get('kind') in ('filtalgo.shopping.authorization', 'filtalgo.commerce.authorization') and d.get('schema_version') == 1 and d.get('request_id') in (None, request_id) and isinstance(baseline, int) and isinstance(d.get('revision'), int) and d['revision'] > baseline]
                challenges.sort(key=lambda d: d['revision'])
                authorization = self.start_authorization(key, challenges[-1]) if status == 'waiting' and challenges else None
                context = [d for d in context if d.get('kind') not in ('filtalgo.shopping.authorization', 'filtalgo.commerce.authorization')]
                selectors = [d for d in docs if d.get('kind') == 'filtalgo.commerce.region_selector' and d.get('schema_version') == 1 and d.get('request_id') in (None, request_id) and isinstance(baseline, int) and isinstance(d.get('revision'), int) and d['revision'] > baseline]
                selectors.sort(key=lambda d: d['revision'])
                result = {'ok': status in ('completed', 'waiting'), 'status': status, 'conversation': key, 'answer': answer, 'context_documents': context}
                if status == 'completed' and selectors:
                    latest = selectors[-1]['value']
                    group_id, part_count = latest.get('group_id'), latest.get('part_count')
                    if not isinstance(group_id, str) or not isinstance(part_count, int) or isinstance(part_count, bool) or not 1 <= part_count <= 16:
                        raise ClientError('INVALID_REGION_SELECTOR', '地区选择器数据不完整。')
                    group = [d.get('value') for d in selectors if isinstance(d.get('value'), dict) and d['value'].get('group_id') == group_id]
                    if len(group) != part_count or any(x.get('part_count') != part_count for x in group):
                        raise ClientError('INVALID_REGION_SELECTOR', '地区选择器数据不完整。')
                    group.sort(key=lambda x: x.get('part_index', -1))
                    if [x.get('part_index') for x in group] != list(range(part_count)) or any(x.get('schema') != latest.get('schema') or x.get('columns') != latest.get('columns') or x.get('encoding') != latest.get('encoding') or x.get('count') != latest.get('count') or x.get('root_id') != latest.get('root_id') or not isinstance(x.get('data'), str) for x in group):
                        raise ClientError('INVALID_REGION_SELECTOR', '地区选择器数据不完整。')
                    result['region_selector'] = decode_region_selector({'value': {**latest, 'data': ''.join(x['data'] for x in group)}})
                selector_errors = [d for d in docs if d.get('kind') == 'filtalgo.commerce.region_selector_error' and d.get('schema_version') == 1 and d.get('request_id') in (None, request_id) and isinstance(baseline, int) and isinstance(d.get('revision'), int) and d['revision'] > baseline]
                if status == 'completed' and selector_errors and not selectors:
                    result.update({'ok': False, 'presentation_status': 'failed', 'error': {'code': 'REGION_SELECTOR_UNAVAILABLE', 'message': '地区选择器暂时不可用，请稍后重试。'}})
                current_context = [d for d in context if d.get('request_id') in (None, request_id) and isinstance(baseline, int) and isinstance(d.get('revision'), int) and d['revision'] > baseline]
                if status == 'completed' and not answer and not current_context and not selectors and not selector_errors:
                    result.update({'ok': False, 'presentation_status': 'failed', 'error': {'code': 'NO_PUBLIC_RESPONSE', 'message': '本轮没有可展示的结果，请稍后重试。'}})
                with self.store.locked() as state:
                    current = state['conversations'].get(key)
                    if current and current.get('pending', {}).get('request_id') == value['pending']['request_id']:
                        current.pop('pending'); current['last_status'] = result['status']
                        current['last_request_id'] = value['pending']['request_id']
                        current['last_start_revision'] = value['pending'].get('start_revision', 0)
                        self.store.save(state)
                if authorization:
                    return authorization
                return result
            if time.monotonic() >= deadline:
                raise ClientError('PENDING_INPUT', '尚未取得执行终态，已保存原请求；请 resume，不要重新 send。')
            time.sleep(1)


    def cancel(self, key):
        value = self.conversation(key)
        if not value.get('pending'):
            return {'ok': True, 'status': 'idle', 'conversation': key}
        rid = parse.quote(value['pending']['request_id'], safe='')
        result = self.api('POST', self.path(value['id'], '/inputs/' + rid + '/interrupt'), {})
        return {'ok': True, 'status': result.get('status'), 'conversation': key, 'next_step': 'resume to confirm terminal status'}

    def clear(self, key):
        value = self.conversation(key)
        if value.get('pending'):
            raise ClientError('PENDING_INPUT', '清空前先 cancel，再 resume 确认终态。')
        self.api('DELETE', self.path(value['id']))
        with self.store.locked() as state:
            state['conversations'].pop(key, None); self.store.save(state)
        return {'ok': True, 'status': 'cleared', 'conversation': key}

    def reset_authorization(self, key):
        self.conversation(key)
        with self.store.authorization_lock(key):
            with self.store.locked() as state:
                conversation = state['conversations'].get(key)
                if not conversation:
                    raise ClientError('NO_CONVERSATION', '该本地会话不存在。')
                conversation.pop('authorization', None)
                self.store.save(state)
        return {'ok': True, 'status': 'authorization_reset', 'conversation': key}


def main():
    defaults = json.loads(Path(__file__).resolve().parents[1].joinpath('defaults.json').read_text())
    parser = argparse.ArgumentParser(description='通过公开访客接口委托筛电 Agent；默认生产环境，不需要 AK/SK。')
    parser.add_argument('command', choices=['send', 'resume', 'cancel', 'clear', 'status', 'auth-reset'])
    parser.add_argument('--conversation', required=True, help='宿主为当前用户当前对话生成的独立本地标识')
    parser.add_argument('--user-key', default='local', help='多用户宿主必须使用可信的独立用户标识')
    parser.add_argument('--control-url', default=None)
    parser.add_argument('--agent-id', default=None)
    parser.add_argument('--state-dir', default=None)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--no-wait', action='store_true')
    args = parser.parse_args()
    if not 0 < args.timeout <= 600:
        raise ClientError('INVALID_TIMEOUT', 'timeout 必须大于 0 且不超过 600 秒。')
    if bool(args.control_url) != bool(args.agent_id):
        raise ClientError('TARGET_REQUIRED', '切换环境时必须同时指定 --control-url 和 --agent-id。')
    origin = args.control_url or defaults['control_url']; agent = args.agent_id or defaults['agent_id']
    namespace = hashlib.sha256((origin + '\0' + agent + '\0' + args.user_key).encode()).hexdigest()
    directory = Path(args.state_dir) if args.state_dir else Path.home() / '.local/state/filtalgo-agent' / namespace
    client = Client(origin, agent, Store(directory), user_key=args.user_key)
    if args.command == 'send':
        result = client.send(args.conversation, sys.stdin.read(), not args.no_wait, args.timeout)
    elif args.command == 'resume': result = client.resume(args.conversation, args.timeout)
    elif args.command == 'cancel': result = client.cancel(args.conversation)
    elif args.command == 'clear': result = client.clear(args.conversation)
    elif args.command == 'auth-reset': result = client.reset_authorization(args.conversation)
    else:
        value = client.conversation(args.conversation)
        result = {'ok': True, 'status': 'pending' if value.get('pending') else value.get('last_status', 'idle'), 'conversation': args.conversation}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except ClientError as exc:
        print(json.dumps({'ok': False, 'error': {'code': exc.code, 'message': str(exc)}}, ensure_ascii=False))
        sys.exit(1)
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({'ok': False, 'error': {'code': 'INVALID_STATE_OR_RESPONSE', 'message': '本地状态或服务响应不完整；保留原会话，不输出凭据或自动换身份。'}}, ensure_ascii=False))
        sys.exit(1)
