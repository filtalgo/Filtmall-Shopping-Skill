"""Read-only renderers for public commerce projections. No business requests or body parsing."""
from decimal import Decimal, InvalidOperation, localcontext
import html
import re
from urllib.parse import urlsplit, urlunsplit, quote
import cards

STYLE = '''<style>
.fm-commerce{--fg:var(--color-text-primary,#2a2724);--fg-2:var(--color-text-secondary,#6f6a63);--fg-3:var(--color-text-secondary,#8f897f);--line:var(--color-border-tertiary,#e4dfd7);--line-soft:var(--color-border-tertiary,#f0ebe4);--fill:var(--color-background-secondary,#f8f5f1);--skin:var(--color-background-secondary,#f4f0ec);--surface:var(--color-background-primary,#fff);--accent:#3c6470;--accent-bg:#edf3f4;--accent-line:#cfdde0;--warn:#7d5c2c;--warn-bg:#fbf6ea;--warn-line:#ebe0c4;display:block;max-width:560px;margin:0 0 12px;color:var(--fg);background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden;font:14px/1.6 var(--font-sans,system-ui,-apple-system,"Segoe UI",sans-serif);font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.fm-commerce *{box-sizing:border-box}.fm-commerce p{margin:8px 0}.fm-commerce a{color:inherit;text-decoration:none}.fm-commerce a:focus-visible,.fm-commerce summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.fm-commerce .hd{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:14px 16px 12px}.fm-commerce h2{margin:0;font-size:15px;line-height:1.35;font-weight:600}.fm-commerce .meta{font-size:12px;color:var(--fg-3)}
.fm-commerce .status{font-size:12px;line-height:1.4;color:var(--accent);background:var(--accent-bg);border:1px solid var(--accent-line);border-radius:999px;padding:2px 9px}
.fm-commerce .body{padding:2px 16px 12px}.fm-commerce .product{display:grid;grid-template-columns:40px minmax(0,1fr) auto;gap:12px;align-items:center;padding:12px 0;border-top:1px solid var(--line-soft)}.fm-commerce .product:first-child{border-top:0}.fm-commerce .thumb{width:40px;height:48px;border-radius:6px;background:var(--skin);display:grid;place-items:center;overflow:hidden;font-size:11px;color:var(--fg-3)}.fm-commerce .thumb img{display:block;width:100%;height:100%;object-fit:contain}.fm-commerce .product b{display:block;font-size:13px;font-weight:600;line-height:1.45}.fm-commerce .price{font-size:13px;color:var(--fg-2);white-space:nowrap}
.fm-commerce .sub{font-size:12px;color:var(--fg-3)}.fm-commerce .h3{margin:14px 0 8px;font-size:12px;color:var(--fg-2)}.fm-commerce .fees{border-top:1px solid var(--line-soft)}.fm-commerce .line{display:flex;justify-content:space-between;gap:12px;padding:7px 0;font-size:13px;color:var(--fg-2)}.fm-commerce .line.sum{border-top:1px solid var(--line);margin-top:4px;padding-top:11px;color:var(--fg)}.fm-commerce .sum b:last-child{font-size:22px;font-weight:600}
.fm-commerce .note{margin:12px 0 2px;padding:9px 12px;border-radius:6px;background:var(--warn-bg);border:1px solid var(--warn-line);color:var(--warn);font-size:12px}.fm-commerce .foot{display:flex;flex-wrap:wrap;gap:8px;padding:12px 16px;border-top:1px solid var(--line-soft);background:var(--fill)}.fm-commerce .button{display:inline-flex;align-items:center;padding:7px 12px;border-radius:6px;border:1px solid var(--line);background:var(--surface);font-size:12px;line-height:1.4}.fm-commerce .button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.fm-commerce .event{padding:2px 0 14px 18px;border-left:1px solid var(--line);font-size:13px}.fm-commerce details{border-top:1px solid var(--line-soft);padding:10px 0 2px}.fm-commerce summary{cursor:pointer;font-size:12px;color:var(--fg-2)}
@media(prefers-color-scheme:dark){.fm-commerce{--fg:var(--color-text-primary,#e8e3db);--fg-2:var(--color-text-secondary,#aaa399);--fg-3:var(--color-text-secondary,#8c867d);--line:var(--color-border-tertiary,#3b3733);--line-soft:var(--color-border-tertiary,#322e2b);--fill:var(--color-background-secondary,#2e2a27);--skin:var(--color-background-secondary,#37322e);--surface:var(--color-background-primary,#252220);--accent:#9fc2ca;--accent-bg:#26343a;--accent-line:#38505a;--warn:#dcc28f;--warn-bg:#332c1f;--warn-line:#4a3f2a}.fm-commerce .button.primary{color:#1d2528}}
</style>'''


