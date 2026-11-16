"""Validate and render private, request-bound logistics snapshots without business calls."""
import datetime
import html
import json
import re
import time

import commerce_ui


def unavailable(status='unavailable', reason=None):
    return {'status': status, 'query': None, 'fetched_at': None, 'empty_reason': None,
            'reason': reason if reason in ('query_failed', 'invalid_data', 'payload_too_large') else None, 'packages': []}


def text(value, limit, required=False):
    return isinstance(value, str) and len(value) <= limit and not re.search(r'[\x00-\x1f\x7f]', value) and (not required or bool(value.strip()))


def integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 9007199254740991


def timestamp(value):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})', value):
        return None
    if value[-1] != 'Z' and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        return None
    try:
        dt = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
        delta = dt.astimezone(datetime.timezone.utc) - datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
        return (delta.days*86400000 + delta.seconds*1000 + delta.microseconds//1000) if dt.year >= 1900 else None
    except (ValueError, OverflowError, OSError):
        return None


def display_time(value):
    """Show explicit instants in Beijing time; preserve unzoned wall clocks and unknown text."""
    try:
        if type(value) is int:
            dt = datetime.datetime.fromtimestamp(value / 1000, datetime.timezone.utc)
        elif timestamp(value) is not None:
            dt = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
        elif re.fullmatch(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?', value):
            dt = datetime.datetime.fromisoformat(value)
        else:
            return value
        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
        return dt.strftime('%Y-%m-%d %H:%M')
    except (ValueError, OverflowError, OSError):
        return value if isinstance(value, str) else '时间未提供'


def validate(value):
    if not isinstance(value, dict) or value.get('status') not in ('current', 'authorization_required', 'unavailable'):
        return False
    if not {'status', 'query', 'fetched_at', 'empty_reason', 'reason', 'packages'} <= set(value):
        return False
    if value.get('reason') not in (None, 'query_failed', 'invalid_data', 'payload_too_large'):
        return False
    query = value.get('query')
    if query is not None:
        if not isinstance(query, dict) or set(query) != {'order_sn', 'package_no', 'include_items', 'include_traces'}: return False
        if not text(query['order_sn'], 256, True) or (query['package_no'] is not None and not text(query['package_no'], 256, True)): return False
        if type(query['include_items']) is not bool or type(query['include_traces']) is not bool: return False
    packages = value.get('packages')
    if not isinstance(packages, list) or len(packages) > 100: return False
    if value['status'] != 'current':
        return (not packages and value.get('fetched_at') is None and value.get('empty_reason') is None
                and 'authorization_binding' not in value and 'authorization_expires_at' not in value)
    if query is None or value.get('reason') is not None or not integer(value.get('fetched_at'), 1) or value['fetched_at'] > 253402300799999: return False
    if not integer(value.get('authorization_expires_at'), 1) or value['authorization_expires_at'] <= time.time()*1000: return False
    if not isinstance(value.get('authorization_binding'), str) or not re.fullmatch('[0-9a-f]{64}', value['authorization_binding']): return False
    expected_empty = None if packages else 'no_packages' if query['package_no'] is None else 'package_not_found'
    if value.get('empty_reason') != expected_empty: return False
    ids = set(); nodes = 0
    for pkg in packages:
        if not isinstance(pkg, dict) or set(pkg) != {'package_no', 'logistics_name', 'logistics_no', 'logistics_time', 'items', 'trace_status', 'trace_order', 'traces'}: return False
        if not text(pkg['package_no'], 256, True) or pkg['package_no'] in ids: return False
        if query['package_no'] is not None and pkg['package_no'] != query['package_no']: return False
        ids.add(pkg['package_no'])
        if not all(text(pkg[k], limit) for k, limit in [('logistics_name', 256), ('logistics_no', 256), ('logistics_time', 128)]): return False
        if not isinstance(pkg['items'], list) or len(pkg['items']) > 500: return False
        if not query['include_items'] and pkg['items']: return False
        for item in pkg['items']:
            if not isinstance(item, dict) or set(item) != {'goods_name', 'sku_name', 'deliver_number'}: return False
            if not text(item['goods_name'], 2048) or not text(item['sku_name'], 2048) or not integer(item['deliver_number']): return False
        traces = pkg['traces']
        if not isinstance(traces, list): return False
        nodes += len(traces)
        if nodes > 2000 or pkg['trace_order'] not in ('source', 'time_desc'): return False
        expected = 'not_requested' if not query['include_traces'] else 'available' if traces else 'no_trace'
        if pkg['trace_status'] != expected or (not query['include_traces'] and traces): return False
        times = []
        for node in traces:
            if not isinstance(node, dict) or set(node) != {'time', 'occurred_at', 'description', 'location', 'status'}: return False
            if not all(text(node[k], limit) for k, limit in [('time', 128), ('description', 2048), ('location', 512), ('status', 256)]): return False
            actual = timestamp(node['time'])
            if node['occurred_at'] is not None and (type(node['occurred_at']) is not int or node['occurred_at'] != actual): return False
            if actual != node['occurred_at']: return False
            times.append(actual)
        if pkg['trace_order'] == 'time_desc' and (not traces or None in times or times != sorted(times, reverse=True)): return False
        if pkg['trace_order'] == 'source' and times and None not in times: return False
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf8')) <= 256*1024
    except (ValueError, TypeError, UnicodeError):
        return False


def escaped(value, markdown=False, identifier=False):
    if not identifier:
        value = re.sub(r'(?<!\d)(1\d{2})\d{4}(\d{4})(?!\d)', r'\1****\2', value)
    value = html.escape(value, quote=True)
    return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', value) if markdown else value


STYLE = '<style>' + commerce_ui.theme_css('.fm-logistics-root') + commerce_ui.card_rule('.fm-logistics-root .fm-package') + '''
.fm-logistics-root{line-height:1.6;width:100%;max-width:100%;min-width:0;padding:1px;box-sizing:border-box}
.fm-logistics-root *{box-sizing:border-box;min-width:0;overflow-wrap:anywhere}
.fm-logistics-root h2{font-size:15px;margin:0;font-weight:600}
.fm-logistics-root h3{font-size:14px;margin:0 0 8px;font-weight:600}
.fm-logistics-root p{margin:5px 0;font-size:13px;white-space:pre-wrap}
.fm-logistics-root .fm-caption{font-size:12px;color:var(--fm-muted)}
.fm-logistics-root .fm-package{margin-top:10px;width:100%;border:1px solid var(--fm-line)}
.fm-logistics-root .fm-badge{font-size:11px;color:var(--fm-muted);font-weight:400;margin-left:8px}
.fm-logistics-root .fm-summary{margin:12px 0;padding:10px 12px;background:var(--fm-surface2);border-radius:8px;font-size:13px}
.fm-logistics-root .fm-items{padding-left:18px;margin:8px 0;font-size:13px}
.fm-logistics-root .fm-traces{list-style:none;margin:12px 0 0;padding:0 0 0 12px}
.fm-logistics-root .fm-node{position:relative;margin:0;padding:0 0 18px 18px;border-left:1px solid var(--fm-line)}
.fm-logistics-root .fm-node::before{content:"";position:absolute;left:-4px;top:6px;width:7px;height:7px;border-radius:50%;background:var(--fm-muted)}
.fm-logistics-root .fm-node:first-child::before{background:var(--fm-accent)}
.fm-logistics-root .fm-node:last-child{padding-bottom:0;border-left-color:transparent}
.fm-logistics-root .fm-message{border:1px solid var(--fm-line);border-radius:var(--commerce-card-radius);padding:18px;margin-top:10px}
</style>'''


def render(snapshots, fmt='md'):
    values = snapshots if isinstance(snapshots, list) and 0 < len(snapshots) <= 16 else [unavailable()]
    values = [v if validate(v) else unavailable() for v in values]
    overall = 'unavailable' if any(v['status'] == 'unavailable' for v in values) else 'authorization_required' if any(v['status'] == 'authorization_required' for v in values) else 'current'
    parts = []; md = []; count = 0
    for value in values:
        status = value['status']; query = value['query']
        if status != 'current':
            message = '查看物流需要会员授权，请按当前授权流程继续。' if status == 'authorization_required' else '物流信息暂不可用，请在对话中重新查询确认。'
            if value['reason'] == 'payload_too_large': message = '本次数据超出完整展示上限，可指定单个包裹查询；当前未删减或展示部分轨迹。'
            parts.append('<section class="fm-logistics-root"><h2>订单物流</h2><p class="fm-message">%s</p></section>' % message)
            md.append('## 订单物流\n\n' + message)
            continue
        heading = '订单 ' + query['order_sn']
        caption = '本次返回 %d 个包裹' % len(value['packages'])
        if query['package_no'] is not None: caption += ' · 当前查看指定包裹'
        fetched = display_time(value['fetched_at'])
        body = '<h2>订单物流 · %s</h2><p class="fm-caption">%s</p><p class="fm-caption">查询时间：%s</p>' % (escaped(heading, identifier=True), caption, fetched)
        lines = ['## 订单物流 · ' + escaped(heading, True, identifier=True), caption, '查询时间：' + fetched]
        if not value['packages']:
            message = '未找到指定包裹，请核对包裹信息。' if value['empty_reason'] == 'package_not_found' else '该订单暂无包裹信息。'
            body += '<p class="fm-message">%s</p>' % message; lines.append(message)
        for index, pkg in enumerate(value['packages'], 1):
            count += 1
            label = {'available': '', 'no_trace': '暂无物流轨迹', 'not_requested': '未查询轨迹'}[pkg['trace_status']]
            badge = '<span class="fm-badge">%s</span>' % label if label else ''
            card = '<article class="fm-package"><h3>包裹 %s%s</h3>' % (index, badge)
            lines += ['### 包裹 %s%s' % (index, ' · ' + label if label else '')]
            for title, raw in [('快递公司', pkg['logistics_name']), ('运单号', pkg['logistics_no']), ('发货时间', pkg['logistics_time'])]:
                if title == '发货时间': raw = display_time(raw)
                # Tracking identifiers are private business facts, not phone fields.
                value_html = html.escape(raw, quote=True) if title == '运单号' else escaped(raw)
                value_md = re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', html.escape(raw)) if title == '运单号' else escaped(raw, True)
                card += '<p>%s：%s</p>' % (title, value_html or '暂未提供')
                lines.append('%s：%s' % (title, value_md or '暂未提供'))
            if not query['include_items']:
                card += '<p class="fm-caption">本次不包含商品明细。</p>'; lines.append('本次不包含商品明细。')
            elif pkg['items']:
                card += '<ul class="fm-items">'
                for item in pkg['items']:
                    item_text = '%s / %s / 发货 %s 件' % (item['goods_name'] or '商品名称未提供', item['sku_name'] or '规格未提供', item['deliver_number'])
                    card += '<li>%s</li>' % escaped(item_text); lines.append('- ' + escaped(item_text, True))
                card += '</ul>'
            else:
                card += '<p class="fm-caption">暂未提供商品明细。</p>'; lines.append('暂未提供商品明细。')
            if not pkg['traces']:
                message = '本次未查询物流轨迹。' if pkg['trace_status'] == 'not_requested' else '暂未获取到物流轨迹，可稍后在对话中刷新。'
                card += '<p>%s</p>' % message; lines.append(message)
            else:
                newest = pkg['traces'][0]
                title = '最新动态' if pkg['trace_order'] == 'time_desc' else '首条返回轨迹'
                summary = '%s：%s · %s' % (title, display_time(newest['time']) or '时间未提供', newest['description'] or '描述未提供')
                card += '<div class="fm-summary">%s</div>' % escaped(summary); lines.append(escaped(summary, True))
                if pkg['trace_order'] == 'source':
                    message = '按返回顺序展示，时间顺序待核实。'
                    card += '<p class="fm-caption">%s</p>' % message; lines.append(message)
                card += '<ol class="fm-traces" aria-label="完整物流轨迹">'; lines.append('完整物流轨迹：')
                for node in pkg['traces']:
                    node_time = display_time(node['time']) or '时间未提供'
                    card += '<li class="fm-node"><p class="fm-caption">%s</p><p>%s</p>' % (escaped(node_time), escaped(node['description'] or '描述未提供'))
                    lines.append('- %s · %s' % (escaped(node_time, True), escaped(node['description'] or '描述未提供', True)))
                    for title, key in [('地点', 'location'), ('状态', 'status')]:
                        if node[key]:
                            card += '<p class="fm-caption">%s：%s</p>' % (title, escaped(node[key])); lines.append('  %s：%s' % (title, escaped(node[key], True)))
                    card += '</li>'
                card += '</ol>'
            body += card + '</article>'
        parts.append('<section class="fm-logistics-root">%s</section>' % body)
        md.append('\n\n'.join(lines))
    if fmt == 'md': return overall, count, '\n\n'.join(md) + '\n'
    content = STYLE + '\n'.join(parts)
    return overall, count, commerce_ui.html_page(content, '订单物流') if fmt == 'html' else content
