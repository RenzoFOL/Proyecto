from odoo import fields
from odoo.tests import tagged
from odoo.addons.leyka_store_credit_account.tests.test_integration import TestCreditAccounting as AccountingFixture


@tagged('post_install', '-at_install')
class TestLocalSummary(AccountingFixture):
    def test_summary_excludes_voucher_product_and_matches_liability(self):
        self._make_exchange()
        self._close()
        today = fields.Date.today()
        summary = self.env['leyka.local.summary'].create({
            'date_from': today, 'date_to': today, 'timezone': 'UTC'})
        summary.action_calculate()
        self.assertEqual(summary.gross_sales, 100)
        self.assertEqual(summary.returns, 100)
        self.assertEqual(summary.net_sales, 0)
        self.assertEqual(summary.credit_outstanding, 100)
        self.assertEqual(summary.credit_ledger, 100)
        self.assertEqual(summary.credit_difference, 0)
        self.assertEqual(len(summary.order_ids), 2)

    def test_mexico_day_uses_utc_boundaries(self):
        summary = self.env['leyka.local.summary'].create({
            'date_from': '2026-09-15', 'date_to': '2026-09-15', 'timezone': 'America/Mexico_City'})
        start, end = summary._period_utc()
        self.assertEqual(str(start), '2026-09-15 06:00:00')
        self.assertEqual(str(end), '2026-09-16 06:00:00')

    def test_native_refund_is_negative_in_summary(self):
        original = self._sync_order(self.create_ui_order_data([(self.product, 1)]))
        refund = self.create_ui_order_data([{
            'product': self.product, 'quantity': -1, 'refunded_orderline_id': original.lines.id}],
            pos_order_ui_args={'is_refund': True}, payments=[(self.cash_payment_method, -100)])
        self._sync_order(refund)
        summary = self.env['leyka.local.summary'].create({
            'date_from': fields.Date.today(), 'date_to': fields.Date.today(), 'timezone': 'UTC'})
        summary.action_calculate()
        self.assertEqual(summary.gross_sales, 100)
        self.assertEqual(summary.returns, 100)
        self.assertEqual(summary.net_sales, 0)
