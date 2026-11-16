"""Strict, static address projection with offline phone recognition; no business calls."""
import html
import math
import re
import time
import commerce_ui
from phone_privacy import contains_phone


def text(value, limit):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and not re.search(r'[\x00-\x1f\x7f]', value)


def unavailable(scene='address_book', way=None):
    return {'status': 'unavailable', 'scene': scene, 'way': way,
            'selection_status': 'not_applicable' if scene == 'address_book' else 'unknown',
            'selected_address_id': None, 'page': {'number': 1, 'has_more': None}, 'items': []}


def validate(value):
    if not isinstance(value, dict): return False
    if not {'status', 'scene', 'way', 'selection_status', 'selected_address_id', 'page', 'items'} <= set(value): return False
    status, scene, way = value.get('status'), value.get('scene'), value.get('way')
    if status not in ('current', 'unavailable', 'authorization_required'): return False
    if scene not in ('address_book', 'checkout'): return False
    if scene == 'address_book':
        if way is not None or value.get('selection_status') != 'not_applicable': return False
    elif not text(way, 64) or value.get('selection_status') not in ('known', 'unknown'): return False
    selected = value.get('selected_address_id')
    if value.get('selection_status') == 'known':
        if not text(selected, 256): return False
    elif selected is not None: return False
    page, items = value.get('page'), value.get('items')
    if not isinstance(page, dict) or type(page.get('number')) is not int or not 1 <= page['number'] <= 1000000: return False
    if 'has_more' not in page or (page['has_more'] is not None and type(page['has_more']) is not bool): return False
    if not isinstance(items, list) or len(items) > 100: return False
    if status != 'current': return not items and selected is None
    expires = value.get('authorization_expires_at')
    binding = value.get('authorization_binding')
    if not isinstance(binding, str) or not re.fullmatch(r'[0-9a-f]{64}', binding): return False
    # Compare integer bounds before float conversion: JSON may contain huge ints.
    if type(expires) not in (int, float) or not 0 < expires <= 9007199254740991: return False
    if not math.isfinite(expires) or expires <= time.time()*1000: return False
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {'address_id', 'recipient_name', 'mobile_display', 'region_path', 'detail', 'is_default'}: return False
        for key, limit in (('address_id', 256), ('recipient_name', 256), ('region_path', 1024), ('detail', 4096)):
            if not text(item.get(key), limit): return False
        if item['address_id'] in seen or type(item.get('is_default')) is not bool: return False
        seen.add(item['address_id'])
        if not isinstance(item.get('mobile_display'), str) or not re.fullmatch(r'1[0-9]{2}\*{4}[0-9]{4}', item['mobile_display']): return False
        # A misplaced raw phone number must not bypass the mobile field guard.
        if any(contains_phone(item[k]) for k in ('recipient_name', 'region_path', 'detail')): return False
    return True


STYLE = '<style>' + commerce_ui.theme_css('.fm-address-root') + commerce_ui.card_rule('.fm-address-root .fm-item') + '''
.fm-address-root{line-height:1.6;min-width:0;width:100%;max-width:100%;padding:1px;box-sizing:border-box}
.fm-address-root *{box-sizing:border-box}
.fm-address-root .fm-hd{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:14px;flex-wrap:wrap}
.fm-address-root h2{font-size:15px;line-height:1.4;font-weight:600;margin:0}
.fm-address-root .fm-caption{font-size:12px;color:var(--fm-muted);margin:3px 0 0}
.fm-address-root .fm-count{font-size:12px;color:var(--fm-muted);white-space:nowrap}
.fm-address-root .fm-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px}
.fm-address-root .fm-item{display:flex;gap:12px;align-items:flex-start;width:100%;max-width:100%;min-width:0;border:1px solid var(--fm-line)}
.fm-address-root .fm-item.is-selected{border:1px solid var(--fm-accent)}
.fm-address-root .fm-number{width:30px;height:30px;flex:0 0 30px;display:grid;place-items:center;border-radius:8px;background:var(--fm-surface2);color:var(--fm-muted);font-size:12px;font-weight:500;font-variant-numeric:tabular-nums}
.fm-address-root .is-selected .fm-number{background:var(--fm-accent-bg);color:var(--fm-accent)}
.fm-address-root .fm-info{min-width:0;flex:1}
.fm-address-root .fm-person{display:flex;align-items:center;gap:6px 10px;flex-wrap:wrap}
.fm-address-root .fm-name{font-size:14px;font-weight:600;overflow-wrap:anywhere}
.fm-address-root .fm-phone{font-size:12px;color:var(--fm-muted);font-variant-numeric:tabular-nums}
.fm-address-root .fm-tags{display:flex;gap:6px;flex-wrap:wrap;margin-left:auto}
.fm-address-root .fm-tag{font-size:11px;line-height:1.3;padding:3px 6px;border-radius:4px;white-space:nowrap}
.fm-address-root .fm-tag--default{border:.5px solid var(--fm-line);color:var(--fm-muted)}
.fm-address-root .fm-tag--selected{background:var(--fm-accent-bg);color:var(--fm-accent)}
.fm-address-root .fm-region{font-size:12px;color:var(--fm-muted);margin:8px 0 2px;overflow-wrap:anywhere;white-space:pre-wrap}
.fm-address-root .fm-detail{font-size:13px;font-weight:500;margin:0;overflow-wrap:anywhere;white-space:pre-wrap}
.fm-address-root .fm-note{font-size:12px;line-height:1.6;color:var(--fm-muted);margin:12px 2px 0;overflow-wrap:anywhere}
.fm-address-root .fm-state{padding:26px 18px;text-align:center;border:.5px solid var(--fm-line);border-radius:var(--commerce-card-radius);background:var(--fm-surface)}
.fm-address-root .fm-state-title{font-size:14px;font-weight:500;margin:0 0 5px}
.fm-address-root .fm-state-copy{font-size:12px;color:var(--fm-muted);margin:0}
@media(max-width:400px){.fm-address-root .fm-item{gap:10px}.fm-address-root .fm-tags{margin-left:0;flex-basis:100%}}
</style>'''


