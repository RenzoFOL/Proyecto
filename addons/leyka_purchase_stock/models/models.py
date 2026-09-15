from odoo import Command, fields, models, _
from odoo.exceptions import UserError, ValidationError


class CfdiPurchase(models.Model):
    _inherit = 'leyka.cfdi.purchase'

    purchase_order_id = fields.Many2one('purchase.order', readonly=True, copy=False)
    receipt_ids = fields.Many2many('stock.picking', compute='_compute_receipts', string='Recepciones')
    credit_effect = fields.Selection([
        ('price', 'Descuento o ajuste de precio'),
        ('return', 'Devolución física al proveedor'),
    ], string='Motivo de la nota de crédito')
    original_cfdi_id = fields.Many2one('leyka.cfdi.purchase', string='CFDI original',
        domain="[('document_type', '=', 'I'), ('company_id', '=', company_id)]")

    def _compute_receipts(self):
        for record in self:
            record.receipt_ids = record.purchase_order_id.picking_ids

    def action_create_purchase(self):
        self.ensure_one()
        self.check_access('write')
        with self.env.cr.savepoint():
            self.env.cr.execute('SELECT id FROM leyka_cfdi_purchase WHERE id = %s FOR UPDATE', [self.id])
            self.invalidate_recordset(['purchase_order_id', 'vendor_bill_id', 'state'])
            if self.purchase_order_id:
                return self._open_purchase()
            if self.state != 'approved' or self.document_type != 'I':
                raise UserError(_('Aprueba un CFDI de ingreso antes de crear la compra.'))
            if self.vendor_bill_id:
                raise UserError(_('Ya hay una factura vinculada. Relaciona la compra existente desde Contabilidad para evitar duplicarla.'))
            commands = []
            for line in self.line_ids:
                product = line.product_id
                if not product or product.company_id not in (self.env['res.company'], self.company_id):
                    raise ValidationError(_('Asigna un producto válido de esta compañía a cada concepto.'))
                if line.quantity <= 0 or line.unit_price < 0:
                    raise ValidationError(_('Revisa las cantidades y precios del XML.'))
                if self.classification == 'merchandise' and not product.is_storable:
                    raise ValidationError(_('Para mercancía, activa el seguimiento de inventario del producto %s.') % product.display_name)
                tax = self.env['account.tax'].search([
                    ('company_id', '=', self.company_id.id), ('type_tax_use', '=', 'purchase'),
                    ('amount_type', '=', 'percent'), ('amount', '=', line.tax_rate),
                    ('price_include', '=', False),
                ], limit=1)
                if line.tax_rate and not tax:
                    raise ValidationError(_('Falta configurar IVA de compra excluido del precio: %s%%.') % line.tax_rate)
                commands.append(Command.create({
                    'product_id': product.id, 'name': line.description,
                    'product_qty': line.quantity, 'product_uom_id': product.uom_id.id,
                    'price_unit': line.unit_price,
                    'discount': 100 * line.discount / line.line_subtotal if line.line_subtotal else 0,
                    'tax_ids': [Command.set(tax.ids)],
                    'date_planned': self.invoice_date,
                    'leyka_cfdi_line_id': line.id,
                }))
            purchase = self.env['purchase.order'].with_company(self.company_id).create({
                'partner_id': self._find_or_create_supplier().id,
                'company_id': self.company_id.id, 'currency_id': self.currency_id.id,
                'partner_ref': self.uuid, 'origin': self.display_reference,
                'order_line': commands, 'leyka_cfdi_id': self.id,
            })
            if not self.currency_id.is_zero(purchase.amount_total - self.total):
                raise ValidationError(_('La compra no coincide con el total XML. Revisa impuestos y descuentos.'))
            self.purchase_order_id = purchase
            return self._open_purchase()

    def _open_purchase(self):
        return {'type': 'ir.actions.act_window', 'res_model': 'purchase.order',
                'res_id': self.purchase_order_id.id, 'view_mode': 'form'}

    def action_open_receipts(self):
        self.ensure_one()
        purchase = self.original_cfdi_id.purchase_order_id if self.document_type == 'E' else self.purchase_order_id
        return {'type': 'ir.actions.act_window', 'res_model': 'stock.picking',
                'view_mode': 'list,form', 'domain': [('id', 'in', purchase.picking_ids.ids)]}

    def _create_checked_vendor_bill(self):
        if self.classification == 'merchandise' and self.document_type == 'I':
            if not self.purchase_order_id or self.purchase_order_id.state not in ('purchase', 'done'):
                raise UserError(_('Crea y confirma primero la orden de compra para vincular factura y recepción.'))
        if self.document_type == 'E' and not self.credit_effect:
            raise UserError(_('Indica si la nota de crédito es un ajuste de precio o una devolución física.'))
        if self.original_cfdi_id and (
            self.original_cfdi_id.company_id != self.company_id
            or self.original_cfdi_id.issuer_rfc != self.issuer_rfc
            or self.original_cfdi_id.document_type != 'I'
        ):
            raise ValidationError(_('El CFDI original debe pertenecer al mismo proveedor y compañía.'))
        return super()._create_checked_vendor_bill()

    def _prepare_leyka_bill_line(self, line, product, tax, discount_percent):
        vals = super()._prepare_leyka_bill_line(line, product, tax, discount_percent)
        if self.purchase_order_id:
            purchase_line = self.purchase_order_id.order_line.filtered(lambda p: p.leyka_cfdi_line_id == line)
            if len(purchase_line) != 1 or purchase_line.product_id != product:
                raise ValidationError(_('El producto del XML cambió después de crear la compra. Revisa la vinculación.'))
            vals['purchase_line_id'] = purchase_line.id
            vals['product_uom_id'] = purchase_line.product_uom_id.id
        return vals


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    leyka_cfdi_id = fields.Many2one('leyka.cfdi.purchase', readonly=True, copy=False)
    _leyka_cfdi_uniq = models.Constraint('unique(leyka_cfdi_id)', 'El XML ya tiene una orden de compra.')

    def action_create_invoice(self, attachment_ids=False):
        if self.filtered('leyka_cfdi_id'):
            self.ensure_one()
            cfdi = self.leyka_cfdi_id
            if cfdi.vendor_bill_id:
                return {'type': 'ir.actions.act_window', 'res_model': 'account.move',
                        'res_id': cfdi.vendor_bill_id.id, 'view_mode': 'form'}
            return cfdi.action_create_vendor_bill()
        return super().action_create_invoice(attachment_ids=attachment_ids)


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    leyka_cfdi_line_id = fields.Many2one('leyka.cfdi.purchase.line', readonly=True, copy=False)
