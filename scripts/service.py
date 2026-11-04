#!/usr/bin/env python3
"""filtalgo 常驻服务：skill 的唯一入口，每行一个 JSON 请求，每行一个 JSON 应答。

stdin:  {"op":"send","conversation":"...","text":"...","format":"widget"}
        {"op":"resume","conversation":"...","format":"widget"}
        {"op":"cancel"|"clear"|"auth-reset"|"status","conversation":"..."}
        {"op":"ping"}
stdout: {"id":<请求序号>,"ok":true,"status":"completed","card_count":3,"html_file":"...cards.html","answer_file":"...answer.md"}
        {"id":<请求序号>,"ok":false,"error":{"code":"...","message":"..."}}

整轮对话只启动一次，复用同一个 Client、文件锁和本地状态；按行串行处理，应答顺序与请求一致。
每轮成功结果拆成两个文件：商品卡片 HTML（html_file）和 answer 正文（answer_file），应答只回路径。
不会新建身份，也不会在失败后重发。不向 stdout 写日志：诊断信息全部进 stderr。
"""
import argparse
import hashlib
import json
import os
import math
import re
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / 'scripts'))

import cards  # noqa: E402
import client  # noqa: E402

ClientError = client.ClientError

PROTOCOL = 1
FORMATS = ('widget', 'markdown', 'text', 'json')
OPS = ('send', 'resume', 'cancel', 'clear', 'auth-reset', 'status', 'ping')
# 请求里可对单个产物指定完整文件路径，覆盖默认目录命名。
OUTPUT_PATH_KEYS = ('fragment_path', 'page_path', 'answer_path')


def state_directory(args):
    defaults = json.loads(Path(__file__).resolve().parents[1].joinpath('defaults.json').read_text(encoding='utf8'))
    if bool(args.control_url) != bool(args.agent_id):
        raise client.ClientError('TARGET_REQUIRED', '切换环境时必须同时指定 --control-url 和 --agent-id。')
    origin = args.control_url or defaults['control_url']
    agent = args.agent_id or defaults['agent_id']
    namespace = hashlib.sha256((origin + '\0' + agent + '\0' + args.user_key).encode()).hexdigest()
    directory = Path(args.state_dir) if args.state_dir else Path.home() / '.local/state/filtalgo-agent' / namespace
    return origin, agent, directory


def build_client(args):
    origin, agent, directory = state_directory(args)
    return client.Client(origin, agent, client.Store(directory), user_key=args.user_key)


HEARTBEAT = {'started_at': None, 'requests': 0, 'last_request_at': None, 'restarts': 0}


