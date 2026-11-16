"""Shared presentation primitives for product, cart and shipping address cards."""
import html

FONT = 'var(--font-sans,system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif)'
LIGHT = {'fg':'#111', 'muted':'#6b6b66', 'line':'rgba(0,0,0,.14)',
         'surface':'#fff', 'surface2':'#f6f6f3', 'accent':'#A32D2D', 'accent-bg':'#FCEBEB'}
DARK = {'fg':'#ECEBE6', 'muted':'#A9A79F', 'line':'rgba(255,255,255,.16)',
        'surface':'#1E1E1C', 'surface2':'#2A2A27', 'accent':'#F09595', 'accent-bg':'#501313'}
HOST = {'fg':'color-text-primary', 'muted':'color-text-secondary', 'line':'color-border-tertiary',
        'surface':'color-background-primary', 'surface2':'color-background-secondary'}


def theme_vars(theme='auto', prefix='fm', accent='accent'):
    values = {}
    for name, light in LIGHT.items():
        token = name.replace('accent', accent)
        if theme == 'dark': value = DARK[name]
        else:
            fallback = 'var(--%s-%s-auto,%s)' % (prefix, token, light) if theme == 'auto' else light
            value = 'var(--%s,%s)' % (HOST[name], fallback) if name in HOST else fallback
        values['--%s-%s' % (prefix, token)] = value
    return values


def dark_rule(selector, prefix='fm', accent='accent'):
    tokens = ';'.join('--%s-%s-auto:%s' % (prefix, name.replace('accent', accent), value)
                      for name, value in DARK.items())
    return '@media (prefers-color-scheme:dark){%s{%s}}' % (selector, tokens)


def theme_css(selector, prefix='fm', accent='accent'):
    tokens = ';'.join('%s:%s' % item for item in theme_vars('auto', prefix, accent).items())
    return ('%s{%s;--commerce-card-radius:var(--border-radius-lg,12px);font-family:%s;color:var(--%s-fg)}'
            % (selector, tokens, FONT, prefix)) + dark_rule(selector, prefix, accent)


def card_style(prefix='fm'):
    return ('padding:12px;border-radius:var(--commerce-card-radius,var(--border-radius-lg,12px));'
            'border:.5px solid var(--%s-line);background:var(--%s-surface)' % (prefix, prefix))


def card_rule(selector, prefix='fm'):
    return '%s{%s}' % (selector, card_style(prefix))


def html_page(fragment, title):
    return ('<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="color-scheme" content="light dark"><title>%s</title>'
            '<style>body{margin:0;background:var(--color-background-secondary,#f6f6f3);'
            'font-family:%s}.commerce-page{max-width:760px;margin:0 auto;padding:28px 20px;min-width:0}'
            '@media(max-width:480px){.commerce-page{padding:18px 12px}}'
            '@media(prefers-color-scheme:dark){body{background:var(--color-background-secondary,#171715)}}'
            '</style></head><body><main class="commerce-page">%s</main></body></html>\n'
            % (html.escape(title), FONT, fragment))
