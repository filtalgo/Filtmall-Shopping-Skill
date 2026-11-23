#!/usr/bin/env python3
"""Public Control guest client used by scripts/service.py. Standard library only; no channel secrets."""
from contextlib import contextmanager
import hashlib
import base64
import gzip
import io
import zlib
import json
import os
import re
from pathlib import Path
import tempfile
import time
from urllib import error, parse, request
import uuid
import address_cards
import logistics_cards
import customer_service_cards


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
                    state = json.loads(self.path.read_text(encoding='utf8'))
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
    def __init__(self, origin, agent_id, store, transport=None, user_key='local', host='default'):
        url = parse.urlsplit(origin)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
            raise ClientError('INVALID_ORIGIN', 'Control 地址必须是明确的 HTTPS 根地址。')
        if not agent_id or not agent_id.strip():
            raise ClientError('INVALID_AGENT', '需要明确的目标 Agent。')
        self.origin = origin.rstrip('/')
        self.agent_id = agent_id
        self.host = host
        self.subject = hashlib.sha256(user_key.encode()).hexdigest()
        self.store = store
        self.http = transport or HTTP(self.origin)

    @property
    def client_id(self):
        """会话级客户端标识随 host 变化（host 在请求解析后才确定）。"""
        return self.client_identifier(self.host)

    @staticmethod
    def client_identifier(host):
        """会话级客户端标识：filtalgo.skill.<host>，满足远端的字符与长度约束。"""
        value = re.sub(r'[^A-Za-z0-9_.:-]+', '-', str(host or '')).strip('-')[:40]
        return 'filtalgo.skill.' + (value or 'default')

    def locked_host(self, key):
        """读取该会话已锁定的宿主；不存在返回 None。"""
        with self.store.locked() as state:
            table = state.get('hosts')
            value = table.get(key) if isinstance(table, dict) else None
            return value if isinstance(value, str) and value else None

    def remember_host(self, key, host):
        """首次确定后锁定该会话的宿主，后续请求不再覆盖。"""
        if not isinstance(key, str) or not key or not isinstance(host, str) or not host:
            return
        with self.store.locked() as state:
            table = state.get('hosts')
            if not isinstance(table, dict):
                table = {}
                state['hosts'] = table
            if not table.get(key):
                table[key] = host
                self.store.save(state)

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

    def carried_product_documents(self, session_id, request_id, baseline, limit=5):
        """追问轮没有新商品块时，从会话库取本轮基线之前最近一组商品块。"""
        if type(baseline) is not int or baseline < 0:
            return []
        try:
            documents = self.documents(session_id, request_id)
        except ClientError:
            return []
        blocks = [d for d in documents
                  if str(d.get('kind', '')).startswith('filtalgo.shopping.block:')
                  and isinstance(d.get('revision'), int) and d['revision'] <= baseline
                  and isinstance(d.get('request_id'), str)]
        if not blocks:
            return []
        groups = {}
        for document in blocks:
            groups.setdefault(document['request_id'], []).append(document)
        latest_key = max(groups, key=lambda key: max(d['revision'] for d in groups[key]))
        members = sorted(groups[latest_key], key=lambda d: d.get('display_order', 0))
        return members[:limit]

    def send(self, key, text, wait=True, timeout=120, allow_repeat=False, force=False):
        if not text.strip() or len(text.encode()) > 1024 * 1024:
            raise ClientError('INVALID_TEXT', '消息不能为空或超过 1 MiB。')
        try:
            current = self.conversation(key)
        except ClientError as exc:
            if exc.code != 'NO_CONVERSATION':
                raise
            current = {}
        self._guard_authorization_resume(current)
        if not force and self._needs_resume(current):
            raise ClientError('RESUME_REQUIRED', '上一条请求的终态未确认（%s）；请先 resume 核对，确认后再发送新消息。'
                              % (current['last_error'].get('code') or '结果未知'))
        token = self.token()
        with self.store.locked() as state:
            value = state['conversations'].get(key)
            if not isinstance(value, dict):
                value = None
            if value:
                self._guard_authorization_resume(value)
                if value.get('pending'):
                    raise ClientError('PENDING_INPUT', '当前会话仍有未核对请求，请先 resume 或 cancel。')
            if not value:
                result = self.http('POST', '/api/v2/sessions', {'agent_id': self.agent_id, 'title': '外部 Agent 会话', 'client_id': self.client_id}, token=token)
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
            value['last_payload'] = text
            value.pop('last_error', None)
            self.store.save(state)  # persist the exact identity and payload BEFORE submission
        try:
            self.submit(key)
        except ClientError as exc:
            pending = self.conversation(key).get('pending') or {}
            if pending.get('request_id'):
                self.record_error(key, pending['request_id'], exc.code)
            raise
        return self.wait(key, timeout) if wait else {'ok': True, 'status': 'accepted', 'conversation': key}

    def submit(self, key):
        value = self.conversation(key)
        pending = value.get('pending')
        if not isinstance(pending, dict) or not pending.get('request_id'):
            raise ClientError('PENDING_LOST', '本地没有待提交请求；确认是否已提交前只用 resume，不要重新 send。')
        payload = {k: pending[k] for k in ('request_id', 'text', 'mode')}
        return self.api('POST', self.path(value['id'], '/inputs'), payload, {'Prefer': 'respond-async'})

    @staticmethod
    def _guard_authorization_resume(value):
        if value.get('authorization') or (value.get('pending') or {}).get('authorization_resume'):
            raise ClientError('RESUME_REQUIRED', '请先用 resume 恢复授权后的原请求；本条新消息未提交。确认原请求终态后，再发送本条消息。')

    @staticmethod
    def _needs_resume(value):
        """上一条请求是否停在未知态：需要先 resume 确认，才允许再发新消息。"""
        pending = value.get('pending')
        return isinstance(pending, dict) and bool(pending.get('request_id')) and 'last_error' in value

    def resume(self, key, timeout=120):
        value = self.conversation(key)
        if value.get('authorization'):
            result = self.complete_authorization(key, time.monotonic() + max(0, timeout))
            if result is not None:
                return result
            value = self.conversation(key)
        pending = value.get('pending') or {}
        if pending.get('authorization_resume') and pending.get('baseline_pending'):
            snapshot = self.api('GET', self.path(value['id'], '/documents?limit=1'))
            revision = snapshot.get('revision') if isinstance(snapshot, dict) else None
            if type(revision) is not int or revision < 0:
                raise ClientError('INVALID_CURSOR', '无法确认继续请求的文档边界；保留原请求。')
            with self.store.locked() as state:
                current = (state['conversations'].get(key) or {}).get('pending') or {}
                if current.get('request_id') == pending.get('request_id') and current.get('baseline_pending'):
                    current['start_revision'] = revision
                    current.pop('baseline_pending', None)
                    self.store.save(state)
            value = self.conversation(key)
        if not value.get('pending'):
            if value.get('authorization'):
                return {'ok': True, 'status': 'authorization_required', 'conversation': key, 'authorization_url': value['authorization']['url'], 'message': '请打开链接完成商城授权，然后用 resume 恢复原请求。'}
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
                self.record_error(key, value['pending']['request_id'], exc.code)
                raise
            try:
                self.submit(key)  # ONLY the stored request id and identical payload
            except ClientError as again:
                self.record_error(key, value['pending']['request_id'], again.code)
                raise
        return self.wait(key, timeout)

    def result(self, value):
        rid = parse.quote(value['pending']['request_id'], safe='')
        return self.api('GET', self.path(value['id'], '/inputs/' + rid + '/result'))

    def documents(self, session_id, request_id, after_revision=None):
        incremental = type(after_revision) is int and after_revision >= 0
        cursor = after_revision if incremental else 0
        parameter = 'after_revision' if incremental else 'after_order'
        documents = {}
        for _ in range(100):
            page = self.api('GET', self.path(session_id, '/documents?' + parameter + '=' + str(cursor) + '&limit=200'))
            revision = page.get('revision')
            if incremental and (type(revision) is not int or revision < cursor):
                raise ClientError('INVALID_CURSOR', '会话文档版本异常，保留原请求并使用 resume 核对。')
            for document in page['documents']:
                document_id = document.get('document_id')
                if not isinstance(document_id, str) or not document_id:
                    raise ClientError('INVALID_RESPONSE', '会话文档缺少标识。')
                previous = documents.get(document_id)
                if previous is None or document.get('revision', 0) > previous.get('revision', 0):
                    documents[document_id] = document
            next_cursor = page.get('next_cursor')
            if next_cursor is None:
                return [d for d in documents.values() if not d.get('deleted')]
            if type(next_cursor) is not int or next_cursor <= cursor or (incremental and next_cursor > revision):
                raise ClientError('INVALID_CURSOR', '会话文档分页游标无效。')
            cursor = next_cursor
        raise ClientError('DOCUMENT_LIMIT', '会话文档过多，保留原请求并使用 resume 核对。')

    def complete_authorization(self, key, deadline=None):
        with self.store.authorization_lock(key):
            return self._complete_authorization_locked(key, deadline)

    def _complete_authorization_locked(self, key, deadline=None):
        with self.store.locked() as state:
            target = {'origin': self.origin, 'agent_id': self.agent_id, 'subject': self.subject}
            if state.get('target', target) != target:
                raise ClientError('STATE_TARGET_MISMATCH', '不能将另一用户或环境的身份用于当前请求。')
            conversation = state['conversations'].get(key) or {}
            pending = conversation.get('authorization')
            if not pending:
                return None
            pending = dict(pending)
        if pending.get('completion_verified') is True:
            return self.finish_authorization(key, pending['id'], {'id': pending.get('completed_delegation_id')})
        if pending['expires_at'] <= time.time() * 1000:
            if pending.get('poll_attempted'):
                recovered = self.recover_authorization_completion(pending)
                if recovered is not None:
                    return self.finish_authorization(key, pending['id'], recovered)
                path = '/api/v2/delegations/authorization-requests/' + parse.quote(pending['id'], safe='')
                status = self.api('GET', path)
                if isinstance(status, dict) and status.get('status') == 'completed' and status.get('delegation_id'):
                    return self.finish_authorization(key, pending['id'], {'id': status['delegation_id']})
            with self.store.locked() as state:
                conversation = state['conversations'].get(key) or {}
                if conversation.get('authorization', {}).get('id') == pending['id']:
                    conversation.pop('authorization', None)
                    self.store.save(state)
            raise ClientError('AUTHORIZATION_EXPIRED', '授权已过期，请重新发起业务请求获取新链接。')
        if pending.get('next_poll_at', 0) > time.time() * 1000:
            return {'ok': True, 'status': 'authorization_required', 'conversation': key, 'authorization_url': pending['url'], 'message': '请先完成商城授权，再用 resume 恢复原请求。'}
        path = '/api/v2/delegations/authorization-requests/' + parse.quote(pending['id'], safe='')
        with self.store.locked() as state:
            current = (state['conversations'].get(key) or {}).get('authorization')
            if current and current.get('id') == pending['id']:
                current['poll_attempted'] = True
                self.store.save(state)
        try:
            result = self.api('POST', path + '/device/poll', {'state': pending['state'], 'exchange': pending['exchange']})
        except ClientError as exc:
            if exc.code not in ('HTTP_401', 'HTTP_409', 'IDENTITY_EXPIRED'):
                raise
            recovered = self.recover_authorization_completion(pending)
            if recovered is not None:
                return self.finish_authorization(key, pending['id'], recovered)
            if exc.code != 'HTTP_409':
                raise ClientError('AUTHORIZATION_UNCERTAIN', '授权响应尚未恢复，请保留状态后重试 resume。') from None
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
            result = {'status': 'active', 'id': status['delegation_id']}
        if not isinstance(result, dict):
            raise ClientError('INVALID_RESPONSE', '授权状态响应无效。')
        if result.get('status') in ('authorization_pending', 'slow_down'):
            interval = result.get('interval', pending.get('interval', 5))
            if not isinstance(interval, int) or isinstance(interval, bool) or not 1 <= interval <= 300:
                interval = 5
            previous_interval = pending.get('interval', 5)
            if result.get('status') == 'slow_down' and isinstance(previous_interval, int) and not isinstance(previous_interval, bool) and 1 <= previous_interval <= 300:
                interval = min(max(interval, previous_interval + 5), 300)
            pending['interval'] = interval
            with self.store.locked() as state:
                conversation = state['conversations'].get(key) or {}
                current = conversation.get('authorization')
                if current and current.get('id') == pending['id']:
                    current['interval'] = interval
                    current['next_poll_at'] = int(time.time() * 1000) + interval * 1000
                    self.store.save(state)
            if self.poll_granted(pending, deadline, key=key):
                return self.finish_authorization(key, pending['id'])
            with self.store.locked() as state:
                current = (state['conversations'].get(key) or {}).get('authorization')
                if current and current.get('id') == pending['id']:
                    current['interval'] = pending['interval']
                    current['next_poll_at'] = int(time.time() * 1000) + pending['interval'] * 1000
                    self.store.save(state)
            return {'ok': True, 'status': 'authorization_required', 'conversation': key, 'authorization_url': pending['url'], 'message': '请先完成商城授权，再用 resume 恢复原请求。'}
        if result.get('status') != 'active':
            raise ClientError('AUTHORIZATION_FAILED', '授权未完成，请重新发起业务请求。')
        return self.finish_authorization(key, pending['id'], result)

    def poll_granted(self, pending, deadline, key=None):
        """授权可能在首次 poll 返回 pending 之后才回写；在同一个授权请求上继续轮询，
        避免用户刚确认就被当成未授权而重建请求、丢掉已完成的授权。"""
        if deadline is None:
            return False
        path = '/api/v2/delegations/authorization-requests/' + parse.quote(pending['id'], safe='')
        interval = pending.get('interval', 5)
        if not isinstance(interval, int) or isinstance(interval, bool) or not 1 <= interval <= 300:
            interval = 5
        while time.monotonic() + interval <= deadline:
            time.sleep(interval)
            try:
                result = self.api('POST', path + '/device/poll',
                                  {'state': pending['state'], 'exchange': pending['exchange']})
            except ClientError as exc:
                if exc.code in ('HTTP_401', 'HTTP_409', 'IDENTITY_EXPIRED'):
                    recovered = self.recover_authorization_completion(pending)
                    if recovered is not None:
                        if key is not None:
                            self.finish_authorization(key, pending['id'], recovered)
                        return True
                    try:
                        status = self.api('GET', path)
                    except ClientError:
                        return False
                    if isinstance(status, dict) and status.get('status') == 'completed' and status.get('delegation_id'):
                        if key is not None:
                            self.finish_authorization(key, pending['id'], {'status': 'active', 'id': status['delegation_id']})
                        return True
                    return False
                if exc.code != 'HTTP_429':
                    return False
                interval = min(interval + 5, 300)
                pending['interval'] = interval
                continue
            if isinstance(result, dict) and result.get('status') == 'active':
                if key is not None:
                    self.finish_authorization(key, pending['id'], result)
                return True
            if isinstance(result, dict) and result.get('status') in ('authorization_pending', 'slow_down'):
                updated_interval = result.get('interval')
                if isinstance(updated_interval, int) and not isinstance(updated_interval, bool) and 1 <= updated_interval <= 300:
                    interval = max(interval + 5, updated_interval) if result.get('status') == 'slow_down' else updated_interval
                elif result.get('status') == 'slow_down':
                    interval += 5
                interval = min(interval, 300)
                pending['interval'] = interval
            try:
                status = self.api('GET', path)
            except ClientError:
                status = None
            if isinstance(status, dict):
                if status.get('status') == 'completed' and status.get('delegation_id'):
                    if key is not None:
                        self.finish_authorization(key, pending['id'], {'status': 'active', 'id': status['delegation_id']})
                    return True
                if status.get('status') in ('expired', 'denied', 'revoked', 'cancelled'):
                    return False
        return False

    def recover_authorization_completion(self, pending):
        with self.store.locked() as state:
            auth = state.get('auth') or {}
            proof = auth.get('access_token')
        if not proof:
            return None  # compatibility with older platform deployments
        path = '/api/v2/delegations/authorization-requests/' + parse.quote(pending['id'], safe='') + '/completion'
        try:
            # A merge revokes the guest for ordinary APIs. Use its original proof
            # only at the receipt endpoint; do not refresh it or create a guest.
            result = self.http('POST', path, {'state': pending['state']}, token=proof)
        except ClientError as exc:
            if exc.code in ('HTTP_404', 'HTTP_409'):
                return None
            raise
        if not isinstance(result, dict) or result.get('status') != 'active' or not isinstance(result.get('platform_tokens'), dict):
            raise ClientError('INVALID_IDENTITY', '授权完成凭据无效，保留原授权状态。')
        return result

    @staticmethod
    def platform_completion_tokens(result):
        if not isinstance(result, dict) or 'platform_tokens' not in result:
            return None
        value = result['platform_tokens']
        if not isinstance(value, dict):
            raise ClientError('INVALID_IDENTITY', '授权完成凭据无效，保留原授权状态。')
        fields = ('access_token', 'refresh_token', 'principal_id', 'credential_session_id')
        if any(not isinstance(value.get(k), str) or not value[k] or len(value[k]) > 4096 or value[k].strip() != value[k] for k in fields):
            raise ClientError('INVALID_IDENTITY', '授权完成凭据不完整，保留原授权状态。')
        now = time.time() * 1000
        if any(type(value.get(k)) is not int or value[k] <= now for k in ('access_expires_at', 'refresh_expires_at')):
            raise ClientError('INVALID_IDENTITY', '授权完成凭据已失效，保留原授权状态。')
        return {k: value[k] for k in fields + ('access_expires_at', 'refresh_expires_at')}

    def finish_authorization(self, key, identifier, result=None):
        tokens = self.platform_completion_tokens(result)
        with self.store.locked() as state:
            conversation = state['conversations'].get(key) or {}
            if conversation.get('authorization', {}).get('id') != identifier:
                return None
            overlapping = bool(conversation.get('pending'))
            if overlapping:
                # A merged guest cannot inspect ordinary APIs until its new
                # platform identity is persisted. Keep both recovery records.
                if tokens is not None:
                    state['auth'] = tokens
                conversation['authorization']['completion_verified'] = True
                if isinstance(result, dict) and isinstance(result.get('id'), str):
                    conversation['authorization']['completed_delegation_id'] = result['id']
                self.store.save(state)
        if overlapping:
            self.reconcile_authorization_input(key, identifier)
        with self.store.locked() as state:
            conversation = state['conversations'].get(key) or {}
            if conversation.get('authorization', {}).get('id') == identifier:
                if conversation.get('pending'):
                    raise ClientError('PENDING_INPUT', '原请求仍在核对，请保留授权状态并稍后 resume。')
                if tokens is not None:
                    state['auth'] = tokens
                if isinstance(result, dict) and isinstance(result.get('id'), str):
                    conversation['delegation_id'] = result['id']
                conversation.pop('authorization', None)
                conversation['last_status'] = 'authorization_completed'
                if conversation.get('last_request_id'):
                    conversation['pending'] = {
                        'request_id': 'skill-auth-' + hashlib.sha256(identifier.encode()).hexdigest()[:32],
                        'mode': 'prompt', 'authorization_resume': True, 'baseline_pending': True,
                        'authorization_for_request_id': conversation['last_request_id'],
                        'text': '商城授权已完成。请继续刚才因授权暂停的业务请求，先核对已有执行结果；复用已有订单及业务记录，避免重复创建或修改。支付仍由用户在真实支付页完成。',
                    }
                conversation.pop('last_error', None)
                self.store.save(state)
        return None

    def reconcile_authorization_input(self, key, identifier):
        value = self.conversation(key)
        authorization = value.get('authorization') or {}
        pending = value.get('pending') or {}
        request_id = pending.get('request_id')
        if authorization.get('id') != identifier or not pending:
            return
        if not request_id or pending.get('authorization_resume'):
            raise ClientError('AUTHORIZATION_UNCERTAIN', '待核对输入与授权关系不明，保留状态。')
        bound = authorization.get('for_request_id')
        if bound is not None and bound != request_id:
            raise ClientError('AUTHORIZATION_UNCERTAIN', '待核对输入不属于本次授权，保留状态。')
        if bound is None:
            # Older files can contain a challenge saved just before settle.
            # Prove that it belongs to this waiting request; never discard an
            # unrelated input just because another authorization completed.
            response = self.result(value) or {}
            status = (response.get('execution_result') or {}).get('operation_status')
            baseline = pending.get('start_revision')
            if status != 'waiting' or type(baseline) is not int:
                raise ClientError('AUTHORIZATION_UNCERTAIN', '原输入尚未确认因授权暂停，保留状态。')
            documents = self.documents(value['id'], request_id, baseline)
            matched = any(
                doc.get('kind') in ('filtalgo.shopping.authorization', 'filtalgo.commerce.authorization')
                and doc.get('schema_version') == 1 and doc.get('request_id') in (None, request_id)
                and type(doc.get('revision')) is int and doc['revision'] > baseline
                and isinstance(doc.get('value'), dict)
                and doc['value'].get('id') == identifier
                and doc['value'].get('state') == authorization.get('state')
                for doc in documents
            )
            if not matched:
                raise ClientError('AUTHORIZATION_UNCERTAIN', '无法确认原输入对应的授权挑战，保留状态。')
        with self.store.locked() as state:
            current = state['conversations'].get(key) or {}
            if current.get('authorization', {}).get('id') != identifier or current.get('pending') != pending:
                raise ClientError('AUTHORIZATION_UNCERTAIN', '恢复期间输入状态已变化，保留状态。')
            current['last_request_id'] = request_id
            current['last_start_revision'] = pending.get('start_revision', 0)
            current['last_status'] = 'waiting'
            current.pop('pending')
            self.store.save(state)

    def start_authorization(self, key, doc):
        with self.store.authorization_lock(key):
            return self._start_authorization_locked(key, doc)

    def _start_authorization_locked(self, key, doc):
        with self.store.locked() as local:
            existing = (local['conversations'].get(key) or {}).get('authorization')
            if existing and existing.get('expires_at', 0) > time.time() * 1000:
                return {'ok': True, 'status': 'authorization_required', 'conversation': key, 'authorization_url': existing['url'], 'message': '请打开链接完成商城授权，然后用 resume 恢复原请求。'}
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
            pending = conversation.get('pending')
            if pending:
                baseline = pending.get('start_revision')
                if (doc.get('request_id') not in (None, pending.get('request_id'))
                        or type(baseline) is not int or type(doc.get('revision')) is not int
                        or doc['revision'] <= baseline):
                    raise ClientError('AUTHORIZATION_UNCERTAIN', '授权挑战不属于当前待核对输入，保留状态。')
            interval = result.get('interval', 5)
            if not isinstance(interval, int) or isinstance(interval, bool) or not 1 <= interval <= 300:
                interval = 5
            conversation['authorization'] = {'id': identifier, 'state': state_value, 'exchange': result['exchange'], 'expires_at': result['expires_at'], 'url': url, 'interval': interval, 'next_poll_at': int(time.time() * 1000) + interval * 1000}
            if pending:
                conversation['authorization']['for_request_id'] = pending['request_id']
                conversation['last_request_id'] = pending['request_id']
                conversation['last_start_revision'] = pending['start_revision']
                conversation['last_status'] = 'waiting'
                conversation.pop('pending')
            self.store.save(local)
        return {'ok': True, 'status': 'authorization_required', 'conversation': key, 'authorization_url': url, 'message': '请打开链接完成商城授权，然后用 resume 恢复原请求。'}

    def wait(self, key, timeout, value=None):
        value = value or self.conversation(key); deadline = time.monotonic() + timeout
        if not isinstance(value.get('pending'), dict) or not value['pending'].get('request_id'):
            raise ClientError('PENDING_LOST', '等待结果时本地待核对请求已不存在；不要重新 send，先 status 确认会话状态。')
        while True:
            result = self.result(value) or {}; execution = result.get('execution_result') or {}
            status = execution.get('operation_status')
            if status is None and result.get('status') == 'cancelled':
                status = 'cancelled'  # accepted input cancelled by Control before execution
            if status in ('completed', 'cancelled', 'waiting', 'failed'):
                try:
                    return self.settle(key, value, status)
                except ClientError as exc:
                    self.record_error(key, value['pending']['request_id'], exc.code)
                    raise
            if time.monotonic() >= deadline:
                self.record_error(key, value['pending']['request_id'], 'TIMEOUT_WAITING')
                raise ClientError('PENDING_INPUT', '尚未取得执行终态，已保存原请求；请 resume，不要重新 send。')
            time.sleep(1)

    def settle(self, key, value, status):
        request_id = value['pending']['request_id']
        baseline = value['pending'].get('start_revision')
        incremental = type(baseline) is int and baseline >= 0
        try:
            docs = self.documents(value['id'], request_id, baseline) if incremental else self.documents(value['id'], request_id)
        except ClientError as exc:
            if not incremental or exc.code != 'INVALID_CURSOR':
                raise
            docs = self.documents(value['id'], request_id)
            incremental = False
        status_doc = next((d for d in docs if d.get('kind') == 'request.status' and d.get('request_id') == request_id), {})
        ref = status_doc.get('value') if isinstance(status_doc.get('value'), dict) else {}
        answer_ref = ref.get('answer_document_id')
        if incremental and (not status_doc or (isinstance(answer_ref, str) and answer_ref and not any(d.get('document_id') == answer_ref for d in docs))):
            docs = self.documents(value['id'], request_id)
            status_doc = next((d for d in docs if d.get('kind') == 'request.status' and d.get('request_id') == request_id), {})
        status_value = status_doc.get('value')
        valid_status = status_doc.get('schema_version') == 1 and isinstance(status_value, dict) and 'answer_document_id' in status_value
        answer_id = status_value.get('answer_document_id') if valid_status else None
        answer = next((d for d in docs if isinstance(answer_id, str) and answer_id and d.get('document_id') == answer_id), None)
        if answer is not None:
            content = answer.get('value')
            if answer.get('kind') != 'message' or type(answer.get('schema_version')) is not int or answer['schema_version'] not in (1, 2) or answer.get('request_id') not in (None, request_id) or not isinstance(content, dict) or content.get('role') != 'assistant' or not isinstance(content.get('content'), str):
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
        selectors = [d for d in docs if d.get('kind') == 'filtalgo.commerce.region_selector' and d.get('schema_version') == 1 and d.get('request_id') in (None, request_id) and isinstance(baseline, int) and isinstance(d.get('revision'), int) and d['revision'] > baseline]
        selectors.sort(key=lambda d: d['revision'])
        result = {'ok': status in ('completed', 'waiting'), 'status': status, 'conversation': key, 'answer': answer, 'context_documents': context}
        if isinstance(baseline, int) and not any(str(d.get('kind', '')).startswith('filtalgo.shopping.block:') for d in context):
            # 只挂定位信息；真正读库推迟到宿主需要卡片时，避免每轮多一次全量请求。
            result['carry'] = {'session_id': value['id'], 'request_id': request_id, 'baseline': baseline}
        # The cart is a stable, conversation-scoped document. Only its newest
        # revision from this turn is safe to present, including invalidations.
        carts = [d for d in docs if d.get('kind') == 'filtalgo.commerce.cart'
                 and d.get('request_id') in (None, request_id)
                 and type(baseline) is int and type(d.get('revision')) is int
                 and d['revision'] > baseline]
        if carts:
            latest_cart = max(carts, key=lambda d: d['revision'])
            value_cart = latest_cart.get('value')
            if latest_cart.get('schema_version') == 1 and isinstance(value_cart, dict):
                result['cart'] = value_cart
            else:
                result['cart'] = {'status': 'unavailable', 'items': []}
        customer_groups = {}
        for document in docs:
            if (document.get('kind') != 'filtalgo.commerce.customer_service' or document.get('request_id') != request_id
                    or type(baseline) is not int or type(document.get('revision')) is not int or document['revision'] <= baseline):
                continue
            public = document.get('value')
            customer_key = customer_service_cards.group_key(public.get('query')) if isinstance(public, dict) else None
            previous = customer_groups.get(customer_key)
            if previous is None or document['revision'] >= previous['revision']:
                customer_groups[customer_key] = document
        if customer_groups:
            selected = [customer_groups[None]] if None in customer_groups else list(customer_groups.values())
            result['customer_service_snapshots'] = []
            for document in selected:
                public = document.get('value')
                safe = customer_service_cards.unavailable()
                if type(document.get('schema_version')) is int and document['schema_version'] == 1 and customer_service_cards.validate(public):
                    safe = {k: v for k, v in public.items() if k != 'publication'}
                result['customer_service_snapshots'].append(safe)
        logistics = {}
        for document in docs:
            if (document.get('kind') != 'filtalgo.commerce.logistics' or document.get('request_id') != request_id
                    or type(baseline) is not int or type(document.get('revision')) is not int or document['revision'] <= baseline):
                continue
            public = document.get('value')
            query = public.get('query') if isinstance(public, dict) else None
            order = query.get('order_sn') if isinstance(query, dict) else None
            logistics_key = order if logistics_cards.text(order, 256, True) else None
            previous = logistics.get(logistics_key)
            if previous is None or document['revision'] >= previous['revision']:
                logistics[logistics_key] = document
        if logistics:
            selected = [logistics[None]] if None in logistics else list(logistics.values())
            result['logistics_snapshots'] = []
            for document in selected:
                public = document.get('value')
                safe = logistics_cards.unavailable()
                if type(document.get('schema_version')) is int and document['schema_version'] == 1 and logistics_cards.validate(public):
                    safe = {k: public[k] for k in ('status', 'query', 'fetched_at', 'empty_reason', 'reason', 'packages')}
                    if public['status'] == 'current':
                        safe.update({k: public[k] for k in ('authorization_binding', 'authorization_expires_at')})
                result['logistics_snapshots'].append(safe)
        addresses = {}
        for document in docs:
            if (document.get('kind') != 'filtalgo.commerce.addresses' or document.get('request_id') != request_id
                    or type(baseline) is not int or type(document.get('revision')) is not int or document['revision'] <= baseline):
                continue
            public = document.get('value')
            scene = public.get('scene') if isinstance(public, dict) else None
            way = public.get('way') if isinstance(public, dict) else None
            valid_key = (scene == 'address_book' and way is None) or (scene == 'checkout' and address_cards.text(way, 64))
            logical_key = (scene, way) if valid_key else ('invalid', None)
            previous = addresses.get(logical_key)
            if previous is None or document['revision'] >= previous['revision']:
                addresses[logical_key] = document
        if ('invalid', None) in addresses:
            result['address_snapshots'] = [address_cards.unavailable()]
        elif addresses:
            result['address_snapshots'] = []
            for (scene, way), document in addresses.items():
                public = document.get('value')
                safe = address_cards.unavailable(scene, way)
                if type(document.get('schema_version')) is int and document['schema_version'] in (1, 2) and address_cards.validate(public):
                    if public['status'] == 'current':
                        safe = {k: public[k] for k in ('status', 'scene', 'way', 'selection_status', 'selected_address_id', 'page', 'items', 'authorization_binding', 'authorization_expires_at')}
                    else:
                        safe['status'] = public['status']
                result['address_snapshots'].append(safe)
        for kind, field in (('checkout', 'checkouts'), ('after_sale', 'after_sales'), ('after_sale_list', 'after_sale_lists')):
            latest = {}
            for document in docs:
                if (document.get('kind') != 'filtalgo.commerce.' + kind
                        or document.get('request_id') not in (None, request_id)
                        or type(baseline) is not int or type(document.get('revision')) is not int
                        or document['revision'] <= baseline):
                    continue
                identity = document.get('document_id')
                if not isinstance(identity, str) or not identity:
                    continue
                if identity not in latest or document['revision'] > latest[identity]['revision']:
                    latest[identity] = document
            collected = []
            for document in sorted(latest.values(), key=lambda d: (d.get('display_order', 0), d['revision'])):
                if document.get('deleted'):
                    continue
                public = document.get('value')
                collected.append({**document, 'value': public if document.get('schema_version') == 1 and isinstance(public, dict)
                                  else {'status': 'unavailable'}})
            if collected:
                result[field] = collected
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
        result['context_documents'] = [d for d in current_context if d.get('kind') not in ('filtalgo.shopping.authorization', 'filtalgo.commerce.authorization')]
        if status == 'completed' and not answer and not current_context and not selectors and not selector_errors and not any(k in result for k in ('cart', 'address_snapshots', 'logistics_snapshots', 'customer_service_snapshots')) and not any(result.get(k) for k in ('checkouts', 'after_sales', 'after_sale_lists')):
            result.update({'ok': False, 'presentation_status': 'failed', 'error': {'code': 'NO_PUBLIC_RESPONSE', 'message': '本轮没有可展示的结果，请稍后重试。'}})
        with self.store.locked() as state:
            current = state['conversations'].get(key)
            if current and current.get('pending', {}).get('request_id') == value['pending']['request_id']:
                current.pop('pending'); current['last_status'] = status
                current['last_request_id'] = value['pending']['request_id']
                current['last_start_revision'] = value['pending'].get('start_revision', 0)
                current.pop('last_error', None)
                self.store.save(state)
        if authorization:
            return authorization
        return result

    def record_error(self, key, request_id, code):
        """把未结算请求的失败原因落在本地，方便宿主判断该 resume 还是可以重发。"""
        with self.store.locked() as state:
            current = state['conversations'].get(key)
            if current and current.get('pending', {}).get('request_id') == request_id:
                current['last_error'] = {'request_id': request_id, 'code': code}
                self.store.save(state)

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
        # The server session is gone; dropping local state must not strand a stale error marker.
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

    def revoke_authorization(self, key):
        value = self.conversation(key)
        identifier = value.get('delegation_id')
        if not isinstance(identifier, str) or not identifier:
            raise ClientError('NO_DELEGATION', '当前本地会话没有可撤销的已完成授权。')
        self.api('DELETE', '/api/v2/delegations/' + parse.quote(identifier, safe=''))
        with self.store.locked() as state:
            for conversation in state['conversations'].values():
                if conversation.get('delegation_id') == identifier:
                    conversation.pop('delegation_id', None)
                    conversation.pop('authorization', None)
            self.store.save(state)
        return {'ok': True, 'status': 'authorization_revoked', 'conversation': key}

    def logout(self, key):
        self.conversation(key)
        self.api('POST', '/api/v2/identity/logout', {})
        with self.store.locked() as state:
            state['auth'] = None
            state['conversations'] = {}
            self.store.save(state)
        return {'ok': True, 'status': 'logged_out', 'conversation': key}
