import copy
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import address_cards
import cards
import service
from test_address_outputs import snapshot


class Rows(HTMLParser):
    def __init__(self, content):
        super().__init__(); self.rows = []; self.active = None; self.feed(content)
    def handle_starttag(self, tag, attrs):
        if tag == 'li': self.active = ''
    def handle_data(self, data):
        if self.active is not None: self.active += data
    def handle_endtag(self, tag):
        if tag == 'li' and self.active is not None:
            self.rows.append(self.active); self.active = None


class CommerceVisualTests(unittest.TestCase):
    def test_one_list_keeps_default_and_selected_on_their_own_rows(self):
        for fmt in ('html', 'widget', 'md'):
            result = service.render({'address_snapshots': [snapshot(), snapshot('checkout', 'CART')]}, fmt, 0)
            content = result['address_content']
            self.assertEqual(content.count('默认地址'), 1)
            self.assertEqual(content.count('本次已选中'), 1)
            if fmt != 'md':
                rows = Rows(content).rows
                self.assertEqual(len(rows), 2)
                self.assertIn('默认地址', rows[0]); self.assertNotIn('本次已选中', rows[0])
                self.assertIn('本次已选中', rows[1]); self.assertNotIn('默认地址', rows[1])

    def test_unavailable_checkout_shows_current_book_without_old_selected_badge(self):
        checkout = snapshot('checkout', 'CART')
        checkout.update(status='unavailable', items=[], selected_address_id=None, selection_status='unknown')
        result = service.render({'address_snapshots': [checkout, snapshot()]}, 'html', 0)
        self.assertEqual(len(Rows(result['address_content']).rows), 2)
        self.assertNotIn('本次已选中', result['address_content'])
        self.assertIn('本次收货地址尚未核实', result['address_content'])
        self.assertEqual(result['address_status'], 'unavailable')

    def test_multiple_checkout_scenes_do_not_choose_an_arbitrary_selection(self):
        data = [snapshot(), snapshot('checkout', 'CART'), snapshot('checkout', 'BUY_NOW')]
        content = service.render({'address_snapshots': data}, 'html', 0)['address_content']
        self.assertEqual(len(Rows(content).rows), 2)
        self.assertNotIn('本次已选中', content)
        self.assertIn('请明确本次结算', content)

    def test_expired_checkout_keeps_only_safe_context_and_shows_pending_selection(self):
        checkout = snapshot('checkout', 'CART'); checkout['authorization_expires_at'] = 1
        content = service.render({'address_snapshots':[snapshot(), checkout]}, 'widget', 0)['address_content']
        self.assertEqual(len(Rows(content).rows), 2)
        self.assertIn('本次收货地址尚未核实', content)
        self.assertNotIn('本次已选中', content)

    def test_checkout_is_rendered_as_a_complete_snapshot_not_joined_to_book_rows(self):
        checkout = snapshot('checkout', 'CART'); checkout['items'] = checkout['items'][1:]
        content = address_cards.render([snapshot(), checkout], 'widget')[1]
        self.assertEqual(len(Rows(content).rows), 1)
        self.assertNotIn('默认地址', content)
        self.assertIn('本次已选中', content)

    def test_mismatched_authorization_snapshots_cannot_be_combined(self):
        checkout = snapshot('checkout', 'CART'); checkout['authorization_binding'] = 'b2'*32
        content = address_cards.render([snapshot(), checkout], 'widget')[1]
        self.assertEqual(len(Rows(content).rows), 0)
        self.assertNotIn('本次已选中', content)

    def test_render_is_read_only_and_no_buttons_scripts_or_private_fields(self):
        data = [snapshot(), snapshot('checkout', 'CART')]; original = copy.deepcopy(data)
        content = address_cards.render(data, 'html')[1]
        self.assertEqual(data, original)
        for token in ('<script', '<button', '<input', 'authorization_binding', 'address_id', '13812341234'):
            self.assertNotIn(token, content)

    def test_new_cards_share_theme_without_replacing_main_cart_renderer(self):
        product = cards.render_widget([{'title':'示例商品', 'rank':1}], {}, 'auto')
        cart = service.render_cart({'status':'current', 'items':[]}, 'widget')[1]
        address = address_cards.render([snapshot()], 'widget')[1]
        for fragment in (product, address):
            self.assertIn('--commerce-card-radius', fragment)
        # main moved cart/checkout/after-sale to commerce_render. Preserve that
        # renderer rather than restoring the removed cart implementation.
        for fragment in (product, cart, address):
            self.assertIn('prefers-color-scheme:dark', fragment)
        self.assertIn('class="fm-commerce"', cart)
        self.assertIn('commerce-page', address_cards.render([snapshot()], 'html')[1])
        cart_page = service.render_cart({'status':'current','items':[]}, 'html')[1]
        self.assertTrue(cart_page.startswith('<!doctype html>'))
        self.assertEqual(cart_page.count('<html'), 1)


if __name__ == '__main__': unittest.main()
