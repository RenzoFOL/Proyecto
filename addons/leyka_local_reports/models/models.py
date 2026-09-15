from datetime import datetime, time, timedelta
import pytz

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class LocalSummary(models.TransientModel):
    _name = 'leyka.local.summary'
    _description = 'Resumen operativo Leyka'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date(required=True, default=lambda self: fields.Date.today().replace(day=1), string='Desde')
    date_to = fields.Date(required=True, default=fields.Date.today, string='Hasta')
    timezone = fields.Char(required=True, default=lambda self: self.env.user.tz or 'America/Mexico_City', string='Zona horaria')
    computed_at = fields.Datetime(readonly=True, string='Calculado el')
    gross_sales = fields.Monetary(readonly=True, string='Ventas positivas con impuestos')
    returns = fields.Monetary(readonly=True, string='Devoluciones con impuestos')
    net_sales = fields.Monetary(readonly=True, string='Ventas netas sin impuestos')
    sales_taxes = fields.Monetary(readonly=True, string='Impuestos registrados en POS')
    cost = fields.Monetary(readonly=True, string='Costo registrado de mercancía vendida')
    gross_profit = fields.Monetary(readonly=True, string='Utilidad bruta antes de gastos')
    pending_cost_count = fields.Integer(readonly=True, string='Líneas con costo pendiente')
    zero_cost_count = fields.Integer(readonly=True, string='Líneas con costo cero: revisar')
    external_payments = fields.Monetary(readonly=True, string='Cobros netos por medios distintos de vale')
    credit_redeemed = fields.Monetary(readonly=True, string='Vales usados como pago')
    purchase_base = fields.Monetary(readonly=True, string='Compras facturadas sin impuestos')
    purchase_taxes = fields.Monetary(readonly=True, string='Impuestos en facturas de compra')
    credit_outstanding = fields.Monetary(readonly=True, string='Saldo operativo de vales al corte')
    credit_ledger = fields.Monetary(readonly=True, string='Pasivo de vales contabilizado al corte')
    credit_difference = fields.Monetary(readonly=True, string='Diferencia por conciliar')
    has_credit_account = fields.Boolean(readonly=True)
    pending_receipt_count = fields.Integer(readonly=True, string='Recepciones actualmente pendientes')
    unposted_bill_count = fields.Integer(readonly=True, string='Facturas de compra en borrador del periodo')
    open_session_count = fields.Integer(readonly=True, string='Sesiones con ventas sin cierre')
    order_ids = fields.Many2many('pos.order', readonly=True)
    bill_ids = fields.Many2many('account.move', readonly=True)

    @api.onchange("company_id", "date_from", "date_to", "timezone")
    def _clear_calculated(self):
        self.computed_at = False

    def _period_utc(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('La fecha inicial no puede ser posterior a la final.'))
        try:
            zone = pytz.timezone(self.timezone)
        except pytz.UnknownTimeZoneError as error:
            raise UserError(_('Usa una zona horaria válida, por ejemplo America/Mexico_City.')) from error
        def utc(day):
            return zone.localize(datetime.combine(day, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        return utc(self.date_from), utc(self.date_to + timedelta(days=1))

    def action_calculate(self):
        self.ensure_one()
        if self.company_id not in self.env.companies:
            raise UserError(_('Selecciona una compañía permitida.'))
        start, end = self._period_utc()
        orders = self.env['pos.order'].search([
            ('company_id', '=', self.company_id.id), ('state', 'in', ['paid', 'done', 'invoiced']),
            ('date_order', '>=', start), ('date_order', '<', end),
        ])
        values = dict.fromkeys(['gross_sales', 'returns', 'net_sales', 'sales_taxes', 'cost',
                               'gross_profit', 'pending_cost_count', 'zero_cost_count',
                               'external_payments', 'credit_redeemed', 'purchase_base', 'purchase_taxes'], 0)
        for order in orders:
            def convert(amount):
                return order.currency_id._convert(amount, self.currency_id, self.company_id, order.date_order)
            for line in order.lines:
                if line.product_id == order.config_id.leyka_credit_product_id or line.product_id.type == 'combo':
                    continue
                sign = -1 if order.is_refund else 1
                subtotal = convert(sign * line.price_subtotal)
                total = convert(sign * line.price_subtotal_incl)
                values['gross_sales'] += max(0, total)
                values['returns'] += max(0, -total)
                values['net_sales'] += subtotal
                values['sales_taxes'] += total - subtotal
                if line.is_total_cost_computed:
                    values['cost'] += convert(line.total_cost)
                    if line.product_id.is_storable and not line.total_cost:
                        values['zero_cost_count'] += 1
                else:
                    values['pending_cost_count'] += 1
            for payment in order.payment_ids:
                key = 'credit_redeemed' if payment.payment_method_id.leyka_store_credit_payment else 'external_payments'
                values[key] += convert(payment.amount)
        values['gross_profit'] = values['net_sales'] - values['cost'] if not values['pending_cost_count'] else 0
        bill_domain = [('company_id', '=', self.company_id.id), ('move_type', 'in', ['in_invoice', 'in_refund']),
                       ('invoice_date', '>=', self.date_from), ('invoice_date', '<=', self.date_to)]
        bills = self.env['account.move'].search(bill_domain + [('state', '=', 'posted')])
        for bill in bills:
            sign = -1 if bill.move_type == 'in_refund' else 1
            values['purchase_base'] += sign * abs(bill.amount_untaxed_signed)
            values['purchase_taxes'] += sign * abs(bill.amount_tax_signed)
        movements = self.env['leyka.store.credit.transaction'].search([
            ('credit_id.company_id', '=', self.company_id.id), ('create_date', '<', end)])
        outstanding = sum(movements.mapped('amount'))
        account = self.company_id.leyka_credit_liability_id
        ledger = 0
        if account:
            lines = self.env['account.move.line'].search([
                ('company_id', '=', self.company_id.id), ('account_id', '=', account.id),
                ('parent_state', '=', 'posted'), ('date', '<=', self.date_to)])
            ledger = -sum(lines.mapped('balance'))
        values.update({
            'credit_outstanding': outstanding, 'credit_ledger': ledger,
            'credit_difference': outstanding - ledger, 'has_credit_account': bool(account),
            'pending_receipt_count': self.env['stock.picking'].search_count([
                ('company_id', '=', self.company_id.id), ('picking_type_code', '=', 'incoming'),
                ('state', 'not in', ['done', 'cancel'])]),
            'unposted_bill_count': self.env['account.move'].search_count(bill_domain + [('state', '=', 'draft')]),
            'open_session_count': len(orders.session_id.filtered(lambda s: s.state != 'closed')),
            'order_ids': [(6, 0, orders.ids)], 'bill_ids': [(6, 0, bills.ids)],
            'computed_at': fields.Datetime.now(),
        })
        self.write(values)
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form'}

    def action_orders(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'pos.order', 'view_mode': 'list,form',
                'domain': [('id', 'in', self.order_ids.ids)]}

    def action_bills(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'view_mode': 'list,form',
                'domain': [('id', 'in', self.bill_ids.ids)]}