def clean(value, default=''):
    return re.sub(r'[\x00-\x1f\x7f]+', ' ', value).strip() if isinstance(value, str) else default


def escape(value):
    return html.escape(clean(value), quote=True)


def md(value):
    return re.sub(r'([\\`*_{}\[\]()#+.!|~\-])', r'\\\1', escape(value))


def money(value, major=False):
    currency = 'CNY' if major else value.get('currency') if isinstance(value, dict) else None
    raw = value if major else value.get('minor_units') if isinstance(value, dict) else None
    if currency not in ('CNY', 'USD', 'EUR', 'GBP') or isinstance(raw, bool):
        return None
    if not re.fullmatch(r'\d{1,30}(?:\.\d{1,2})?' if major else r'\d{1,30}', str(raw)):
        return None
    try:
        with localcontext() as context:
            context.prec = 40
            amount = Decimal(str(raw)) / (1 if major else 100)
            return {'CNY': '¥', 'USD': '$', 'EUR': '€', 'GBP': '£'}[currency] + format(amount, '.2f')
    except InvalidOperation:
        return None


def page(fragment, title):
    return '<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>%s</title></head><body>%s</body></html>\n' % (escape(title), fragment)


def card(title, state, body, footer=''):
    return '<article class="fm-commerce"><div class="hd"><h2>%s</h2>%s</div><div class="body">%s</div>%s</article>' % (escape(title), '<span class="status">%s</span>' % escape(state) if state else '', body, '<footer class="foot">%s</footer>' % footer if footer else '')


def product_rows(items, fmt, budget, cart=False):
    if not isinstance(items, list) or len(items) > 500 or any(not isinstance(i, dict) for i in items):
        raise ValueError('Invalid items')
    images = []
    for item in items:
        url = item.get('thumbnail')
        images.append({'thumbnail': url if isinstance(url, str) and len(url) <= 2048 and url.startswith(('https://', 'data:image/')) and not re.search(r'[\x00-\x20\x7f]', url) else ''})
    if fmt != 'md':
        cards.inline_images(images, 5, budget)
    rows, lines = [], []
    for i, item in enumerate(items):
        title = clean(item.get('title')) or '商品'
        quantity = item.get('quantity')
        if type(quantity) is not int or not 0 <= quantity <= 9007199254740991:
            quantity = None
        price = money(item.get('price'), True) if cart else money(item.get('unit_price'))
        bits = ([('已选' if item.get('checked') else '未选')] if cart else [])
        if item.get('spec'): bits.append(clean(item['spec']))
        if quantity is not None: bits.append('数量 %s' % quantity)
        if price or cart:
            bits.append('单价 ' + price if price else '价格待确认')
        image = '<img src="%s" alt="">' % escape(images[i]['thumbnail']) if images[i].get('thumbnail') and fmt != 'md' else '暂无图'
        price_html = '<span class="price">%s</span>' % (price or '待确认') if price or cart else ''
        rows.append('<div class="product"><div class="thumb" aria-hidden="true">%s</div><div><b>%s</b><div class="sub">%s</div></div>%s</div>' % (image, escape(title), escape(' · '.join(bits)), price_html))
        lines.append('- %s：%s' % (md(title), md(' · '.join(bits))))
    body = ''.join(rows[:3])
    if len(rows) > 3:
        body += '<details><summary>展开另外 %s 款商品</summary>%s</details>' % (len(rows) - 3, ''.join(rows[3:]))
    return body, lines


def mobile_navigation_url(href):
    """Map only known storefront cart/order routes; preserve business query data."""
    hosts = {'buyer.filtalgo.com': 'm.filtalgo.com',
             'pre-buyer.filtalgo.com': 'pre-m.filtalgo.com',
             'dev-buyer.filtalgo.com': 'dev-m.filtalgo.com'}
    paths = {'/cart': '/pages/tabbar/cart',
             '/user/home/orderCenter/myOrder': '/pages/mine/order/list',
             '/user/home/orderCenter/orderDetail': '/pages/mine/order/detail'}
    try:
        url = urlsplit(href)
        if url.scheme == 'https' and url.netloc in hosts and url.path in paths:
            return urlunsplit(('https', hosts[url.netloc], paths[url.path], url.query, url.fragment))
    except ValueError:
        pass
    return href


def navigation(links):
    result = []
    for link in links if isinstance(links, list) else []:
        if not isinstance(link, dict) or link.get('rel') not in ('payment', 'checkout', 'after_sale', 'cart'):
            continue
        href = clean(link.get('href'))
        try:
            url = urlsplit(href)
            if len(href) > 2048 or re.search(r'[\x00-\x20\x7f]', href) or url.scheme != 'https' or not url.hostname or url.username or url.password:
                continue
            url.port
        except ValueError:
            continue
        result.append(({'payment': '打开收银台', 'checkout': '查看结算', 'after_sale': '打开售后详情', 'cart': '打开购物车'}[link['rel']], mobile_navigation_url(href), link['rel']))
    return result


