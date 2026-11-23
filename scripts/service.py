#!/usr/bin/env python3
"""filtalgo 服务入口：skill 的唯一入口，每行一个 JSON 请求，每行一个 JSON 应答。

stdin:  {"op":"send","conversation":"...","text":"...","format":"md"}
        {"op":"resume","conversation":"...","format":"md"}
        {"op":"cancel"|"clear"|"auth-reset"|"status","conversation":"..."}
        {"op":"ping"}
stdout: {"id":<请求序号>,"ok":true,"status":"completed","card_count":3,"display_file":"...display.md","answer_file":"...answer.md"}
        {"id":<请求序号>,"ok":false,"error":{"code":"...","message":"..."}}

支持 --once 单次调用与常驻逐行处理；复用同一个 Client、文件锁和本地状态。
默认输出 Markdown 正文 display_file，并兼容保留 answer_file、html_file 及各业务文件字段。
不会新建身份，也不会在失败后重发。不向 stdout 写日志：诊断信息全部进 stderr。
"""
import argparse
import hashlib
import html
import json
import os
import tempfile
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
import hosts  # noqa: E402
import client  # noqa: E402
import address_cards  # noqa: E402
import logistics_cards  # noqa: E402
import customer_service_cards  # noqa: E402
import commerce_ui  # noqa: E402
import commerce_render  # noqa: E402
import link_response  # noqa: E402
from update_check import UpdateChecker  # noqa: E402

ClientError = client.ClientError

PROTOCOL = 1
FORMATS = ('widget', 'html', 'md')
OPS = ('send', 'resume', 'cancel', 'clear', 'auth-reset', 'revoke-authorization', 'logout', 'status', 'ping')
# 请求里可对单个产物指定完整文件路径，覆盖默认目录命名。
OUTPUT_PATH_KEYS = ('display_path', 'fragment_path', 'page_path', 'answer_path', 'cart_path', 'checkout_path', 'after_sale_path', 'address_path', 'logistics_path', 'customer_service_path')


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


def run_request(client, request, default_format, default_out_dir=None, heartbeat_path=None, update_checker=None):
    """请求放在线程里跑：单次请求崩溃不会带走进程，超时也只影响这一条。"""
    box = {}

    def target():
        try:
            box['ok'] = handle(client, request, default_format, default_out_dir, update_checker)
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
    text = cards.unescape_markdown(content) if isinstance(content, str) else ''
    return URL_PATTERN.sub(lambda match: commerce_render.mobile_navigation_url(match.group()), text)


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


render_cart = commerce_render.render_cart



def html_page(fragment, title):
    return commerce_ui.html_page(fragment, title)


def build_display_markdown(answer, sections):
    """按固定业务顺序拼接同轮已验证正文与各业务 Markdown 段，不二次请求或反向解析 HTML。"""
    parts = []
    if isinstance(answer, str) and answer.strip():
        parts.append(answer.strip())
    for section in sections:
        if isinstance(section, str) and section.strip():
            parts.append(section.strip())
    return ('\n\n'.join(parts) + '\n') if parts else ''



CARD_CACHE_FIELDS = ('title', 'price', 'spec', 'score', 'availability', 'thumbnail',
                     'url', 'goods_id', 'sku_id', 'advantage')
ORDINAL = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6,
           '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6}


def _cache_file(client, conversation):
    directory = getattr(getattr(client, 'store', None), 'directory', None)
    if not isinstance(directory, (str, os.PathLike)) or not isinstance(conversation, str) or not conversation:
        return None
    digest = hashlib.sha256(conversation.encode('utf-8')).hexdigest()[:32]
    folder = Path(directory) / 'product-cache'
    try:
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        return None
    return folder / (digest + '.json')


def save_card_cache(client, conversation, items):
    path = _cache_file(client, conversation)
    if path is None or not items:
        return
    payload = {'saved_at': time.strftime('%Y-%m-%d %H:%M'),
               'cards': [{key: item.get(key) for key in CARD_CACHE_FIELDS} for item in items[:5]]}
    tmp = path.with_suffix('.tmp')
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf8')
        tmp.replace(path)
    except OSError:
        pass