def write_heartbeat(path):
    if not path:
        return
    payload = dict(HEARTBEAT, pid=__import__('os').getpid(), updated_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf8')
    tmp.replace(path)


def run_request(client, request, default_format, default_out_dir=None, heartbeat_path=None):
    """请求放在线程里跑：单次请求崩溃不会带走进程，超时也只影响这一条。"""
    box = {}

    def target():
        try:
            box['ok'] = handle(client, request, default_format, default_out_dir)
        except BaseException as exc:  # 线程里必须兜住所有异常；可预期的 ClientError 不刷栈
            if not isinstance(exc, ClientError):
                traceback.print_exc(file=sys.stderr)
            box['error'] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    previous = sys.gettrace()
    sys.settrace(None)  # 调试器下 join 心跳会让主线程一直不返回
    try:
        while thread.is_alive():
            thread.join(0.5)
            if thread.is_alive() and heartbeat_path:
                try:
                    write_heartbeat(heartbeat_path)
                except OSError:
                    pass  # 不因心跳写入失败丢弃仍在执行的请求
    finally:
        sys.settrace(previous)
    if 'ok' in box:
        return box['ok']
    exc = box.get('error')
    if isinstance(exc, ClientError):
        raise exc
    raise ClientError('INTERNAL_ERROR', '本次请求内部异常（%s）；先 resume 核对，不要重新 send。'
                                    % type(exc).__name__)


def answer_text(result):
    value = (result.get('answer') or {}).get('value') or {}
    content = value.get('content')
    return content if isinstance(content, str) else ''


URL_PATTERN = re.compile(r'https://[^\s<>"\'）)】\]，。；、]+')
PAYMENT_URL_HINT = re.compile(r'cashier|payment|pay|收银台|支付', re.IGNORECASE)


def extract_payment_links(answer):
    """下单答复里若带回收银台链接，单独列出，方便宿主直接展示支付入口。"""
    links = []
    for url in URL_PATTERN.findall(answer or ''):
        url = url.rstrip('.,;')
        if PAYMENT_URL_HINT.search(url) and url not in links:
            links.append(url)
    return links


def render(result, fmt, max_cards, all_cards=False):
    out = {'answer': answer_text(result)}
    items = cards.collect(result, cards.DEFAULT_URL_BASE)
    cards.attach_answer_reasons(items, out['answer'])
    cards.attach_answer_analysis(items, out['answer'])
    if not all_cards and out['answer']:
        kept = [c for c in items if cards.referenced(c, out['answer'])]
        items = kept
    if max_cards and max_cards > 0:
        items = items[:max_cards]
    out['card_count'] = len(items)
    if not items:
        return out
    meta = {'title': '', 'footer': ''}
    if fmt == 'widget':
        out['widget_cards'] = items
        out['product_links'] = [{'title': item['title'], 'url': item['url']} for item in items if item.get('url')]
    elif fmt == 'markdown':
        out['cards_markdown'] = cards.render_markdown(items, meta)
    elif fmt == 'text':
        out['cards_text'] = cards.render_text(items, meta, False, 80)
    else:
        out['cards'] = items
    return out


def write_outputs(payload, request, default_out_dir):
    """本轮结果拆成两个文件：卡片文件（html_file）和 answer 正文（answer_file），应答只回路径。"""
    conversation = request['conversation']
    directory = Path(request.get('out_dir') or default_out_dir or Path.home() / '.local/state/filtalgo-agent/output')
    directory = directory / hashlib.sha256(conversation.encode()).hexdigest()[:16]
    custom = dict(request.get('out_dirs') or {})
    for key in OUTPUT_PATH_KEYS:
        if key in request:
            custom[key] = request[key]
    def private_write(target, content):
        target.parent.mkdir(parents=True, exist_ok=True)
        if os.name != 'nt':
            target.parent.chmod(0o700)
        # 调用方明确指定路径时允许覆盖同名文件，默认命名仍是只新建。
        flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if target in overwritable else os.O_EXCL)
        fd = os.open(target, flags, 0o600)
        with os.fdopen(fd, 'w', encoding='utf8') as stream:
            stream.write(content)
    overwritable = {Path(value).expanduser().resolve() for value in custom.values()}
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex
    def target_path(key, suffix):
        if key in custom:
            return Path(custom[key]).expanduser().resolve()
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            if os.name != 'nt':
                directory.chmod(0o700)
        return directory / ('turn-%s.%s' % (stamp, suffix))
    answer = payload.pop('answer', '')
    if 'widget_cards' in payload:
        items = payload.pop('widget_cards')
        cards.inline_images(items, 10)
        payload['cards_html'] = cards.render_widget(items, {'title': '', 'footer': ''}, 'auto')
    if 'cards_html' in payload:
        fragment = payload.pop('cards_html')
        fragment_target = target_path('fragment_path', 'fragment.html')
        page_target = target_path('page_path', 'page.html')
        private_write(fragment_target, fragment)
        private_write(page_target, '<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>商品推荐</title></head><body>\n' + fragment + '\n</body></html>\n')
        payload['fragment_file'] = str(fragment_target)
        payload['page_file'] = str(page_target)
        payload['html_file'] = str(page_target)
    elif 'cards_markdown' in payload:
        target = directory / ('turn-%s.cards.md' % stamp)
        private_write(target, payload.pop('cards_markdown'))
        payload['html_file'] = str(target)
    elif 'cards_text' in payload:
        target = directory / ('turn-%s.cards.txt' % stamp)
        private_write(target, payload.pop('cards_text'))
        payload['html_file'] = str(target)
    elif 'cards' in payload:
        card_items = payload.pop('cards')
        target = directory / ('turn-%s.cards.json' % stamp)
        private_write(target, json.dumps(card_items, ensure_ascii=False, indent=2))
        payload['html_file'] = str(target)
    if answer.strip():
        target = target_path('answer_path', 'answer.md')
        private_write(target, answer)
        payload['answer_file'] = str(target)
    if 'region_selector' in payload:
        payload.pop('region_selector')
        payload['region_selection_required'] = True
    payload['card_count'] = payload.get('card_count', 0)


