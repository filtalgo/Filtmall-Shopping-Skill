#!/usr/bin/env python3
"""Query the bundled pre region snapshot using one JSON request on stdin."""
import json
import sys
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[1] / 'data' / 'regions-pre.json'


def lookup(request, data):
    if not isinstance(request, dict):
        raise ValueError('请求必须为 JSON 对象')
    nodes = data['nodes']
    op = request.get('op')
    if op == 'children':
        parent = request.get('parent_id', '0')
        if not isinstance(parent, str):
            raise ValueError('parent_id 必须是字符串')
        if parent != '0' and not any(n['id'] == parent for n in nodes):
            raise ValueError('找不到上级地区')
        return {'ok': True, 'environment': data['environment'], 'parent_id': parent,
                'regions': [n for n in nodes if n['parent_id'] == parent]}
    if op == 'resolve':
        names, ids = request.get('names'), request.get('ids')
        if (names is None) == (ids is None):
            raise ValueError('请提供 names 或 ids 中的一项')
        values = names if names is not None else ids
        if not isinstance(values, list) or len(values) != 3 or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError('需要依次提供省、市、区三个非空字符串')
        parent, path = '0', []
        for value, level in zip(values, ('province', 'city', 'district')):
            matches = [n for n in nodes if n['parent_id'] == parent and n['level'] == level
                       and n['name' if names is not None else 'id'] == value.strip()]
            if len(matches) != 1:
                return {'ok': False, 'error': 'REGION_NOT_UNIQUE', 'level': level,
                        'parent_id': parent, 'candidates': matches}
            path.append(matches[0])
            parent = matches[0]['id']
        return {'ok': True, 'environment': data['environment'], 'ids': [n['id'] for n in path],
                'names': [n['name'] for n in path], 'snapshot_at': data['retrieved_at']}
    raise ValueError('op 必须是 children 或 resolve')


def main():
    try:
        request = json.load(sys.stdin)
        data = json.loads(DATA_PATH.read_text(encoding='utf8'))
        result = lookup(request, data)
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        result = {'ok': False, 'error': 'INVALID_REQUEST_OR_DATA', 'message': str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
