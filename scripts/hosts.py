"""宿主枚举、别名归一与渲染策略（路由表）。

宿主只能从固定枚举中选择；未知值一律降级 default，行为与 2.3.x 一致。
"""
HOSTS = ('today', 'workbuddy', 'doubao', 'qianwen', 'lingguang')

ALIASES = {
    'today': 'today',
    'workbuddy': 'workbuddy',
    'work buddy': 'workbuddy',
    'doubao': 'doubao',
    'doubao work': 'doubao',
    '豆包': 'doubao',
    '豆包工作': 'doubao',
    'qianwen': 'qianwen',
    '千问': 'qianwen',
    '千问办公': 'qianwen',
    '千问 go': 'qianwen',
    'lingguang': 'lingguang',
    '灵光': 'lingguang',
    'default': 'default',
    '其他': 'default',
    '未知': 'default',
    'unsure': 'default',
}

PROFILES = {
    'workbuddy': {'format': 'html', 'images': 'remote', 'cards': 'required'},
    'doubao': {'format': 'md', 'images': 'local_first', 'cards': 'required'},
    'lingguang': {'format': 'md', 'images': 'local_first', 'cards': 'none'},
    'today': {'format': 'md', 'images': 'none', 'cards': 'optional'},
    'qianwen': {'format': 'md', 'images': 'remote', 'cards': 'optional'},
    'default': {'format': 'md', 'images': 'remote', 'cards': 'optional'},
}


def normalize(value):
    """把宿主写法归一为枚举值；无法识别返回 None。"""
    if not isinstance(value, str):
        return None
    key = ' '.join(value.strip().lower().split())
    key = ALIASES.get(key, key)
    return key if key in HOSTS or key == 'default' else None


def profile(host):
    """返回渲染策略；未知宿主走 default。"""
    return PROFILES.get(host) or PROFILES['default']