def render_documents(documents, kind, fmt, budget):
    bodies, texts, public_links = [], [], []
    for document in documents:
        value = document.get('value') if isinstance(document, dict) else None
        value = value if isinstance(value, dict) else {}
        title = '结算' if kind == 'checkout' else '售后列表' if kind == 'after_sale_list' else '售后详情'
        if value.get('status') != 'current':
            message = '状态暂不可用。操作可能已生效，请先查询确认，避免重复操作。'
            bodies.append(card(title, '待核实', '<p>%s</p>' % message))
            texts.append('## %s\n\n%s' % (md(title), message))
            continue
        if kind == 'after_sale_list':
            records = value.get('records')
            if not isinstance(records, list) or len(records) > 500:
                raise ValueError('Invalid after-sale list')
            pagination = value.get('page') if isinstance(value.get('page'), dict) else {}
            summary = '本页 %s 笔' % len(records)
            for key, label in (('current', '页码'), ('total', '总数'), ('size', '每页')):
                if type(pagination.get(key)) is int and pagination[key] >= 0:
                    summary += ' · %s %s' % (label, pagination[key])
            bodies.append(card(title, summary, '<p>暂无售后记录。</p>' if not records else ''))
            texts.append('## 售后列表\n\n' + summary + ('\n\n暂无售后记录。' if not records else ''))
            if records:
                body, text, links = render_documents([{'value': r} for r in records], 'after_sale', fmt, budget)
                bodies.append(body); texts.append(text); public_links.extend(links)
            continue
        body, lines = product_rows(value.get('items', []), fmt, budget)
        log_body, log_lines = '', []
        terminal_checkout = kind == 'checkout' and clean(value.get('checkout_status')).lower() in ('canceled', 'cancelled', 'completed')
        if kind == 'checkout':
            payment = {'paid': '已付款', 'unpaid': '待付款', 'cancelled': '已取消', 'refunded': '已退款'}.get(value.get('payment_status'), '支付待核实')
            state = '预览' if value.get('mode') == 'preview' else payment
            amounts = value.get('amounts') if isinstance(value.get('amounts'), dict) else {}
            fees = [(label, money(amounts.get(key)) or '待确认', key == 'total') for key, label in (('goods', '商品金额'), ('discount', '优惠'), ('shipping', '运费'), ('total', '应付金额')) if key == 'total' or money(amounts.get(key)) is not None]
            if value.get('checkout_status'):
                checkout_state = {'not_ready_for_payment': '信息待完善', 'ready_for_payment': '可提交结算',
                                  'in_progress': '处理中', 'completed': '结算已完成', 'canceled': '已取消',
                                  'cancelled': '已取消', 'authentication_required': '待验证'}.get(value['checkout_status'], '待核实')
                lines.insert(0, '结算状态：' + checkout_state)
                body += '<div class="sub">结算状态：%s</div>' % checkout_state
                if terminal_checkout:
                    state = checkout_state
                    body += '<div class="sub">支付状态：%s</div>' % ('未支付' if value.get('payment_status') == 'unpaid' else payment)
            lines.insert(0, '支付状态：' + ('未支付' if value.get('payment_status') == 'unpaid' else payment))
            if value.get('payment_status') == 'unpaid' and not terminal_checkout:
                note = '请前往收银台完成付款。'
            else:
                note = ''
        else:
            state = clean(value.get('service_status_label')) or {'APPLY': '申请中', 'PASS': '审核通过', 'REFUSE': '已拒绝',
                    'BUYER_RETURN': '待卖家收货', 'SELLER_CONFIRM': '卖家已确认收货', 'SELLER_TERMINATION': '卖家终止售后',
                    'BUYER_CANCEL': '买家取消售后', 'WAIT_REFUND': '等待平台退款', 'COMPLETE': '售后完成'}.get(value.get('service_status'), '待核实')
            fees = [('申请退款', money(value.get('requested_refund')) or '待确认', False)]
            if money(value.get('refund_amount')): fees.append(('退款金额', money(value['refund_amount']), False))
            fees.append(('实际到账', '尚未确认', False))
            for key, label in (('after_sale_id', '售后号'), ('service_type', '售后类型')):
                if value.get(key):
                    field = {'RETURN_GOODS': '退货退款', 'RETURN_MONEY': '仅退款'}.get(value[key], '待核实') if key == 'service_type' else value[key]
                    lines.insert(0, label + '：' + md(field))
                    body += '<div class="sub">%s：%s</div>' % (label, escape(field))
            logs = value.get('logs') if isinstance(value.get('logs'), list) else []
            if logs:
                log_body += '<h3 class="h3">处理记录</h3>'
                log_lines.append('### 处理记录')
                for log in logs:
                    if isinstance(log, dict):
                        event = ' · '.join(clean(log.get(k)) for k in ('message', 'status', 'occurred_at') if clean(log.get(k)))
                        log_body += '<div class="event">%s</div>' % escape(event)
                        log_lines.append('- ' + md(event))
            note = ' '.join(clean(v) for v in value.get('next_actions', []) if isinstance(v, str)) if isinstance(value.get('next_actions'), list) else ''
        fee_rows = []
        for label, amount, total in fees:
            tag = 'b' if total else 'span'
            fee_rows.append('<div class="line%s"><%s>%s</%s><%s>%s</%s></div>' % (' sum' if total else '', tag, label, tag, tag, amount, tag))
        body += '<div class="fees">' + ''.join(fee_rows) + '</div>'
        lines.extend('%s：%s' % (label, amount) for label, amount, _ in fees)
        body += log_body
        lines.extend(log_lines)
        if note:
            body += '<div class="note">%s</div>' % escape(note)
            lines.append('> 下一步：' + md(note))
        links = [link for link in navigation(value.get('links')) if kind != 'checkout' or link[2] != 'checkout']
        filtered_payment = terminal_checkout and any(rel == 'payment' for _, _, rel in links)
        if terminal_checkout:
            links = [link for link in links if link[2] != 'payment']
        public_links.extend(links)
        footer = ''.join('<a class="button%s" href="%s" target="_blank" rel="noopener noreferrer">%s ↗</a>' % (' primary' if rel == 'payment' else '', escape(url), label) for label, url, rel in links)
        lines.extend('[%s](%s)' % (label, quote(url, safe=':/?=&%#@+;,~')) for label, url, _ in links)
        if not links:
            message = '该结算已结束，暂无可用的详情入口。' if filtered_payment else '暂未取得可用入口。'
            body += '<p class="sub">%s</p>' % message
            lines.append(message)
        bodies.append(card(title, state, body, footer))
        texts.append('## %s\n\n**状态：** %s\n\n%s' % (md('售后' if kind == 'after_sale' else title), md(state), '\n\n'.join(lines)))
    return ''.join(bodies), '\n\n'.join(texts) + '\n', public_links


