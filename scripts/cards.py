#!/usr/bin/env python3
"""把 filtalgo 的 product-card 资料块渲染成宿主界面友好的输出。

只读请求结算结果（result JSON），不修改会话状态。
默认只渲染当前答复确实引用的商品，避免把上轮卡片当成本轮推荐。
widget 模式将缩略图压缩后以内联 data URI 写入 HTML。
"""
import base64
import html
import re
import sys
import unicodedata
import urllib.request
import urllib.parse


CARD_KIND_PREFIX = 'filtalgo.shopping.block:'
CARD_SCHEMAS = ('filtmall.product-card/v1', 'filtmall.product-card/v2')
LIST_SCHEMAS = ('filtmall.products/v1', 'filtmall.products/v2')
DEFAULT_URL_BASE = 'https://m.filtalgo.com/pages/goods/product/detail'
IMAGE_MAX_BYTES = 12 * 1024
IMAGE_MAX_SIDE = 160

AVAILABILITY = {
    'in_stock': '有货',
    'low_stock': '库存紧张',
    'out_of_stock': '缺货',
    'preorder': '预售',
    'unavailable': '不可售',
}


def unescape_markdown(text):
    """还原 Markdown 的标点转义，保留双反斜杠及非标点转义。"""
    return re.sub(r'\\\\|\\([!"#$%&\'()*+,\-./:;<=>?@\[\]^_`{|}~])',
                  lambda match: match.group(1) if match.group(1) else match.group(0), text)


def money(value):
    """18.8 -> 18.8 / 49 -> 49 / 49.00 -> 49"""
    if value is None or value == '':
        return None
    text = unescape_markdown(str(value)).strip()
    try:
        number = float(text)
    except ValueError:
        return text
    return str(int(number)) if number == int(number) else ('%.2f' % number).rstrip('0')


def clean(text):
    return re.sub(r'\s+', ' ', unescape_markdown(str(text or ''))).strip()


def strip_space(text):
    return re.sub(r'\s+', '', str(text or ''))


def normalize_dimensions(raw):
    out = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                name = clean(item.get('name') or item.get('label') or item.get('key'))
                value = clean(item.get('value') or item.get('text'))
                merged = (name + ' ' + value).strip()
                if merged:
                    out.append(merged)
            elif isinstance(item, str) and item.strip():
                out.append(clean(item))
    return out[:6]


def pick(doc, payload, product, schema, index):
    """把两种商品 schema 归一到同一结构；缺失字段留 None。"""
    price = product.get('price_amount')
    currency = product.get('currency') or 'CNY'
    advantage = payload.get('price_advantage') or {}
    brand = payload.get('brand_knowledge') or {}
    goods_id = str(product.get('goods_id') or '').strip() or None
    sku_id = str(product.get('sku_id') or '').strip() or None
    rank = product.get('rank') or payload.get('rank') or index
    return {
        'schema': schema,
        'document_id': doc.get('document_id'),
        'revision': doc.get('revision'),
        'rank': rank,
        'title': clean(product.get('title')) or clean(payload.get('fallbackText')) or '未命名商品',
        'subtitle': clean(product.get('subtitle')),
        'price': money(price),
        'currency': currency,
        'origin_price': money(product.get('original_price_amount')),
        'spec': clean(product.get('spec_summary')),
        'dimensions': normalize_dimensions(payload.get('dimensions')),
        'thumbnail': clean(product.get('thumbnail')),
        'availability': product.get('availability'),
        'goods_id': goods_id,
        'sku_id': sku_id,
        'score': money(payload.get('score')),
        'overview': clean(payload.get('product_overview')),
        'reason': clean(payload.get('recommendation_reason')),
        'reason_source': 'block' if clean(payload.get('recommendation_reason')) else None,
        'brand': clean(brand.get('brand_name')),
        'brand_note': clean(brand.get('overview')),
        'advantage': {
            'platform': clean(advantage.get('platform_name')),
            'current': money(advantage.get('current_price')),
            'comparison': money(advantage.get('comparison_price')),
            'saving_amount': money(advantage.get('saving_amount')),
            'saving_rate': money(advantage.get('saving_rate')),
            'compared_at': clean(advantage.get('compared_at')),
            'source_url': clean(advantage.get('source_url')),
        } if advantage else None,
        'verified_at': clean(product.get('verified_at')),
        'url': None,
    }


