from odoo import Command
from odoo.tests import tagged
from odoo.exceptions import UserError
from odoo.addons.leyka_pos_exchange.tests.test_pos_exchange import TestLeykaPosExchange as ExchangeFixture


@tagged('post_install', '-at_install')
class TestCreditAccounting(ExchangeFixture):
    def setUp(self):
        super().setUp()
        self.liability = self.env['account.account'].create({
            'name': 'Vales pendientes prueba', 'code': '209901',
            'account_type': 'liability_current', 'company_ids': [Command.set(self.env.company.ids)]})
        self.env.company.leyka_credit_liability_id = self.liability

    def _close(self):
        cash = sum(self.pos_session.order_ids.payment_ids.filtered(
            lambda p: p.payment_method_id == self.cash_payment_method).mapped('amount'))
        self.pos_session.post_closing_cash_details(cash)
        self.pos_session.close_session_from_ui()
        self.assertEqual(self.pos_session.state, 'closed')

    def test_issue_and_partial_use_close_to_liability(self):
        order, payload, result = self._make_exchange()
        data = self.create_ui_order_data([(self.product, 1)],
            payments=[(self.bank_payment_method, 40), (self.cash_payment_method, 60)])
        data['payment_ids'][0][2]['leyka_credit_code'] = result['credit_code']
        self._sync_order(data)
        self._close()
        lines = self.pos_session.move_id.line_ids.filtered(lambda l: l.account_id == self.liability)
        self.assertEqual(sum(lines.mapped('balance')), -60)
        self.assertFalse(self.env['account.payment'].search([
            ('pos_session_id', '=', self.pos_session.id), ('pos_payment_method_id', '=', self.bank_payment_method.id)]))

    def test_invoiced_sale_redeems_credit_without_bank_deposit(self):
        order, payload, result = self._make_exchange()
        customer = self.env['res.partner'].create({'name': 'Cliente factura'})
        data = self.create_ui_order_data([(self.product, 1)], customer=customer, is_invoiced=True,
            payments=[(self.bank_payment_method, 100)])
        data['payment_ids'][0][2]['leyka_credit_code'] = result['credit_code']
        sale = self._sync_order(data)
        self._close()
        self.assertEqual(sale.account_move.amount_residual, 0)
        lines = self.env['account.move.line'].search([
            ('account_id', '=', self.liability.id), ('parent_state', '=', 'posted')])
        self.assertEqual(sum(lines.mapped('balance')), 0)
        self.assertFalse(self.env['account.payment'].search([
            ('pos_session_id', '=', self.pos_session.id), ('pos_payment_method_id', '=', self.bank_payment_method.id)]))

    def test_missing_liability_blocks_close(self):
        self._make_exchange()
        self.env.company.leyka_credit_liability_id = False
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.pos_session._create_account_move()