def load_card_cache(client, conversation):
    path = _cache_file(client, conversation)
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf8'))
    except (OSError, ValueError):
        return None


def select_reused(cached, text):
    cards_list = (cached or {}).get('cards') or []
    if not cards_list:
        return []
    flat = re.sub(r'\s+', '', text or '')
    picks, seen = [], set()
    for match in re.finditer(r'第\s*([一二三四五六1-6])\s*(?:个|款|件|条)?', flat):
        index = ORDINAL.get(match.group(1))
        if index and 1 <= index <= len(cards_list):
            card = cards_list[index - 1]
            key = (card.get('goods_id'), card.get('sku_id'), card.get('title'))
            if key not in seen:
                seen.add(key)
                picks.append(card)
    if picks:
        return picks
    for card in cards_list:
        title = re.sub(r'\s+', '', card.get('title') or '')
        if title and len(title) >= 4 and title in flat:
            return [card]
    return []


def skill_version():
    """读取 SKILL.md 的 metadata.version；失败返回 None。"""
    try:
        text = (Path(__file__).resolve().parents[1] / 'SKILL.md').read_text(encoding='utf8')
    except OSError:
        return None
    match = re.search(r'^\s+version:\s*"([^"]+)"', text, re.M)
    return match.group(1) if match else None