def collect(result, url_base):
    cards = []
    for doc in result.get('context_documents') or []:
        kind = str(doc.get('kind') or '')
        if not kind.startswith(CARD_KIND_PREFIX) or doc.get('deleted'):
            continue
        block = (doc.get('value') or {}).get('block') or {}
        schema = clean(block.get('schema')) or kind[len(CARD_KIND_PREFIX):]
        payload = block.get('payload') or {}
        fallback_text = clean(block.get('fallbackText'))
        if schema in CARD_SCHEMAS:
            product = payload.get('product') or {}
            if product:
                cards.append(pick(doc, payload, product, schema, len(cards) + 1))
            elif fallback_text:
                cards.append({'schema': schema, 'rank': len(cards) + 1, 'title': fallback_text,
                              'price': None, 'currency': 'CNY', 'spec': '', 'thumbnail': '',
                              'overview': '', 'advantage': None, 'goods_id': None, 'sku_id': None,
                              'document_id': doc.get('document_id'), 'revision': doc.get('revision')})
        elif schema in LIST_SCHEMAS:
            for product in payload.get('products') or []:
                cards.append(pick(doc, payload, product, schema, len(cards) + 1))
    for card in cards:
        if card.get('goods_id'):
            params = {'goodsId': card['goods_id']}
            if card.get('sku_id'):
                params['skuId'] = card['sku_id']
            card['url'] = url_base + '?' + urllib.parse.urlencode(params)
    return cards


SECTION_START = re.compile(r'^\s*(?:#{1,6}\s+|\*\*\s*\d+\s*[.、)）]|[0-9]+[.、)）]\s*\S)')
REASON_MARK = re.compile(r'推荐理由[\s*:：]*(.*)')
ANALYSIS_MARK = re.compile(r'商品分析[\s*:：]*(.*)')
ITEM_NO = re.compile(r'^\s*(?:#{1,6}\s+)?(?:\*\*)?[0-9]+[.、)）]\s*')


