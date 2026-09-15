from odoo import Command
from odoo.tests import tagged
from odoo.exceptions import UserError, ValidationError
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.leyka_cfdi_purchase.tests.test_cfdi_parser import CFDI


@tagged('post_install', '-at_install')
class TestPurchaseStock(AccountTestInvoicingCommon):
    def setUp(self):
        super().setUp()
        self.env.user.group_ids |= self.env.ref('leyka_local_core.group_leyka_manager')
        self.env.company.with_context(no_vat_validation=True).vat = 'XAXX010101000'
        self.env['res.partner'].with_context(no_vat_validation=True).create({
            'name': 'Proveedor XML', 'vat': 'AAA010101AAA', 'supplier_rank': 1})
        self.env['account.tax'].create({'name': 'IVA compras prueba 16', 'amount': 16,
            'amount_type': 'percent', 'type_tax_use': 'purchase', 'company_id': self.env.company.id})
        self.product = self.env['product.product'].create({'name': 'Cadena XML',
            'type': 'consu', 'is_storable': True, 'purchase_ok': True,
            'property_account_expense_id': self.company_data['default_account_expense'].id})
        xml = CFDI.replace(b'Moneda="MXN"', ('Moneda="%s"' % self.env.company.currency_id.name).encode())
        self.cfdi = self.env['leyka.cfdi.purchase'].import_xml_payload(xml, 'compra.xml')
        self.cfdi.classification = 'merchandise'
        self.cfdi.line_ids.product_id = self.product
        self.cfdi.action_approve()

    def test_receipt_and_invoice_are_linked_without_duplicates(self):
        self.cfdi.action_create_purchase()
        purchase = self.cfdi.purchase_order_id
        self.cfdi.action_create_purchase()
        self.assertEqual(self.cfdi.purchase_order_id, purchase)
        self.assertFalse(purchase.picking_ids)
        purchase.button_confirm()
        self.assertEqual(len(purchase.picking_ids), 1)
        picking = purchase.picking_ids
        self.assertNotEqual(picking.state, 'done')
        self.cfdi.action_create_vendor_bill()
        bill = self.cfdi.vendor_bill_id
        self.assertEqual(bill.state, 'draft')
        self.assertEqual(bill.invoice_line_ids.purchase_line_id, purchase.order_line)
        self.assertEqual(bill.amount_total, 116)
        purchase.action_create_invoice()
        self.assertEqual(len(purchase.invoice_ids), 1)
        picking.move_ids.write({'quantity': 1, 'picked': True})
        picking._action_done()
        self.assertEqual(purchase.order_line.qty_received, 1)

    def test_missing_product_blocks_purchase(self):
        self.cfdi.line_ids.product_id = False
        with self.assertRaises(ValidationError):
            self.cfdi.action_create_purchase()
        self.assertFalse(self.cfdi.purchase_order_id)

    def test_invoice_waits_for_confirmed_purchase(self):
        with self.assertRaises(UserError):
            self.cfdi.action_create_vendor_bill()
        self.assertFalse(self.cfdi.vendor_bill_id)

    def test_changed_purchase_total_blocks_invoice(self):
        self.cfdi.action_create_purchase()
        purchase = self.cfdi.purchase_order_id
        purchase.button_confirm()
        purchase.order_line.price_unit = 120
        with self.assertRaises(ValidationError):
            self.cfdi.action_create_vendor_bill()
        self.assertFalse(self.cfdi.vendor_bill_id)

    def test_partial_receipt_keeps_remaining_quantity(self):
        self.cfdi.line_ids.write({'quantity': 2, 'unit_price': 50})
        self.cfdi.action_create_purchase()
        purchase = self.cfdi.purchase_order_id
        purchase.button_confirm()
        picking = purchase.picking_ids
        picking.move_ids.write({'quantity': 1, 'picked': True})
        picking._action_done()
        self.assertEqual(purchase.order_line.qty_received, 1)
        backorder = purchase.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel'))
        self.assertEqual(len(backorder), 1)
        self.assertEqual(sum(backorder.move_ids.mapped('product_uom_qty')), 1)