def handle(client, request, default_format, default_out_dir=None):
    op = request.get('op')
    conversation = request.get('conversation')
    if op == 'ping':
        return {'ok': True, 'status': 'idle', 'protocol': PROTOCOL,
                'capabilities': {'ops': list(OPS), 'formats': list(FORMATS)},
                'health': dict(HEARTBEAT)}
    if op not in OPS:
        raise ClientError('INVALID_OP', '未知 op：%s（可用：%s）' % (op, '/'.join(OPS)))
    if not isinstance(conversation, str) or not conversation.strip():
        raise ClientError('INVALID_CONVERSATION', '每个请求都必须带非空 conversation。')
    fmt = request.get('format') or default_format
    if fmt not in FORMATS:
        raise ClientError('INVALID_FORMAT', 'format 只能是 ' + '/'.join(FORMATS))
    if op in ('send', 'resume'):
        timeout = request.get('timeout', 120)
        limit = request.get('max', 0)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0 or timeout > 3600:
            raise ClientError('INVALID_REQUEST', 'timeout 必须是 0 到 3600 秒。')
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0 or limit > 100:
            raise ClientError('INVALID_REQUEST', 'max 必须是 0 到 100 的整数。')
        for key in ('wait', 'all', 'allow_repeat', 'force'):
            if key in request and not isinstance(request[key], bool):
                raise ClientError('INVALID_REQUEST', key + ' 必须是布尔值。')
        for key in OUTPUT_PATH_KEYS:
            if key in request and (not isinstance(request[key], str) or not request[key].strip()):
                raise ClientError('INVALID_REQUEST', key + ' 必须是非空路径。')
        if 'out_dirs' in request:
            out_dirs = request['out_dirs']
            if not isinstance(out_dirs, dict) or set(out_dirs) - set(OUTPUT_PATH_KEYS):
                raise ClientError('INVALID_REQUEST', 'out_dirs 只能包含 ' + '/'.join(OUTPUT_PATH_KEYS))
            for key, value in out_dirs.items():
                if not isinstance(value, str) or not value.strip():
                    raise ClientError('INVALID_REQUEST', 'out_dirs.' + key + ' 必须是非空路径。')
    if op == 'send':
        text = request.get('text')
        if not isinstance(text, str) or not text.strip():
            raise ClientError('INVALID_TEXT', 'send 需要非空 text。')
        wait = request.get('wait', True) is not False
        result = client.send(conversation, text, wait, timeout,
                             request.get('allow_repeat') is True, request.get('force') is True)
    elif op == 'resume':
        result = client.resume(conversation, timeout)
    elif op == 'cancel':
        result = client.cancel(conversation)
    elif op == 'clear':
        result = client.clear(conversation)
    elif op == 'auth-reset':
        result = client.reset_authorization(conversation)
    elif op == 'status':
        value = client.conversation(conversation)
        out = {'ok': True, 'status': 'pending' if value.get('pending') else value.get('last_status', 'idle'),
               'conversation': conversation}
        if value.get('pending') and value.get('last_error'):
            out['last_error'] = value['last_error']['code']
        return out
    payload = {'ok': result.get('ok', True), 'status': result.get('status'), 'conversation': conversation}
    for key in ('authorization_url', 'message', 'error', 'presentation_status'):
        if result.get(key):
            payload[key] = result[key]
    if result.get('ok', True) and (result.get('answer') is not None or result.get('context_documents') or result.get('region_selector')):
        rendered = render(result, fmt, request.get('max') or 0, bool(request.get('all')))
        payload.update(rendered)
        if result.get('region_selector'):
            payload['region_selector'] = result['region_selector']
        payment_links = extract_payment_links(payload.get('answer'))
        if payment_links:
            payload['payment_links'] = payment_links
        write_outputs(payload, request, default_out_dir)
    return payload


def main():
    parser = argparse.ArgumentParser(description='filtalgo 常驻服务：stdin/stdout 逐行 JSON，skill 的唯一入口。')
    parser.add_argument('--user-key', default='local')
    parser.add_argument('--control-url', default=None)
    parser.add_argument('--agent-id', default=None)
    parser.add_argument('--state-dir', default=None)
    parser.add_argument('--format', choices=FORMATS, default='widget', help='请求未指定 format 时使用的默认值')
    parser.add_argument('--heartbeat', default=None, help='心跳文件路径；默认写到状态目录的 service-heartbeat.json')
    parser.add_argument('--out-dir', default=None, help='每轮卡片与正文的输出目录；请求里可用 out_dir 覆盖')
    parser.add_argument('--once', action='store_true', help='读取一条 JSON 请求并输出一条应答后退出；省略 op 时默认为 send')
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf8', errors='backslashreplace', newline='\n')
    api = build_client(args)
    _, _, directory = state_directory(args)
    heartbeat_path = Path(args.heartbeat) if args.heartbeat else directory / 'service-heartbeat.json'
    HEARTBEAT['started_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    write_heartbeat(heartbeat_path)
    seq = 0
    for line in sys.stdin.buffer:
        if not line.strip():
            continue
        seq += 1
        HEARTBEAT['requests'] = seq
        HEARTBEAT['last_request_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        try:
            request = json.loads(line.decode('utf8'))
            if not isinstance(request, dict):
                raise ClientError('INVALID_REQUEST', '请求必须是 JSON 对象。')
            if args.once and 'op' not in request:
                request['op'] = 'send'
            response = run_request(api, request, args.format, args.out_dir, heartbeat_path)
        except ClientError as exc:
            response = {'ok': False, 'error': {'code': exc.code, 'message': str(exc)}}
        except BaseException as exc:  # 循环本身不能退出，否则后续请求全部丢失
            traceback.print_exc(file=sys.stderr)
            HEARTBEAT['restarts'] = HEARTBEAT.get('restarts', 0) + 1
            try:
                api = build_client(args)
            except Exception:
                traceback.print_exc(file=sys.stderr)
            response = {'ok': False, 'error': {'code': 'INVALID_STATE_OR_RESPONSE',
                                               'message': '本次请求内部异常（%s）；先 resume 核对，不要重新 send。' % type(exc).__name__}}
        response['id'] = seq
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + '\n')
        sys.stdout.flush()
        write_heartbeat(heartbeat_path)
        if args.once:
            break


if __name__ == '__main__':
    try:
        main()
    except ClientError as exc:
        sys.stderr.write(json.dumps({'ok': False, 'error': {'code': exc.code, 'message': str(exc)}}, ensure_ascii=False) + '\n')
        sys.exit(1)