def answer_sections(text):
    """按标题或编号切分答复正文，便于把每段文字归到对应商品。"""
    sections, current = [], []
    for line in text.splitlines():
        if SECTION_START.match(line) and current:
            sections.append('\n'.join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append('\n'.join(current))
    return sections


def match_section(section, card):
    if card.get('goods_id') and card['goods_id'] in section:
        return True
    if card.get('sku_id') and card['sku_id'] in section:
        return True
    title = strip_space(card.get('title'))
    return bool(title) and len(title) >= 4 and title in strip_space(section)


def section_number(section):
    first = section.splitlines()[0] if section else ''
    matched = ITEM_NO.match(first)
    return int(re.search(r'[0-9]+', matched.group(0)).group(0)) if matched else None


def match_rank(section, card):
    """新版正文以“1. 商品名”分段，序号与卡片 rank 对应。"""
    number = section_number(section)
    rank = card.get('rank')
    return isinstance(number, int) and isinstance(rank, int) and number == rank


def card_sections(sections, card):
    """优先按序号归属；正文没有序号时退回首行标题匹配，避免同一段落到多张卡。"""
    if any(section_number(section) is not None for section in sections):
        if card.get('rank') is not None:
            return [s for s in sections if match_rank(s, card)]
    return [s for s in sections if match_section(s.splitlines()[0] if s else '', card)]


def extract_marked(mark, section):
    matched = mark.search(section)
    if not matched:
        return ''
    kept = []
    for line in matched.group(1).splitlines():
        stripped = line.strip()
        if not stripped:
            if kept:
                break
            continue
        if stripped.startswith(('**', '[', '#', '!')) or REASON_MARK.match(stripped) or ANALYSIS_MARK.match(stripped):
            break
        kept.append(stripped)
    return clean(' '.join(kept))


def extract_reason(section):
    return extract_marked(REASON_MARK, section)


def extract_analysis(section):
    return extract_marked(ANALYSIS_MARK, section)


def attach_answer_reasons(cards, answer):
    """块内 recommendation_reason 为空时，从当前答复正文里按商品分段提取推荐理由。

    只搬用服务端本轮已经写出的文字，不生成、不外推；取不到就保持为空。
    """
    if not answer:
        return 0
    sections = answer_sections(answer)
    filled = 0
    for card in cards:
        if card.get('reason'):
            continue
        for section in card_sections(sections, card):
            reason = extract_reason(section)
            if reason:
                card['reason'] = reason
                card['reason_source'] = 'answer'
                filled += 1
                break
    return filled


def attach_answer_analysis(cards, answer):
    """正文“商品分析”段落同样只取自本轮答复，用于卡片里替代空的商品概述。"""
    if not answer:
        return 0
    sections = answer_sections(answer)
    filled = 0
    for card in cards:
        for section in card_sections(sections, card):
            analysis = extract_analysis(section)
            if analysis:
                card['analysis'] = analysis
                filled += 1
                break
    return filled


def referenced(card, text):
    """答复里是否明确引用该商品：商品 ID、SKU、标题或详情链接任一命中。"""
    if not text:
        return False
    flat = strip_space(text)
    if card.get('goods_id') and card['goods_id'] in text:
        return True
    if card.get('sku_id') and card['sku_id'] in text:
        return True
    title = strip_space(card.get('title'))
    if title and len(title) >= 4 and title in flat:
        return True
    return False


def theme_vars(theme):
    light = {
        '--fcard-fg': 'var(--color-text-primary,#111)',
        '--fcard-muted': 'var(--color-text-secondary,#6b6b66)',
        '--fcard-line': 'var(--color-border-tertiary,rgba(0,0,0,.14))',
        '--fcard-surface': 'var(--color-background-primary,#fff)',
        '--fcard-surface2': 'var(--color-background-secondary,#f6f6f3)',
        '--fcard-price': '#A32D2D',
        '--fcard-price-bg': '#FCEBEB',
    }
    dark = {
        '--fcard-fg': '#ECEBE6',
        '--fcard-muted': '#A9A79F',
        '--fcard-line': 'rgba(255,255,255,.16)',
        '--fcard-surface': '#1E1E1C',
        '--fcard-surface2': '#2A2A27',
        '--fcard-price': '#F09595',
        '--fcard-price-bg': '#501313',
    }
    if theme == 'dark':
        return dark
    if theme == 'light':
        return light
    return {**light, '--fcard-price': 'var(--fcard-price-auto,#A32D2D)',
            '--fcard-price-bg': 'var(--fcard-price-bg-auto,#FCEBEB)'}


def image_type(data, fallback):
    if data[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return fallback


def image_dimensions(data):
    if data[:8] == b'\x89PNG\r\n\x1a\n' and len(data) >= 24 and data[12:16] == b'IHDR':
        return int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
    if data[:6] in (b'GIF87a', b'GIF89a') and len(data) >= 10:
        return int.from_bytes(data[6:8], 'little'), int.from_bytes(data[8:10], 'little')
    if data[:4] == b'RIFF' and data[8:16] == b'WEBPVP8X' and len(data) >= 30:
        return 1 + int.from_bytes(data[24:27], 'little'), 1 + int.from_bytes(data[27:30], 'little')
    if data[:2] == b'\xff\xd8':
        pos = 2
        while pos + 4 <= len(data):
            if data[pos] != 0xff: return None
            while pos < len(data) and data[pos] == 0xff: pos += 1
            if pos >= len(data): return None
            marker = data[pos]; pos += 1
            if marker in (0xd8, 0xd9, 0x01) or 0xd0 <= marker <= 0xd7: continue
            if pos + 2 > len(data): return None
            length = int.from_bytes(data[pos:pos+2], 'big')
            if length < 2 or pos + length > len(data): return None
            if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf) and length >= 7:
                return int.from_bytes(data[pos+5:pos+7], 'big'), int.from_bytes(data[pos+3:pos+5], 'big')
            pos += length
    return None


def thumbnail_data(url, timeout):
    """通过商品图片源生成缩略图，并校验尺寸和大小。"""
    def valid(data, expected=None):
        kind = image_type(data, None)
        dimensions = image_dimensions(data)
        if not kind or (expected and kind != expected) or len(data) > IMAGE_MAX_BYTES or not dimensions or not all(0 < x <= IMAGE_MAX_SIDE for x in dimensions):
            return None
        return data, kind
    if url.startswith('data:'):
        try:
            prefix, encoded = url.split(',', 1)
            if prefix not in ('data:image/png;base64', 'data:image/jpeg;base64', 'data:image/gif;base64', 'data:image/webp;base64') or len(encoded) > ((IMAGE_MAX_BYTES + 2) // 3) * 4:
                return None
            data = base64.b64decode(encoded, validate=True)
            return valid(data, prefix[5:-7])
        except (ValueError, TypeError):
            return None
    try:
        parsed = urllib.parse.urlsplit(url)
        allowed = parsed.scheme == 'https' and parsed.hostname == 'filtering-tech-product-data.oss-cn-beijing.aliyuncs.com' and not parsed.username and not parsed.password and parsed.port in (None, 443)
    except ValueError:
        return None
    if not allowed:
        return None
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    if all(key == 'x-oss-process' for key, _ in params):
        urls = [urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                'x-oss-process=image/resize,m_lfit,w_%d,h_%d/quality,q_%d/format,jpg' % (size, size, quality), ''))
                for size, quality in ((160, 65), (120, 50), (80, 35))]
    else:
        urls = [url]  # 保留签名及其他参数，不修改已有语义。
    opener = urllib.request.build_opener(NoRedirect())
    for candidate in urls:
        try:
            req = urllib.request.Request(candidate, headers={'User-Agent': 'filtalgo-render-cards/1'})
            with opener.open(req, timeout=timeout) as response:
                data = response.read(IMAGE_MAX_BYTES + 1)
            image = valid(data)
            if image:
                return image
        except (OSError, ValueError):
            continue
    return None