def record_call(client, payload, host, host_source, fmt):
    """每次调用追加一行 JSONL，便于统计宿主维度的失败率；不记录用户文本。"""
    directory = getattr(getattr(client, 'store', None), 'directory', None)
    if not isinstance(directory, (str, os.PathLike)) or os.environ.get('FILTALGO_NO_LOG') == '1':
        return
    card_count = payload.get('card_count') or 0
    record = {
        'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'host': host,
        'host_source': host_source,
        'format': fmt,
        'card_count': card_count,
        'card_source': payload.get('card_source') or ('new' if card_count else 'none'),
        'status': payload.get('status'),
        'error_code': (payload.get('error') or {}).get('code') if isinstance(payload.get('error'), dict) else None,
        'version': skill_version(),
    }
    try:
        path = Path(directory) / 'calls.jsonl'
        with open(path, 'a', encoding='utf8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
    except OSError:
        pass


def resolve_host(request, client, conversation):
    """宿主解析：会话锁定 → 请求字段 → 环境变量 → default。"""
    raw = request.get('host')
    locked = None
    getter = getattr(client, 'locked_host', None)
    if callable(getter):
        try:
            locked = hosts.normalize(getter(conversation))
        except Exception:
            locked = None
    if locked:
        return locked, 'state', raw
    host = hosts.normalize(raw)
    source = 'request'
    if not host:
        host = hosts.normalize(os.environ.get('FILTALGO_HOST'))
        source = 'env'
    if not host:
        host, source = 'default', 'default'
    if host != 'default':
        remember = getattr(client, 'remember_host', None)
        if callable(remember):
            try:
                remember(conversation, host)
            except Exception:
                pass
    return host, source, raw


def render(result, fmt, max_cards, all_cards=False):
    budget = cards.ImageBudget()
    out = {'answer': answer_text(result), '_format': fmt, '_image_budget': budget}
    customer_service_md = ''
    logistics_md = ''
    address_md = ''
    cart_md = ''
    md_sections_by_field = {}
    products_md = ''
    if 'customer_service_snapshots' in result:
        out['customer_service_status'], out['customer_service_count'], customer_service_md = customer_service_cards.render(result['customer_service_snapshots'], 'md')
        out['customer_service_content'] = (
            customer_service_md if fmt == 'md'
            else customer_service_cards.render(result['customer_service_snapshots'], fmt)[2]
        )
    if 'logistics_snapshots' in result:
        out['logistics_status'], out['logistics_count'], logistics_md = logistics_cards.render(result['logistics_snapshots'], 'md')
        out['logistics_content'] = (
            logistics_md if fmt == 'md'
            else logistics_cards.render(result['logistics_snapshots'], fmt)[2]
        )
    if 'address_snapshots' in result:
        out['address_status'], address_md = address_cards.render(result['address_snapshots'], 'md')
        out['address_content'] = (
            address_md if fmt == 'md'
            else address_cards.render(result['address_snapshots'], fmt)[1]
        )
    if 'cart' in result:
        try:
            out['cart_status'], cart_md = render_cart(result['cart'], 'md', budget)
            if fmt == 'md':
                out['cart_content'] = cart_md
            else:
                out['cart_status'], out['cart_content'] = render_cart(result['cart'], fmt, budget)
        except Exception:
            out['presentation_status'] = 'failed'
            out.setdefault('presentation_errors', []).append('cart_render_failed')
    for field, kinds in (('checkout', [('checkouts', 'checkout')]),
                         ('after_sale', [('after_sales', 'after_sale'), ('after_sale_lists', 'after_sale_list')])):
        documents = [(result.get(key) or [], kind) for key, kind in kinds]
        if not any(docs for docs, _ in documents):
            continue
        try:
            ordered = [(document, kind) for docs, kind in documents for document in docs]
            ordered.sort(key=lambda pair: (pair[0].get('display_order', 0), pair[0].get('revision', 0)))
            md_parts, links = [], []
            for document, kind in ordered:
                md_rendered, navigation = commerce_render.render([document], kind, 'md', budget)
                md_parts.append(md_rendered)
                links.extend(navigation)
            md_combined = '\n'.join(md_parts)
            md_sections_by_field[field] = md_combined
            out[field + '_count'] = sum(len(docs) for docs, _ in documents)
            if field == 'checkout':
                out['payment_links'] = list(dict.fromkeys(url for _, url, rel in links if rel == 'payment'))
            if fmt == 'md':
                out[field + '_content'] = md_combined
            else:
                html_parts = []
                for document, kind in ordered:
                    rendered, _ = commerce_render.render([document], kind, 'widget', budget)
                    html_parts.append(rendered)
                combined = '\n'.join(html_parts)
                out[field + '_content'] = html_page(combined, '结算' if field == 'checkout' else '售后') if fmt == 'html' else combined
        except Exception:
            out['presentation_status'] = 'failed'
            out.setdefault('presentation_errors', []).append(field + '_render_failed')
    try:
        items = cards.collect(result, cards.DEFAULT_URL_BASE)
        cards.attach_answer_reasons(items, out['answer'])
        cards.attach_answer_analysis(items, out['answer'])
        items = cards.select_for_answer(items, out['answer'], all_cards)
        if max_cards and max_cards > 0:
            items = items[:max_cards]
        out['card_count'] = len(items)
        if items:
            has_answer = bool(out['answer'].strip())
            if not (has_answer and all(cards.answer_covers_card(item, out['answer']) for item in items)):
                products_md = cards.render_markdown(
                    items,
                    {'title': '商品信息与入口' if has_answer else '', 'footer': ''},
                    omit_answer_extracts=has_answer,
                )
            product_links = [{'title': item['title'], 'url': item['url']} for item in items if item.get('url')]
            if fmt in ('widget', 'html'):
                out['widget_cards'] = items
                out['product_links'] = product_links
            elif fmt == 'md':
                out['cards_markdown'] = cards.render_markdown(items, {'title': '', 'footer': ''})
                if product_links:
                    out['product_links'] = product_links
    except Exception:
        out['card_count'] = 0
        out['presentation_status'] = 'failed'
        out.setdefault('presentation_errors', []).append('product_render_failed')
    display_content = build_display_markdown(out['answer'], [
        products_md,
        cart_md,
        address_md,
        md_sections_by_field.get('checkout', ''),
        logistics_md,
        md_sections_by_field.get('after_sale', ''),
        customer_service_md,
    ])
    if not display_content and result.get('region_selector'):
        display_content = '请提供或确认收货地区（省、市、区）及详细地址后再继续。\n'
    if display_content:
        out['display_content'] = display_content
    return out


def write_outputs(payload, request, default_out_dir):
    """按所选格式保存商品和购物车产物，正文单独保存。"""
    started = time.monotonic()
    conversation = request['conversation']
    directory = Path(request.get('out_dir') or default_out_dir or Path.home() / '.local/state/filtalgo-agent/output')
    directory = directory / hashlib.sha256(conversation.encode()).hexdigest()[:16]
    custom = dict(request.get('out_dirs') or {})
    for key in OUTPUT_PATH_KEYS:
        if key in request:
            custom[key] = request[key]
    def private_directory(path):
        try:
            path.mkdir(mode=0o700)
        except FileNotFoundError:
            private_directory(path.parent)
            private_directory(path)
        except FileExistsError:
            if not path.is_dir():
                raise
    def private_write(target, content):
        private_directory(target.parent)
        fd, temporary = tempfile.mkstemp(dir=target.parent, prefix='.commerce-')
        try:
            with os.fdopen(fd, 'w', encoding='utf8') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if target in overwritable:
                os.replace(temporary, target)
            else:
                # Atomic create without silently overwriting another turn.
                os.link(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    overwritable = {Path(value).expanduser().resolve() for value in custom.values()}
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex
    def target_path(key, suffix):
        if key in custom:
            return Path(custom[key]).expanduser().resolve()
        return directory / ('turn-%s.%s' % (stamp, suffix))
    display_content = payload.pop('display_content', '')
    answer = payload.pop('answer', '')
    fmt = payload.pop('_format', 'md')
    budget = payload.pop('_image_budget', None)
    def save(target, content):
        try:
            private_write(target, content)
            return True
        except OSError:
            payload['presentation_status'] = 'failed'
            payload.setdefault('presentation_errors', []).append('output_write_failed')
            return False
    for field in ('cart', 'checkout', 'after_sale', 'address', 'logistics', 'customer_service'):
        if field + '_content' not in payload:
            continue
        target = target_path(field + '_path', ('addresses' if field == 'address' else field.replace('_', '-')) + ('.html' if fmt in ('widget', 'html') else '.md'))
        if save(target, payload.pop(field + '_content')):
            payload[field + '_file'] = str(target)
            if fmt == 'widget': payload[field + '_fragment_file'] = str(target)
            if fmt == 'html': payload[field + '_page_file'] = str(target)
    if 'widget_cards' in payload:
        items = payload.pop('widget_cards')
        try:
            cards.inline_images(items, 5, budget)
            payload['cards_html'] = cards.render_widget(items, {'title': '', 'footer': ''}, 'auto')
        except Exception:
            payload['presentation_status'] = 'failed'
            payload.setdefault('presentation_errors', []).append('product_render_failed')
    if 'cards_html' in payload:
        fragment = payload.pop('cards_html')
        if fmt == 'html':
            target = target_path('page_path', 'page.html')
            if save(target, html_page(fragment, '商品推荐')):
                payload['page_file'] = str(target)
                payload['html_file'] = str(target)
        else:
            target = target_path('fragment_path', 'fragment.html')
            if save(target, fragment):
                payload['fragment_file'] = str(target)
                payload['html_file'] = str(target)
    elif 'cards_markdown' in payload:
        target = directory / ('turn-%s.cards.md' % stamp)
        if save(target, payload.pop('cards_markdown')):
            payload['html_file'] = str(target)
    if display_content.strip():
        target = target_path('display_path', 'display.md')
        if save(target, display_content):
            payload['display_file'] = str(target)
    if answer.strip():
        target = target_path('answer_path', 'answer.md')
        if save(target, answer):
            payload['answer_file'] = str(target)
    if 'region_selector' in payload:
        payload.pop('region_selector')
        payload['region_selection_required'] = True
    payload['card_count'] = payload.get('card_count', 0)
    print(json.dumps({'event': 'commerce.presentation', 'format': fmt,
                      'status': payload.get('presentation_status', 'completed'),
                      'checkout_count': payload.get('checkout_count', 0),
                      'after_sale_count': payload.get('after_sale_count', 0),
                      'output_ms': round((time.monotonic() - started) * 1000),
                      'image_budget_exhausted': bool(budget and time.monotonic() >= budget.deadline)},
                     ensure_ascii=False), file=sys.stderr)


def handle(client, request, default_format, default_out_dir=None, update_checker=None):
    # 更新信息只属于当前请求；已知业务错误保留原 code/message 和本轮检查结果。
    context = {}
    try:
        payload = _handle(client, request, default_format, default_out_dir, update_checker, context)
    except ClientError as exc:
        if 'skill_update' in context:
            exc.skill_update = context['skill_update']
        elif hasattr(exc, 'skill_update'):
            del exc.skill_update
        raise
    if 'skill_update' in context:
        payload['skill_update'] = context['skill_update']
    return payload


def _handle(client, request, default_format, default_out_dir, update_checker, context):
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
    host, host_source, _raw_host = resolve_host(request, client, conversation)
    if client is not None:
        client.host = host
    if host == 'default':
        # 未识别宿主：保留 2.3.x 行为，由请求或 CLI 决定格式。
        fmt = request.get('format') or default_format
    else:
        # 已识别宿主：格式由路由表固定，请求里的 format 默认忽略。
        fmt = hosts.profile(host)['format']
        if os.environ.get('FILTALGO_FORMAT_OVERRIDE') == '1' and request.get('format'):
            fmt = request['format']
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
        for key in ('out_dir',) + OUTPUT_PATH_KEYS:
            if key in request and (not isinstance(request[key], str) or not request[key].strip()):
                raise ClientError('INVALID_REQUEST', key + ' 必须是非空路径。')
        if 'out_dirs' in request:
            out_dirs = request['out_dirs']
            if not isinstance(out_dirs, dict) or set(out_dirs) - set(OUTPUT_PATH_KEYS):
                raise ClientError('INVALID_REQUEST', 'out_dirs 只能包含 ' + '/'.join(OUTPUT_PATH_KEYS))
            for key, value in out_dirs.items():
                if not isinstance(value, str) or not value.strip():
                    raise ClientError('INVALID_REQUEST', 'out_dirs.' + key + ' 必须是非空路径。')
        paths = {**(request.get('out_dirs') or {}), **{key: request[key] for key in OUTPUT_PATH_KEYS if key in request}}
        resolved = [str(Path(path).expanduser().resolve()) for path in paths.values()]
        if len(resolved) != len(set(resolved)):
            raise ClientError('INVALID_REQUEST', '不同产物必须指定不同路径。')
    if op == 'send':
        text = request.get('text')
        if not isinstance(text, str) or not text.strip():
            raise ClientError('INVALID_TEXT', 'send 需要非空 text。')
        wait = request.get('wait', True) is not False
        if update_checker is not None:
            try:
                context['skill_update'] = update_checker.check(conversation)
            except Exception:
                context['skill_update'] = {'status': 'unknown', 'notify': False, 'reason': 'check_failed'}
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
    elif op == 'revoke-authorization':
        result = client.revoke_authorization(conversation)
    elif op == 'logout':
        result = client.logout(conversation)
    elif op == 'status':
        value = client.conversation(conversation)
        out = {'ok': True, 'status': 'pending' if value.get('pending') else value.get('last_status', 'idle'),
               'conversation': conversation}
        if value.get('pending') and value.get('last_error'):
            out['last_error'] = value['last_error']['code']
        return out
    payload = {'ok': result.get('ok', True), 'status': result.get('status'), 'conversation': conversation,
               'host': host, 'host_source': host_source}
    for key in ('authorization_url', 'message', 'error', 'presentation_status'):
        if result.get(key):
            payload[key] = result[key]
    if (result.get('ok', True) and (result.get('answer') is not None or result.get('context_documents') or result.get('region_selector'))) or any(k in result for k in ('cart', 'address_snapshots', 'logistics_snapshots', 'customer_service_snapshots')) or any(result.get(k) for k in ('checkouts', 'after_sales', 'after_sale_lists')):
        rendered = render(result, fmt, request.get('max') or 0, bool(request.get('all')))
        payload.update(rendered)
        if result.get('region_selector'):
            payload['region_selector'] = result['region_selector']
        payment_links = payload.get('payment_links', []) if result.get('checkouts') else extract_payment_links(payload.get('answer'))
        if payment_links:
            payload['payment_links'] = payment_links
        link_response.finalize_payload(payload)
        try:
            current_items = cards.collect(result, cards.DEFAULT_URL_BASE)
        except Exception:
            current_items = []
        try:
            if current_items:
                save_card_cache(client, conversation, current_items)
            elif payload.get('display_content'):
                # 第二级：会话库里已有的商品块（真实文档，优先于本地快照）
                carried = []
                carry = result.get('carry') if isinstance(result.get('carry'), dict) else None
                if carry:
                    try:
                        carried = client.carried_product_documents(**carry)
                    except Exception:
                        carried = []
                reused = ''
                if carried:
                    try:
                        carried_items = cards.collect({'context_documents': carried}, cards.DEFAULT_URL_BASE)
                    except Exception:
                        carried_items = []
                    if carried_items:
                        reused = cards.render_reused(carried_items, '本会话前几轮', title='会话内已有商品信息')
                        payload['card_source'] = 'session-library'
                        save_card_cache(client, conversation, carried_items)
                # 第三级：本地快照缓存
                if not reused:
                    cached = load_card_cache(client, conversation)
                    reused = cards.render_reused(select_reused(cached, request.get('text') or ''),
                                                 (cached or {}).get('saved_at') or '')
                    if reused:
                        payload['card_source'] = 'previous-turn'
                if reused:
                    payload['display_content'] = reused + '\n' + payload['display_content']
        except Exception:
            pass
        write_outputs(payload, request, default_out_dir)
        record_call(client, payload, host, host_source, fmt)
    return payload


def update_timeout(value):
    try:
        timeout = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError('更新检查超时必须是大于 0 且不超过 30 秒的有限数值。')
    if not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise argparse.ArgumentTypeError('更新检查超时必须是大于 0 且不超过 30 秒的有限数值。')
    return timeout


def main():
    parser = argparse.ArgumentParser(description='filtalgo 常驻服务：stdin/stdout 逐行 JSON，skill 的唯一入口。')
    parser.add_argument('--user-key', default='local')
    parser.add_argument('--control-url', default=None)
    parser.add_argument('--agent-id', default=None)
    parser.add_argument('--state-dir', default=None)
    parser.add_argument('--format', choices=FORMATS, default='md', help='请求未指定 format 时使用的默认值')
    parser.add_argument('--heartbeat', default=None, help='心跳文件路径；默认写到状态目录的 service-heartbeat.json')
    parser.add_argument('--out-dir', default=None, help='每轮卡片与正文的输出目录；请求里可用 out_dir 覆盖')
    parser.add_argument('--once', action='store_true', help='读取一条 JSON 请求并输出一条应答后退出；省略 op 时默认为 send')
    parser.add_argument('--update-timeout', type=update_timeout, default=2.0, help='更新检查超时秒数，默认 2；必须大于 0 且不超过 30')
    parser.add_argument('--update-action', choices=('check', 'shown', 'later', 'ignore', 'reset'), help='独立检查更新或记录已提醒／稍后／忽略／重置后退出，不读取业务请求')
    parser.add_argument('--update-version', help='提醒选择对应的正式版本，例如 v2.10.0')
    parser.add_argument('--update-conversation', help='更新检查或提醒选择对应的 conversation')
    args = parser.parse_args()
    if not args.update_action and (args.update_version is not None or args.update_conversation is not None):
        parser.error('--update-version 和 --update-conversation 需要同时指定 --update-action。')
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf8', errors='backslashreplace', newline='\n')
    if args.update_action:
        # 使用与 send 相同的状态目录；不构造业务身份、不写心跳、不读取 stdin。
        try:
            _, _, directory = state_directory(args)
            checker = UpdateChecker(SKILL_DIR, directory, args.user_key, args.update_timeout)
            response = ({'ok': True, 'skill_update': checker.check(args.update_conversation)}
                        if args.update_action == 'check' else
                        checker.record(args.update_action, args.update_version, args.update_conversation))
        except ClientError as exc:
            response = {'ok': False, 'error': {'code': exc.code, 'message': str(exc)}}
        except Exception:
            response = {'ok': False, 'error': 'update_management_failed'}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + '\n')
        sys.stdout.flush()
        if not response.get('ok'):
            raise SystemExit(1)
        return
    api = build_client(args)
    _, _, directory = state_directory(args)
    update_checker = UpdateChecker(SKILL_DIR, directory, args.user_key, args.update_timeout)
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
            response = run_request(api, request, args.format, args.out_dir, heartbeat_path, update_checker)
        except ClientError as exc:
            response = {'ok': False, 'error': {'code': exc.code, 'message': str(exc)}}
            if hasattr(exc, 'skill_update'):
                response['skill_update'] = exc.skill_update
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
