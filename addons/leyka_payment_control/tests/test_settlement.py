from odoo import fields
from odoo.tests import tagged
from odoo.exceptions import UserError
from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged('post_install', '-at_install')
class TestSettlement(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.open_new_session()
        self.product = self.env['product.product'].create({
            'name': 'Venta terminal', 'type': 'service', 'list_price': 100,
            'available_in_pos': True, 'taxes_id': [(5, 0, 0)]})
        data = self.create_ui_order_data([(self.product, 1)], payments=[(self.bank_pm1, 100)])
        self.env['pos.order'].sync_from_ui([data])
        self.order = self.env['pos.order'].search([('uuid', '=', data['uuid'])])
        self.settlement = self.env['leyka.payment.settlement'].create({
            'name': 'STORI-001', 'provider': 'stori', 'payment_method_id': self.bank_pm1.id,
            'date_from': fields.Date.today(), 'date_to': fields.Date.today(), 'timezone': 'UTC',
            'fee_base': 4, 'fee_tax': 1, 'received_net': 95})

    def test_collect_once_and_review(self):
        self.settlement.action_collect_payments()
        self.settlement.action_collect_payments()
        self.assertEqual(self.settlement.payment_count, 1)
        self.assertEqual(self.settlement.expected_net, 95)
        self.settlement.action_review()
        self.assertEqual(self.settlement.state, 'reviewed')
        with self.assertRaises(UserError):
            self.settlement.received_net = 90
        with self.assertRaises(UserError):
            self.order.payment_ids.amount = 90

    def test_second_settlement_cannot_count_same_payment(self):
        self.settlement.action_collect_payments()
        second = self.env['leyka.payment.settlement'].create({
            'name': 'STORI-002', 'payment_method_id': self.bank_pm1.id,
            'date_from': fields.Date.today(), 'date_to': fields.Date.today(), 'timezone': 'UTC'})
        second.action_collect_payments()
        self.assertEqual(second.payment_count, 0)
        self.assertEqual(self.order.payment_ids.leyka_settlement_id, self.settlement)

    def test_difference_prevents_review_and_reopen_allows_correction(self):
        self.settlement.action_collect_payments()
        self.settlement.received_net = 90
        with self.assertRaises(UserError):
            self.settlement.action_review()
        self.settlement.received_net = 95
        self.settlement.action_review()
        self.settlement.action_reopen()
        self.settlement.action_clear_payments()
        self.assertFalse(self.order.payment_ids.leyka_settlement_id)