def inline_images(cards, timeout):
    """将图片压缩并嵌入卡片，不创建图片文件。"""
    for card in cards:
        thumb = card.get('thumbnail')
        if not thumb:
            continue
        image = thumbnail_data(thumb, timeout)
        card['thumbnail'] = ('data:%s;base64,%s' % (image[1], base64.b64encode(image[0]).decode('ascii'))) if image else ''


def render_widget(cards, meta, theme, images=True):
    style_vars = ';'.join('%s:%s' % (k, v) for k, v in theme_vars(theme).items())
    dark_rule = ''
    if theme == 'auto':
        dark_rule = ('@media (prefers-color-scheme:dark){.fcard-root{--fcard-price-auto:#F09595;'
                     '--fcard-price-bg-auto:#501313}}')
    head_style = ('position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap')
    names = '、'.join(c['title'] for c in cards[:3])
    summary = '共 %d 件商品：%s%s' % (len(cards), names, '等' if len(cards) > 3 else '')
    out = ['<style>.fcard-root{%s;font-family:var(--font-sans,system-ui,-apple-system,"Segoe UI",sans-serif)}'
           '.fcard-root .fcard-t{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}'
           '.fcard-root .fcard-o{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}'
           '.fcard-root .fcard-r{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}'
           '.fcard-root a{text-decoration:none;color:inherit}'
           '.fcard-root a:hover .fcard-go{text-decoration:underline}%s</style>' % (style_vars, dark_rule)]
    out.append('<div class="fcard-root" style="display:flex;flex-direction:column;gap:10px">')
    out.append('<h2 style="%s">%s</h2>' % (head_style, html.escape(summary)))
    for card in cards:
        price = card.get('price')
        price_html = ('<span style="font-size:16px;font-weight:500;color:var(--fcard-price)">¥%s</span>'
                      % html.escape(price)) if price else ''
        origin = card.get('origin_price')
        origin_html = ('<span style="font-size:12px;color:var(--fcard-muted);text-decoration:line-through">¥%s</span>'
                       % html.escape(origin)) if origin else ''
        chips = []
        if card.get('spec') and card['spec'] != '默认':
            chips.append(html.escape(card['spec']))
        for dimension in card.get('dimensions') or []:
            chips.append(html.escape(dimension))
        availability = AVAILABILITY.get(card.get('availability') or '', '')
        if availability:
            chips.append(availability)
        if card.get('brand'):
            chips.append(html.escape(card['brand']))
        chip_html = ''.join(
            '<span style="font-size:11px;line-height:1;padding:4px 6px;border-radius:4px;'
            'background:var(--fcard-surface2);color:var(--fcard-muted)">%s</span>' % c for c in chips)
        advantage = card.get('advantage') or {}
        advantage_html = ''
        if advantage.get('platform') and advantage.get('comparison'):
            rate = advantage.get('saving_rate')
            rate_chip = ('<span style="font-size:11px;line-height:1;padding:4px 6px;border-radius:4px;'
                         'background:var(--fcard-price-bg);color:var(--fcard-price)">省 %s%%</span>'
                         % html.escape(rate)) if rate else ''
            advantage_html = (
                '%s<span style="font-size:12px;color:var(--fcard-muted)">%s ¥%s，现价 ¥%s</span>'
                % (rate_chip, html.escape(advantage['platform']),
                   html.escape(advantage['comparison']), html.escape(price or '?')))
        go_html = ('<span class="fcard-go" style="font-size:12px;color:var(--fcard-muted);'
                   'white-space:nowrap;margin-left:auto">查看商品 ›</span>') if card.get('url') else ''
        footer_html = ''
        if advantage_html or go_html:
            footer_html = ('<div style="display:flex;align-items:center;gap:6px;margin-top:8px">%s%s</div>'
                           % (advantage_html, go_html))
        thumb = card.get('thumbnail') if images else ''
        thumb_html = (
            '<div style="width:76px;height:76px;flex:0 0 76px;border-radius:var(--border-radius-md,8px);'
            'background:var(--fcard-surface2);overflow:hidden">%s</div>'
            % ('<img src="%s" alt="" style="width:100%%;height:100%%;object-fit:cover;display:block">'
               % html.escape(thumb, quote=True) if thumb else ''))
        score = card.get('score')
        rank_badge = ('<span style="font-size:11px;line-height:1;padding:4px 6px;border-radius:4px;'
                      'background:var(--fcard-price-bg);color:var(--fcard-price);font-weight:500">%s</span>'
                      % html.escape(str(card.get('rank'))))
        score_html = ('<span style="font-size:11px;color:var(--fcard-muted)">评分 %s</span>'
                      % html.escape(score)) if score else ''
        overview = card.get('analysis') or card.get('overview')
        overview_html = ('<p class="fcard-o" style="font-size:12px;line-height:1.55;color:var(--fcard-muted);'
                         'margin:6px 0 0">%s</p>' % html.escape(overview)) if overview else ''
        subtitle_html = ('<p style="font-size:11px;line-height:1.45;color:var(--fcard-muted);'
                         'margin:2px 0 0">%s</p>' % html.escape(card['subtitle'])) if card.get('subtitle') else ''
        reason = card.get('reason')
        reason_html = ''
        if reason:
            reason_html = ('<div style="margin-top:8px;padding:7px 9px;border-radius:6px;'
                           'background:var(--fcard-surface2)">'
                           '<span style="font-size:11px;color:var(--fcard-price);margin-right:6px;'
                           'white-space:nowrap">推荐理由</span>'
                           '<span class="fcard-r" style="font-size:12px;line-height:1.55;'
                           'color:var(--fcard-fg)">%s</span></div>' % html.escape(reason))
        brand_note_html = ''
        if card.get('brand_note'):
            prefix = ('品牌 %s · ' % card['brand']) if card.get('brand') else '品牌背景 · '
            brand_note_html = ('<p class="fcard-o" style="font-size:11px;line-height:1.5;'
                               'color:var(--fcard-muted);margin:6px 0 0">%s%s</p>'
                               % (html.escape(prefix), html.escape(card['brand_note'])))
        body = (
            '<div style="min-width:0;flex:1 1 auto">'
            '<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">%s%s%s</div>'
            '<p class="fcard-t" style="font-size:13px;line-height:1.45;font-weight:500;margin:0">%s</p>'
            '%s<div style="display:flex;align-items:baseline;gap:6px;margin-top:5px">%s%s</div>'
            '%s%s%s%s</div>'
            % (rank_badge, score_html,
               ('<span style="display:flex;gap:6px;flex-wrap:wrap">%s</span>' % chip_html) if chip_html else '',
               html.escape(card['title']), subtitle_html, price_html, origin_html,
               overview_html, reason_html, brand_note_html, footer_html))
        card_html = ('<div style="display:flex;gap:12px;padding:12px;border-radius:var(--border-radius-lg,12px);'
                     'border:0.5px solid var(--fcard-line);background:var(--fcard-surface)">%s%s</div>'
                     % (thumb_html, body))
        if card.get('url'):
            card_html = ('<a href="%s" target="_blank" rel="noopener noreferrer" '
                         'style="display:block">%s</a>'
                         % (html.escape(card['url'], quote=True), card_html))
        out.append(card_html)
    if meta.get('footer'):
        out.append('<div style="font-size:11px;color:var(--fcard-muted);padding:0 2px">%s</div>'
                   % html.escape(meta['footer']))
    out.append('</div>')
    return '\n'.join(out)


