#!/usr/bin/env python3
"""用当前环境的地区目录解析三级名称，街道及门牌保留为详细地址。"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[1] / 'data' / 'regions-pre.json'
LEVELS = ('province', 'city', 'district', 'street')
SEPARATORS = ' \t\r\n,，/、>＞'
MUNICIPALITIES = {'北京', '上海', '天津', '重庆'}
# 仅用于自治州/自治县/自治旗的名称尾部，不对普通地名做任意截断。
AUTONOMOUS_ETHNIC_SUFFIX = re.compile(
    r'(?:土家族|朝鲜族|达斡尔族|鄂温克族|仡佬族|布依族|仫佬族|毛南族|'
    r'哈尼族|纳西族|拉祜族|布朗族|独龙族|普米族|傈僳族|裕固族|景颇族|'
    r'哈萨克族|东乡族|保安族|撒拉族|蒙古族|满族|回族|畲族|苗族|瑶族|'
    r'侗族|壮族|黎族|羌族|彝族|藏族|水族|傣族|佤族|白族|怒族|土族|'
    r'柯尔克孜|哈萨克|塔吉克|蒙古|锡伯|各族)+$'
)


def strip_separators(value):
    return re.sub(r'^[\s,，/、>＞]+', '', value)


class RegionMatchError(ValueError):
    def __init__(self, code, level, parent, candidates):
        self.result = {'ok': False, 'error': code, 'level': level,
                       'parent_id': parent, 'candidates': candidates,
                       'message': '请明确%s；不自动选择候选或推断地区。' % level}
        super().__init__(self.result['message'])


def normalize_name(value):
    return ''.join(unicodedata.normalize('NFKC', value).split())


def aliases(node):
    """仅去已知行政后缀，不做包含匹配或编辑距离纠错。"""
    name = normalize_name(node['name'])
    suffixes = {
        'province': ('壮族自治区', '回族自治区', '维吾尔自治区', '自治区', '特别行政区', '省', '市'),
        'city': ('自治州', '地区', '市', '盟'),
        'district': ('自治县', '自治旗', '区', '县', '市'),
        'street': ('街道', '乡', '镇'),
    }
    names = {name}
    for suffix in suffixes[node['level']]:
        if name.endswith(suffix) and len(name) > len(suffix):
            stem = name[:-len(suffix)]
            names.add(stem)
            if suffix in ('自治州', '自治县', '自治旗'):
                short = AUTONOMOUS_ETHNIC_SUFFIX.sub('', stem)
                # 鄂温克族自治旗/东乡族自治县等本身以民族名命名。
                if not short and stem.endswith('族'):
                    short = stem[:-1]
                if len(short) >= 2:
                    names.add(short)
            break
    return names


def validate_directory(data):
    if not isinstance(data, dict) or not isinstance(data.get('environment'), str) or not data['environment'].strip():
        raise ValueError('地区目录必须标明 environment')
    nodes = data.get('nodes')
    if not isinstance(nodes, list) or not nodes or len(nodes) > 200000:
        raise ValueError('地区目录节点数量无效')
    by_id = {}
    for node in nodes:
        if not isinstance(node, dict) or any(not isinstance(node.get(k), str) or not node[k].strip() for k in ('id', 'parent_id', 'name', 'level')):
            raise ValueError('地区节点字段无效')
        if node['level'] not in LEVELS or node['id'] == '0' or node['id'] in by_id:
            raise ValueError('地区节点级别或ID无效/重复')
        by_id[node['id']] = node
    for node in nodes:
        parent = by_id.get(node['parent_id'])
        if node['level'] == 'province':
            valid = node['parent_id'] == '0'
        else:
            valid = parent is not None and LEVELS.index(parent['level']) + 1 == LEVELS.index(node['level'])
        if not valid:
            raise ValueError('地区目录父子关系无效')
    return nodes


def select_one(matches, level, parent):
    if len(matches) != 1:
        raise RegionMatchError('REGION_NOT_UNIQUE' if matches else 'REGION_NOT_FOUND',
                               level, parent, matches)
    return matches[0]


def match_name(value, children, level, parent):
    value = normalize_name(value)
    exact = [node for node in children if normalize_name(node['name']) == value]
    return select_one(exact or [node for node in children if value in aliases(node)], level, parent)


def named_path(values, nodes, use_ids=False):
    parent, path = '0', []
    for value, level in zip(values, LEVELS[:3]):
        children = [node for node in nodes if node['parent_id'] == parent and node['level'] == level]
        node = (select_one([n for n in children if n['id'] == value.strip()], level, parent)
                if use_ids else match_name(value, children, level, parent))
        path.append(node)
        parent = node['id']
    return path


def text_path(address, nodes):
    remaining, parent, path = strip_separators(address), '0', []
    for level in LEVELS[:3]:
        children = [node for node in nodes if node['parent_id'] == parent and node['level'] == level]
        matches = [(node, name) for node in children for name in aliases(node)
                   if normalize_name(remaining[:len(name)]) == name]
        if not matches and level == 'city' and len(children) == 1 and aliases(path[0]) & MUNICIPALITIES:
            # 直辖市省/市同名且市节点唯一时，允许原文只写一次。
            node = children[0]
        else:
            longest = max((len(name) for _, name in matches), default=0)
            longest_matches = [(node, name) for node, name in matches if len(name) == longest]
            exact = [(node, name) for node, name in longest_matches if name == normalize_name(node['name'])]
            matched = {node['id']: (node, name) for node, name in (exact or longest_matches)}
            node = select_one([item[0] for item in matched.values()], level, parent)
            name = matched[node['id']][1]
            tail = remaining[len(name):]
            if level == 'district' and name != normalize_name(node['name']) and tail and not (tail[0].isspace() or tail[0] in SEPARATORS):
                raise RegionMatchError('REGION_BOUNDARY_UNCLEAR', level, parent, [node])
            remaining = strip_separators(tail)
        path.append(node)
        parent = node['id']
    return path, remaining.strip()


def string_list(value, lengths):
    if not isinstance(value, list) or len(value) not in lengths or any(not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError('请提供三个省市区名称；prepare 可多提供一个街道/乡镇字符串')
    return [v.strip() for v in value]


def lookup(request, data):
    if not isinstance(request, dict):
        raise ValueError('请求必须为 JSON 对象')
    nodes = validate_directory(data)
    if request.get('environment') != data['environment']:
        return {'ok': False, 'error': 'ENVIRONMENT_MISMATCH',
                'message': '必须使用与请求环境一致的地区目录；内置目录仅用于pre，生产须提供生产目录。'}
    op = request.get('op', 'prepare')
    if op == 'children':
        parent = request.get('parent_id', '0')
        if not isinstance(parent, str):
            raise ValueError('parent_id 必须是字符串')
        if parent != '0' and not any(n['id'] == parent for n in nodes):
            raise ValueError('找不到上级地区')
        return {'ok': True, 'environment': data['environment'], 'parent_id': parent,
                'regions': [n for n in nodes if n['parent_id'] == parent]}
    if op not in ('resolve', 'prepare'):
        raise ValueError('op 必须是 children、resolve 或 prepare')
    detail = request.get('detail', '')
    if not isinstance(detail, str):
        raise ValueError('detail 必须是字符串')
    detail = detail.strip()
    detail_required = not bool(detail)
    try:
        if op == 'resolve':
            names, ids = request.get('names'), request.get('ids')
            if (names is None) == (ids is None) or 'address' in request:
                raise ValueError('resolve 请提供 names 或 ids 中的一项')
            path = named_path(string_list(names if names is not None else ids, (3,)), nodes, ids is not None)
        else:
            if 'ids' in request or ('address' in request) == ('names' in request):
                raise ValueError('prepare 请提供 address 或 names 中的一项，不接受ids')
            if 'address' in request:
                address = request['address']
                if 'detail' in request or not isinstance(address, str) or not address.strip() or len(address) > 4096:
                    raise ValueError('address 须为非空地址文本，不能同时传入detail，最长4096字符')
                path, detail = text_path(address, nodes)
                detail_required = not bool(detail)
            else:
                names = string_list(request['names'], (3, 4))
                path = named_path(names[:3], nodes)
                if len(names) == 4 and detail == names[3]:
                    detail_required = True
                if len(names) == 4 and not detail.startswith(names[3]):
                    detail = names[3] + detail
        # 只写到街道/乡镇仍须补充位置；不强制门牌必须含数字。
        detail_required = detail_required or bool(re.fullmatch(r'.+(?:街道|乡|镇)', detail))
        ids, names = [n['id'] for n in path], [n['name'] for n in path]
        return {'ok': True, 'environment': data['environment'], 'ids': ids, 'names': names,
                'region_id_path': ','.join(ids), 'region_path': ','.join(names),
                'detail': detail, 'detail_required': detail_required, 'requires_confirmation': True,
                'snapshot_at': data.get('retrieved_at')}
    except RegionMatchError as exc:
        return exc.result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-file', type=Path, default=DATA_PATH,
                        help='当前环境的可信地区目录；默认内置pre快照，不能用于prod')
    args = parser.parse_args()
    try:
        request = json.load(sys.stdin)
        data = json.loads(args.data_file.read_text(encoding='utf-8-sig'))
        result = lookup(request, data)
    except (ValueError, KeyError, OSError) as exc:
        result = {'ok': False, 'error': 'INVALID_REQUEST_OR_DATA', 'message': str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
