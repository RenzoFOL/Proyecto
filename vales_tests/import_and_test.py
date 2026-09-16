"""Run via odoo-bin shell. Import through the exact ZIP importer, not addons_path."""
import io
import os
import unittest
import zipfile
from pathlib import Path
from odoo.tests import tagged
from odoo.addons.point_of_sale.tests.common import TestPoSCommon
from odoo.exceptions import UserError, ValidationError

root = Path(os.environ['GITHUB_WORKSPACE'])
archive = root / 'dist/leyka_pos_vales_Odoo19.zip'
result = env['ir.module.module']._import_zipfile(io.BytesIO(archive.read_bytes()))
assert 'leyka_pos_vales' in result[1], result
env.cr.commit()
# Reimport exercises updates of fields, assets and actions using the same UI mechanism.
env['ir.module.module']._import_zipfile(io.BytesIO(archive.read_bytes()))
env.cr.commit()
assert env['ir.module.module'].search([('name', '=', 'leyka_pos_vales')]).imported
assert not env['ir.module.module'].search_count([('name', '=', 'account_accountant'), ('state', '=', 'installed')])
assert env['ir.asset'].search_count([('path', 'like', '/leyka_pos_vales/%')]) == 3


@tagged('post_install', '-at_install')
class TestImportableVales(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.program = self.env.ref('leyka_pos_vales.program_vales')
        self.program.company_id = self.company
        self.credit = self.env.ref('leyka_pos_vales.product_vale')
        self.product = self.env['product.product'].create({
            'name': 'Pieza de prueba', 'list_price': 100, 'type': 'consu',
            'is_storable': True, 'available_in_pos': True, 'taxes_id': [(5, 0, 0)],
        })
        self.env['stock.quant']._update_available_quantity(self.product, self.config.picking_type_id.default_location_src_id, 10)
        self.open_new_session()

    def sync(self, data):
        self.env['pos.order'].sync_from_ui([data])
        return self.env['pos.order'].search([('uuid', '=', data['uuid'])], limit=1)

    def original(self, qty=2):
        return self.sync(self.create_ui_order_data([(self.product, qty)]))

    def returned(self, original=None, qty=1, **overrides):
        original = original or self.original()
        amount = 100 * qty
        meta = {
            'is_refund': False, 'x_leyka_vale_holder': 'Persona de prueba',
            'x_leyka_vale_phone': '2225238163', 'x_leyka_vale_reason': 'Pieza sin instalar, devolución aprobada',
            'x_leyka_vale_reviewed': True, 'x_leyka_vale_pending': True,
            'x_leyka_vale_code': 'LK-' + self.env['loyalty.card']._generate_code().replace('044', '', 1).replace('-', '').upper().ljust(20, 'A')[:20],
        }
        meta.update(overrides)
        data = self.create_ui_order_data([
            {'product': self.product, 'quantity': -qty, 'refunded_orderline_id': original.lines.id},
            {'product': self.credit, 'quantity': 1, 'price_unit': amount},
        ], pos_order_ui_args=meta, payments=[])
        return self.sync(data)

    def issue(self, order):
        amount = sum(order.lines.filtered(lambda l: l.product_id == self.credit).mapped('price_subtotal_incl'))
        return order.confirm_coupon_programs({'-1': {
            'program_id': self.program.id, 'points': amount, 'points_earned': amount, 'points_spent': 0,
            'code': order.x_leyka_vale_code, 'expiration_date': False,
        }})

    def card(self, order):
        return self.env['loyalty.card'].search([('source_pos_order_id', '=', order.id), ('program_id', '=', self.program.id)])

    def test_import_and_issue_partial_return(self):
        source = self.original(2)
        order = self.returned(source)
        self.assertEqual(order.amount_total, 0)
        self.assertFalse(order.payment_ids)
        self.issue(order)
        card = self.card(order)
        self.assertEqual(len(card), 1)
        self.assertEqual(card.points, 100)
        self.assertFalse(card.expiration_date)
        self.assertEqual(card.x_leyka_vale_phone, '2225238163')
        self.assertEqual(card.x_leyka_vale_holder, 'Persona de prueba')
        self.assertFalse(card.partner_id)
        self.assertEqual(source.lines.refunded_qty, 1)
        self.assertEqual(self.env['stock.quant']._get_available_quantity(self.product, self.config.picking_type_id.default_location_src_id), 9)

    def test_repeat_confirmation_is_idempotent(self):
        order = self.returned()
        self.issue(order)
        self.issue(order)
        self.assertEqual(len(self.card(order)), 1)
        self.assertEqual(self.card(order).points, 100)

    def test_holder_review_and_phone_required(self):
        for values in [{'x_leyka_vale_holder': ''}, {'x_leyka_vale_phone': '123'}, {'x_leyka_vale_reviewed': False}]:
            with self.assertRaises((UserError, ValidationError)), self.env.cr.savepoint():
                self.returned(**values)

    def test_cannot_return_twice(self):
        source = self.original(1)
        self.returned(source)
        with self.assertRaises((UserError, ValidationError)), self.env.cr.savepoint():
            self.returned(source)

    def test_partial_redemption_and_no_overdraft(self):
        order = self.returned()
        self.issue(order)
        card = self.card(order)
        sale = self.original(1)
        sale.confirm_coupon_programs({str(card.id): {
            'program_id': self.program.id, 'points': -40, 'points_earned': 0, 'points_spent': 40,
        }})
        self.assertEqual(card.points, 60)
        with self.assertRaises((UserError, ValidationError)), self.env.cr.savepoint():
            other = self.original(1)
            other.confirm_coupon_programs({str(card.id): {'program_id': self.program.id, 'points': -61}})
        self.assertEqual(card.points, 60)

    def test_no_orphan_card(self):
        with self.assertRaises((UserError, ValidationError)), self.env.cr.savepoint():
            self.env['loyalty.card'].create({'program_id': self.program.id, 'points': 100})

    def test_no_expiration(self):
        order = self.returned()
        self.issue(order)
        with self.assertRaises((UserError, ValidationError)), self.env.cr.savepoint():
            self.card(order).expiration_date = '2099-12-31'

    def test_cash_is_not_a_vale(self):
        source = self.original(1)
        data = self.create_ui_order_data([
            {'product': self.product, 'quantity': -1, 'refunded_orderline_id': source.lines.id},
        ], pos_order_ui_args={'x_leyka_vale_pending': True}, payments=[(self.cash_pm, -100)])
        with self.assertRaises((UserError, ValidationError)), self.env.cr.savepoint():
            self.sync(data)


suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestImportableVales)
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    raise RuntimeError('Importable vale tests failed')
print('LEYKA_IMPORTABLE_OK: ZIP imported twice; all business tests passed; no Enterprise Accounting.')