PALETTE = {
    'reset': '\033[0m',
    'bold': '\033[1m',
    'dim': '\033[2m',
    'price': '\033[38;5;131m',
}


def char_width(ch):
    return 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1


def text_width(text):
    return sum(char_width(ch) for ch in text)


HANGING = '，。、；：！？）〕」』】…%％,.;:!?)'


def wrap_width(text, limit):
    """按显示宽度折行，中文按两列计；行首禁则用悬挂标点处理。"""
    lines, current, width = [], '', 0
    for ch in text:
        w = char_width(ch)
        if width + w > limit and current and ch not in HANGING:
            lines.append(current.rstrip())
            current, width = '', 0
            if ch == ' ':
                continue
        current += ch
        width += w
    if current.strip():
        lines.append(current.rstrip())
    return lines or ['']


def paint(text, style, color):
    if not color or not text:
        return text
    return PALETTE[style] + text + PALETTE['reset']


def hyperlink(url, color):
    """彩色模式用 OSC 8 可点击链接；无色模式直接给可复制的原始地址。"""
    if not url:
        return ''
    if not color:
        return url
    return '\033]8;;%s\033\\%s%s%s\033]8;;\033\\' % (url, PALETTE['dim'], '打开商品页 ›', PALETTE['reset'])


def render_text(cards, meta, color, width, indent='  '):
    body = max(28, width - text_width(indent))
    rank_width = max(len(str(card.get('rank') or i + 1)) for i, card in enumerate(cards))
    out = []
    header = meta.get('title') or '%d 件商品' % len(cards)
    out.append(paint(header, 'bold', color))
    out.append(paint('─' * min(width, max(20, text_width(header))), 'dim', color))
    for index, card in enumerate(cards):
        if index:
            out.append('')
        rank = str(card.get('rank') or index + 1).rjust(rank_width)
        title_lines = wrap_width(card['title'], body - rank_width - 1)
        out.append('%s%s %s' % (indent, paint(rank, 'price', color),
                                paint(title_lines[0], 'bold', color)))
        pad = ' ' * (text_width(indent) + rank_width + 1)
        for line in title_lines[1:]:
            out.append(pad + paint(line, 'bold', color))
        money_text = ('¥' + card['price']) if card.get('price') else '价格未提供'
        origin = card.get('origin_price')
        price_line = paint(money_text, 'price', color)
        if origin:
            price_line += ' ' + paint('¥' + origin, 'dim', color)
        bits = []
        if card.get('spec') and card['spec'] != '默认':
            bits.append(card['spec'])
        if AVAILABILITY.get(card.get('availability') or ''):
            bits.append(AVAILABILITY[card['availability']])
        if card.get('score'):
            bits.append('评分 ' + card['score'])
        if card.get('brand'):
            bits.append(card['brand'])
        if bits:
            price_line += paint('  ·  ' + ' · '.join(bits), 'dim', color)
        out.append(indent + price_line)
        overview = card.get('analysis') or card.get('overview')
        if overview:
            for line in wrap_width(overview, body):
                out.append(indent + paint(line, 'dim', color))
        reason = card.get('reason')
        if reason:
            lines = wrap_width(reason, body - 5)
            out.append(indent + paint('理由', 'price', color) + ' ' + lines[0])
            pad = ' ' * (text_width(indent) + 5)
            for line in lines[1:]:
                out.append(pad + line)
        if card.get('brand_note'):
            prefix = ('品牌 %s：' % card['brand']) if card.get('brand') else '品牌：'
            for line in wrap_width(prefix + card['brand_note'], body):
                out.append(indent + paint(line, 'dim', color))
        advantage = card.get('advantage') or {}
        if advantage.get('platform') and advantage.get('comparison'):
            rate = ('省 %s%%' % advantage['saving_rate']) if advantage.get('saving_rate') else '比价'
            out.append(indent + paint(rate, 'price', color) + '  '
                       + paint('%s ¥%s，现价 ¥%s' % (advantage['platform'],
                                                     advantage['comparison'],
                                                     advantage.get('current') or card.get('price') or '?'),
                               'dim', color))
        if card.get('url'):
            out.append(indent + hyperlink(card['url'], color))
    if meta.get('footer'):
        out.append('')
        out.append(paint(meta['footer'], 'dim', color))
    return '\n'.join(out) + '\n'


