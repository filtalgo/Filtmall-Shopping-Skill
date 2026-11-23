"""Anonymous Gateway URL resolution and idempotent Markdown entry rendering."""
import json
import re
import time
import uuid
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


def safe_url(value, hosts):
    try:
        p = urlsplit(value)
        return (isinstance(value, str) and len(value) <= 4096
                and not any(c.isspace() or ord(c) < 32 for c in value)
                and p.scheme == 'https' and p.hostname in hosts
                and not p.username and not p.password and not p.fragment
                and p.port in (None, 443) and p.path.startswith('/')
                and not p.path.startswith('//') and '\\' not in value)
    except (ValueError, TypeError, AttributeError):
        return False


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def resolve_url(url):
    """Use the deployed public MCP tool, never member or Control credentials."""
    if not safe_url(url, ('m.filtalgo.com',)):
        raise ValueError('Unsupported URL')
    identifier = str(uuid.uuid4())
    name = 'shopping.navigation.resolve_url_link'
    version = '2026-07-28'
    body = {'jsonrpc': '2.0', 'id': identifier, 'method': 'tools/call',
            'params': {'name': name, 'arguments': {'url': url}, '_meta': {
                'io.modelcontextprotocol/protocolVersion': version,
                'io.modelcontextprotocol/clientCapabilities': {},
                'io.modelcontextprotocol/clientInfo': {'name': 'filtmall-shopping', 'version': '2.3.3'}}}}
    req = Request('https://filtalgo.com/gateway/mcp', json.dumps(body).encode(), {
        'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
        'Mcp-Protocol-Version': version, 'Mcp-Method': 'tools/call', 'Mcp-Name': name}, method='POST')
    with build_opener(NoRedirect()).open(req, timeout=3) as response:
        data = json.load(response)
    if data.get('jsonrpc') != '2.0' or data.get('id') != identifier or data.get('error'):
        raise ValueError('Invalid Gateway response')
    result = data.get('result')
    if not isinstance(result, dict) or result.get('isError'):
        raise ValueError('Gateway tool failed')
    if isinstance(result.get('structuredContent'), dict):
        return result['structuredContent']
    texts = [item.get('text') for item in result.get('content', [])
             if isinstance(item, dict) and item.get('type') == 'text']
    if len(texts) != 1:
        raise ValueError('Missing Gateway URL data')
    return json.loads(texts[0])


def normalized(value):
    if not isinstance(value, dict):
        return None
    value = value.get('result', value)
    if (isinstance(value, dict) and safe_url(value.get('h5_url'), ('m.filtalgo.com',))
            and safe_url(value.get('mp_url'), ('wxaurl.cn', 'wxmpurl.cn'))):
        return value
    return None


def closing(text, start, left, right):
    depth, i = 1, start
    while i < len(text):
        if text[i] == '\\':
            i += 2
            continue
        if text[i] == left:
            depth += 1
        if text[i] == right:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def rewrite_markdown(markdown, resolve=resolve_url, cache=None, max_links=10):
    """Preserve images, code, OAuth URLs, unsafe URLs and existing entry pairs.

    可解析的 H5 业务链接改写成紧凑双入口：`[电脑端](…) ｜ [手机端](…)`，
    已生成的入口不再改写，保证多次调用幂等。
    """
    cache = {} if cache is None else cache
    fence = None
    output = []
    for line in markdown.splitlines(keepends=True):
        match = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if match:
            marker = match[1]
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            output.append(line)
            continue
        if fence:
            output.append(line)
            continue
        i, pieces = 0, []
        while i < len(line):
            if line[i] == '\\':
                pieces.append(line[i:i+2]); i += 2
                continue
            if line[i] == '`':
                ticks = re.match(r'`+', line[i:])[0]
                end = line.find(ticks, i + len(ticks))
                end = len(line) if end < 0 else end + len(ticks)
                pieces.append(line[i:end]); i = end
                continue
            image = line.startswith('![', i)
            start = i + 1 if image else i
            if line[start:start+1] != '[':
                pieces.append(line[i]); i += 1
                continue
            label = closing(line, start + 1, '[', ']')
            end = closing(line, label + 2, '(', ')') if label >= 0 and line[label+1:label+2] == '(' else -1
            if end < 0:
                pieces.append(line[i]); i += 1
                continue
            label_text = line[start+1:label]
            url = line[label+2:end]
            original = line[i:end+1]
            if not image and label_text in ('电脑端', '手机端'):
                pieces.append(original); i = end + 1
                continue
            if (not image and safe_url(url, ('m.filtalgo.com',))
                    and urlsplit(url).path.rstrip('/') not in ('/oauth/device', '/pages/oauth/device')):
                if url not in cache and len(cache) < max_links:
                    try:
                        cache[url] = normalized(resolve(url))
                    except Exception:
                        cache[url] = None
                value = cache.get(url)
                if value:
                    original = '[电脑端](%s) \uFF5C [手机端](%s)' % (value['h5_url'], value['mp_url'])
            pieces.append(original)
            i = end + 1
        output.append(''.join(pieces))
    return ''.join(output)


def finalize_payload(payload, resolve=None):
    """One cache/budget per response, shared across all Markdown artifacts."""
    cache = {}
    deadline = time.monotonic() + 5
    resolver = resolve or resolve_url
    def bounded_resolve(url):
        if time.monotonic() >= deadline:
            return None
        return resolver(url)
    for key in ('display_content', 'answer', 'cards_markdown', 'cart_content',
                'checkout_content', 'after_sale_content', 'logistics_content',
                'address_content', 'customer_service_content'):
        if isinstance(payload.get(key), str) and (key in ('display_content', 'answer', 'cards_markdown')
                                                   or payload.get('_format') in ('md', 'markdown')):
            payload[key] = rewrite_markdown(payload[key], bounded_resolve, cache)
    return payload
