"""Private customer service entry cards; never opens or fetches links."""
import html
import json
import re
import time
from urllib.parse import urlsplit, parse_qsl, quote
import commerce_ui
from logistics_cards import text, escaped

IDS = ('store_id', 'goods_id', 'sku_id', 'order_sn', 'after_sale_sn')
SCENES = {'product': ('store_id', 'goods_id'), 'order': ('order_sn',), 'after_sale': ('after_sale_sn',), 'general': ('store_id',)}
AUTH = {'authorization_binding', 'authorization_expires_at', 'link_origins'}


def unavailable(status='unavailable', reason=None):
    return dict(status=status, query=None, fetched_at=None, reason=reason, entry=None)


def group_key(query):
    if not isinstance(query, dict) or set(query) != {'scene', *IDS} or not isinstance(query.get('scene'), str) or query['scene'] not in SCENES:
        return None
    if any(v is not None and not text(v, 256, True) for k, v in query.items() if k != 'scene'):
        return None
    scene = query['scene']
    if any(not query[k] for k in SCENES[scene]): return None
    keys = (*SCENES[scene], 'sku_id') if scene == 'product' else SCENES[scene]
    return json.dumps([scene, *(query[k] for k in keys)], ensure_ascii=False, separators=(',', ':'))


def safe_url(value, origins, origin_only=False):
    if not text(value, 4096, True) or re.search(r'[\\\s\x00-\x1f\x7f]', value) or '#' in value or re.search(r'%(?![0-9a-fA-F]{2})', value): return False
    try:
        p = urlsplit(value)
        if p.scheme != 'https' or not p.hostname or p.username is not None or p.password is not None or p.port == 0: return False
        hostname = p.hostname.encode('ascii').decode('ascii').lower()
        if '%' in hostname: return False
        hostname = '[' + hostname + ']' if ':' in hostname else hostname
        origin = 'https://' + hostname + (':' + str(p.port) if p.port not in (None, 443) else '')
        if origin_only: return value == origin
        if origins is not None and origin not in origins: return False
        forbidden = {'access_token', 'refresh_token', 'token', 'authorization', 'api_key', 'password', 'client_secret'}
        return not any(k.lower() in forbidden for k, _ in parse_qsl(p.query, keep_blank_values=True, encoding='utf-8', errors='strict'))
    except (ValueError, UnicodeError): return False


def validate(v):
    try:
        return _validate(v)
    except (TypeError, ValueError, UnicodeError, OverflowError):
        return False


def _validate(v):
    if not isinstance(v, dict): return False
    base = {'status', 'query', 'fetched_at', 'reason', 'entry'}
    if not base <= set(v) or set(v) - base - AUTH - {'publication'}: return False
    if 'publication' in v:
        p = v['publication']
        if not isinstance(p, dict) or set(p) != {'task_id', 'call_id'} or any(not text(p[k], 256, True) for k in p): return False
    if len(json.dumps(v, ensure_ascii=False).encode('utf-8')) > 255*1024: return False
    if v['query'] is not None and group_key(v['query']) is None: return False
    if v['status'] != 'current':
        return (v['status'] in ('unavailable', 'authorization_required') and v['entry'] is None and v['fetched_at'] is None and not AUTH.intersection(v) and v['reason'] in (None, 'query_failed', 'invalid_data', 'payload_too_large', 'no_entry') and (v['reason'] != 'no_entry' or v['status'] == 'unavailable'))
    if v['reason'] is not None or v['query'] is None: return False
    if type(v['fetched_at']) is not int or not 0 < v['fetched_at'] <= 253402300799999: return False
    origins = None
    if AUTH.intersection(v):
        if not AUTH <= set(v): return False
        if not isinstance(v['authorization_binding'], str) or not re.fullmatch('[0-9a-f]{64}', v['authorization_binding']): return False
        if type(v['authorization_expires_at']) is not int or not 0 < v['authorization_expires_at'] <= 253402300799999: return False
        if v['authorization_expires_at'] <= time.time()*1000: return False
        origins = v['link_origins']
        if not isinstance(origins, list) or not 1 <= len(origins) <= 2 or any(not safe_url(o, [], True) for o in origins) or len(set(origins)) != len(origins): return False
    e = v['entry']; q = v['query']
    if not isinstance(e, dict) or set(e) != {'scene', *IDS, 'store_name', 'default_channel', 'channels'}: return False
    if e['scene'] != q['scene'] or any(not text(e[k], 256, k == 'store_id') for k in IDS) or not text(e['store_name'], 2048): return False
    if any(e[k] != q[k] for k in SCENES[q['scene']]): return False
    if q['scene'] == 'product' and q['sku_id'] is not None and e['sku_id'] != q['sku_id']: return False
    channels = e['channels']
    if e['default_channel'] not in ('pc_web', 'mobile_h5') or not isinstance(channels, dict) or not channels or set(channels) - {'pc_web', 'mobile_h5'}: return False
    return all(isinstance(c, dict) and set(c) == {'url'} and safe_url(c['url'], origins) for c in channels.values())