def markdown(value):
    return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', html.escape(value, quote=True))


def display_snapshot(values):
    """Choose one complete trusted snapshot; never join selected IDs to another list."""
    current = [v for v in values if v['status'] == 'current']
    if len({v['authorization_binding'] for v in current}) > 1:
        return unavailable(), ['地址信息需要重新查询确认。']
    books = [v for v in current if v['scene'] == 'address_book']
    checkouts = [v for v in values if v['scene'] == 'checkout']
    if len(checkouts) > 1:
        return (books[0] if len(books) == 1 else unavailable()), ['请明确本次结算使用哪一种方式，再确认收货地址。']
    if len(checkouts) == 1 and checkouts[0]['status'] == 'current':
        return checkouts[0], []
    if len(books) == 1:
        return books[0], ['本次收货地址尚未核实，请在结算前重新确认。'] if checkouts else []
    return next((v for v in values if v['status'] == 'authorization_required'), unavailable()), []


def render(snapshots, fmt='md'):
    if not isinstance(snapshots, list) or not snapshots or len(snapshots) > 100:
        snapshots = [unavailable()]
    values = []
    for raw in snapshots:
        if validate(raw): values.append(raw)
        elif isinstance(raw, dict) and raw.get('scene') == 'checkout' and text(raw.get('way'), 64):
            # Keep only the non-sensitive scene, so expiry cannot hide the pending-selection notice.
            values.append(unavailable('checkout', raw['way']))
        else: values.append(unavailable())
    value, notes = display_snapshot(values)
    statuses = [v['status'] for v in values] + [value['status']]
    overall = 'unavailable' if 'unavailable' in statuses else 'authorization_required' if 'authorization_required' in statuses else 'current'
    status = value['status']; items = value['items']
    subtitle = '用于本次结算' if value['scene'] == 'checkout' else '管理配送使用的收货地址'
    info = '第%s页 · 本页%s条' % (value['page']['number'], len(items)) if status == 'current' else ''
    if status == 'current' and value['page']['has_more'] is True: info += ' · 还有后页'
    body = '<header class="fm-hd"><div><h2>收货地址</h2><p class="fm-caption">%s</p></div><span class="fm-count">%s</span></header>' % (subtitle, info)
    md = ['## 收货地址\n', info + '\n']
    if status != 'current' or not items:
        if status == 'unavailable':
            title, message = '地址列表暂不可用', '请先查询确认，避免重复操作。'
        elif status == 'authorization_required':
            title, message = '需要会员授权', '查看收货地址需要会员授权，请按当前授权流程继续。'
        else:
            title = '暂无收货地址。' if value['page']['number'] == 1 and value['page']['has_more'] is False else '本页没有地址。'
            message = '可以在对话中提供收货信息，继续添加地址。'
        body += '<div class="fm-state"><p class="fm-state-title">%s</p><p class="fm-state-copy">%s</p></div>' % (title, message)
        md += [title + '\n', message + '\n']
    rows = []
    for index, item in enumerate(items, 1):
        selected = value['selection_status'] == 'known' and value['selected_address_id'] == item['address_id']
        labels = (['默认地址'] if item['is_default'] else []) + (['本次已选中'] if selected else [])
        badges = ('<span class="fm-tag fm-tag--default">默认地址</span>' if item['is_default'] else '') + ('<span class="fm-tag fm-tag--selected">本次已选中</span>' if selected else '')
        rows.append('<li class="fm-item%s"><span class="fm-number" aria-hidden="true">%s</span><div class="fm-info"><div class="fm-person"><span class="fm-name">%s</span><span class="fm-phone">%s</span><span class="fm-tags">%s</span></div><p class="fm-region">%s</p><p class="fm-detail">%s</p></div></li>' % (
            ' is-selected' if selected else '', index, html.escape(item['recipient_name']), html.escape(item['mobile_display']), badges, html.escape(item['region_path']), html.escape(item['detail'])))
        md.append('%s. %s · %s %s\n\n   %s\n\n   %s\n' % (index, markdown(item['recipient_name']), markdown(item['mobile_display']), ' · '.join(labels), markdown(item['region_path']), markdown(item['detail'])))
    if rows: body += '<ol class="fm-list">%s</ol>' % ''.join(rows)
    if value['selection_status'] == 'unknown': notes.append('本次收货地址尚未核实，请在结算前确认。')
    elif value['selection_status'] == 'known' and value['selected_address_id'] not in [i['address_id'] for i in items]: notes.append('本页未列出当前选中地址。')
    for note in notes:
        body += '<p class="fm-note" role="status">%s</p>' % html.escape(note)
        md.append(note + '\n')
    if fmt == 'md': return overall, '\n'.join(md)
    content = STYLE + '<section class="fm-address-root" aria-label="收货地址">%s</section>' % body
    return overall, commerce_ui.html_page(content, '收货地址') if fmt == 'html' else content