def render(documents, kind, fmt, budget):
    body, markdown, links = render_documents(documents, kind, fmt, budget)
    fragment = STYLE + body
    return (markdown if fmt == 'md' else page(fragment, '结算' if kind == 'checkout' else '售后') if fmt == 'html' else fragment), links


def render_cart(value, fmt='md', budget=None):
    budget = budget or cards.ImageBudget()
    items = value.get('items') if isinstance(value, dict) else None
    valid = isinstance(value, dict) and value.get('status') == 'current' and isinstance(items, list) and len(items) <= 500
    valid = valid and all(isinstance(i, dict) and isinstance(i.get('sku_id'), str) and i['sku_id'] and type(i.get('quantity')) is int and 0 <= i['quantity'] <= 9007199254740991 and type(i.get('checked')) is bool for i in items)
    if not valid:
        message = '购物车状态正在更新或暂不可用。操作可能已生效，请先查询确认，避免重复操作。'
        body, markdown, status = '<p>%s</p>' % message, message + '\n', 'unavailable'
    else:
        status = 'current'
        if not items:
            body, markdown = '<p>购物车为空。</p>', '购物车为空。\n'
        else:
            selected = [i for i in items if i['checked']]
            summary = '已选 %s 款 / %s 件 · 全车 %s 款 · %s 件' % (len(selected), sum(i['quantity'] for i in selected), len(items), sum(i['quantity'] for i in items))
            rows, lines = product_rows(items, fmt, budget, cart=True)
            body = '<div class="fees"><div class="line"><b>已选 %s 款 / %s 件</b><span class="sub">全车 %s 款 · %s 件</span></div></div>' % (len(selected), sum(i['quantity'] for i in selected), len(items), sum(i['quantity'] for i in items)) + rows
            markdown = '## 购物车\n\n%s\n\n%s\n' % (summary, '\n'.join(lines))
    links = navigation([{'rel': 'cart', 'href': value.get('cart_url')}]) if valid else []
    footer = ''.join('<a class="button" href="%s" target="_blank" rel="noopener noreferrer">%s ↗</a>' % (escape(url), label) for label, url, _ in links)
    markdown += ''.join('\n[%s](%s)\n' % (label, quote(url, safe=':/?=&%#@+;,~')) for label, url, _ in links)
    fragment = STYLE + card('购物车', '' if valid else '待核实', body, footer)
    return status, markdown if fmt == 'md' else page(fragment, '购物车') if fmt == 'html' else fragment