def render_markdown(cards, meta):
    lines = []
    if meta.get('title'):
        lines.append('**%s**' % meta['title'])
        lines.append('')
    for card in cards:
        price = ('¥' + card['price']) if card.get('price') else '价格未提供'
        origin = ('（原价 ¥%s）' % card['origin_price']) if card.get('origin_price') else ''
        bits = [price + origin]
        if card.get('spec') and card['spec'] != '默认':
            bits.append('规格 ' + card['spec'])
        if card.get('score'):
            bits.append('评分 ' + card['score'])
        if AVAILABILITY.get(card.get('availability') or ''):
            bits.append(AVAILABILITY[card['availability']])
        lines.append('%s. **%s** · %s' % (card.get('rank') or '-', card['title'], ' · '.join(bits)))
        overview = card.get('analysis') or card.get('overview')
        if overview:
            lines.append('   %s' % overview)
        if card.get('reason'):
            lines.append('   > 推荐理由：%s' % card['reason'])
        if card.get('brand_note'):
            label = ('品牌 %s' % card['brand']) if card.get('brand') else '品牌背景'
            lines.append('   %s：%s' % (label, card['brand_note']))
        advantage = card.get('advantage') or {}
        if advantage.get('platform') and advantage.get('comparison'):
            lines.append('   比价：%s ¥%s，当前 ¥%s，省 %s%%'
                         % (advantage['platform'], advantage['comparison'],
                            advantage.get('current') or card.get('price') or '?',
                            advantage.get('saving_rate') or '?'))
        if card.get('url'):
            lines.append('   [查看商品](%s)' % card['url'])
        lines.append('')
    if meta.get('footer'):
        lines.append('_%s_' % meta['footer'])
    return '\n'.join(lines).rstrip() + '\n'