STYLE = '<style>' + commerce_ui.theme_css('.fm-customer-service') + commerce_ui.card_rule('.fm-customer-service .fm-service-card') + '''
.fm-customer-service{line-height:1.6;width:100%;max-width:100%;min-width:0;padding:1px;box-sizing:border-box}
.fm-customer-service *{box-sizing:border-box;min-width:0;overflow-wrap:anywhere}
.fm-customer-service .fm-service-card{width:100%;margin-top:10px;padding:20px;border:1px solid var(--fm-line)}
.fm-customer-service .fm-service-heading{display:flex;align-items:center;gap:12px}
.fm-customer-service .fm-service-icon{display:flex;align-items:center;justify-content:center;flex:0 0 44px;height:44px;border-radius:10px;background:var(--fm-accent-bg);color:var(--fm-accent)}
.fm-customer-service .fm-service-icon svg{width:23px;height:23px}
.fm-customer-service .fm-heading-copy{flex:1}
.fm-customer-service h2{display:inline-block;margin:0;font-size:11px;line-height:1.5;font-weight:500;color:var(--fm-muted)}
.fm-customer-service h3{margin:2px 0 0;font-size:18px;line-height:1.5;font-weight:600}
.fm-customer-service .fm-service-summary{margin:16px 0 0;padding:12px 14px;border-radius:8px;background:var(--fm-surface2);font-size:13px;color:var(--fm-muted)}
.fm-customer-service dl{margin:12px 0 0;font-size:13px}
.fm-customer-service dt{color:var(--fm-muted)}
.fm-customer-service dd{margin:0 0 8px}
.fm-customer-service .fm-caption{font-size:12px;color:var(--fm-muted);margin:10px 0 0}
.fm-customer-service .fm-actions{display:flex;align-items:center;flex-wrap:wrap;gap:12px;margin-top:18px;padding-top:16px;border-top:1px solid var(--fm-line)}
.fm-customer-service a{font-size:13px;color:var(--fm-accent);text-underline-offset:3px}
.fm-customer-service .fm-primary{display:inline-flex;align-items:center;justify-content:center;min-height:40px;padding:8px 22px;border-radius:8px;border:1px solid var(--fm-accent);background:var(--fm-accent);color:var(--fm-surface);font-weight:600;text-decoration:none}
.fm-customer-service .fm-primary:hover{filter:brightness(.94)}
.fm-customer-service a:focus-visible{outline:2px solid var(--fm-accent);outline-offset:3px}
@media(max-width:480px){.fm-customer-service .fm-service-card{padding:16px}.fm-customer-service .fm-primary{width:100%}.fm-customer-service h3{font-size:17px}}
</style>'''


def render(snapshots, fmt='md'):
    values = snapshots if isinstance(snapshots, list) and 0 < len(snapshots) <= 16 else [unavailable()]
    values = [v if validate(v) else unavailable() for v in values]
    status = 'unavailable' if any(v['status'] == 'unavailable' for v in values) else 'authorization_required' if any(v['status'] == 'authorization_required' for v in values) else 'current'
    parts = []; markdown = []; count = 0
    for v in values:
        if v['status'] != 'current':
            message = '查看客服入口需要会员授权。' if v['status'] == 'authorization_required' else '客服入口暂不可用，请重新查询。'
            parts.append('<article class="fm-service-card"><h2>客服入口</h2><p class="fm-caption">%s</p></article>' % message)
            markdown.append('## 客服入口\n\n' + message); continue
        count += 1; e = v['entry']
        heading = {'general': '店铺客服', 'product': '商品客服', 'order': '订单客服', 'after_sale': '售后客服'}[e['scene']]
        store = e['store_name'] or '商家客服'
        card = ('<article class="fm-service-card"><header class="fm-service-heading">'
                '<span class="fm-service-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
                '<path d="M20 11.5a8 8 0 0 1-8 8H5l-3 2v-10a8 8 0 0 1 16-2"/><path d="M7 11h7M7 15h4"/></svg></span>'
                '<div class="fm-heading-copy"><h2>%s</h2><h3>%s</h3></div></header>') % (heading, escaped(store))
        lines = ['## ' + heading, escaped(store, True)]
        description = {'product': '商品相关问题，可通过下方入口咨询商家。', 'general': '店铺相关问题，可通过下方入口咨询商家。',
                       'order': '订单相关问题，可通过下方入口咨询商家。', 'after_sale': '售后相关问题，可通过下方入口咨询商家。'}[e['scene']]
        card += '<p class="fm-service-summary">%s</p>' % description
        lines.append(description)
        references = []
        labels = {'order_sn': '关联订单', 'after_sale_sn': '关联售后单'}
        for key in labels:
            if e[key]:
                references.append('<dt>%s</dt><dd>%s</dd>' % (labels[key], escaped(e[key], identifier=True)))
                lines.append(labels[key] + '：' + escaped(e[key], True, identifier=True))
        if references: card += '<dl>' + ''.join(references) + '</dl>'
        card += '<div class="fm-actions">'
        seen = set()
        for channel in dict.fromkeys([e['default_channel'], 'pc_web', 'mobile_h5']):
            c = e['channels'].get(channel)
            if not c or c['url'] in seen: continue
            label = '联系客服' if not seen else '电脑页面入口' if channel == 'pc_web' else '手机页面入口'
            primary = not seen
            seen.add(c['url'])
            url = html.escape(c['url'], quote=True)
            link = '<a%s href="%s" target="_blank" rel="noopener noreferrer">%s</a>' % (' class="fm-primary"' if primary else '', url, label)
            card += link
            lines.append('[%s](%s)' % (label, quote(c['url'], safe=':/?=&%#@+;,~')))
        note = '打开商城客服页面继续咨询，目标页面可能需要登录。'
        parts.append(card + '</div><p class="fm-caption">%s</p></article>' % note)
        markdown.append('\n\n'.join(lines + [note]))
    if fmt == 'md': return status, count, '\n\n'.join(markdown) + '\n'
    content = STYLE + '<section class="fm-customer-service">' + ''.join(parts) + '</section>'
    return status, count, commerce_ui.html_page(content, '客服入口') if fmt == 'html' else content
