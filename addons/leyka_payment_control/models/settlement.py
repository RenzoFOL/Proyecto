from datetime import datetime, time, timedelta
import pytz

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class Settlement(models.Model):
    _name = 'leyka.payment.settlement'
    _description = 'Liquidación de terminal Leyka'
    _order = 'settlement_date desc, id desc'

    name = fields.Char(string='Referencia de liquidación', required=True, index=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    payment_method_id = fields.Many2one('pos.payment.method', required=True, string='Método POS',
        domain="[('company_id', '=', company_id), ('leyka_store_credit_payment', '=', False)]")
    provider = fields.Selection([('mercado_pago', 'Mercado Pago'), ('stori', 'Stori Tap'),
        ('other', 'Otro proveedor')], default='other', required=True, string='Proveedor')
    date_from = fields.Date(required=True, default=fields.Date.today, string='Cobros desde')
    date_to = fields.Date(required=True, default=fields.Date.today, string='Cobros hasta')
    timezone = fields.Char(required=True, default=lambda self: self.env.user.tz or 'America/Mexico_City', string='Zona horaria')
    settlement_date = fields.Date(required=True, default=fields.Date.today, string='Fecha del depósito')
    payment_ids = fields.One2many('pos.payment', 'leyka_settlement_id', readonly=True, string='Cobros incluidos')
    payment_count = fields.Integer(compute='_compute_amounts')
    gross_amount = fields.Monetary(compute='_compute_amounts', string='Cobros netos de devoluciones')
    fee_base = fields.Monetary(string='Comisión sin impuestos')
    fee_tax = fields.Monetary(string='Impuestos de la comisión')
    fee_total = fields.Monetary(compute='_compute_amounts', string='Comisión total')
    other_adjustment = fields.Monetary(string='Otros ajustes al depósito',
        help='Positivo aumenta el depósito; negativo lo disminuye. Describe el motivo y su comprobante.')
    expected_net = fields.Monetary(compute='_compute_amounts', string='Depósito esperado')
    received_net = fields.Monetary(string='Depósito recibido')
    difference = fields.Monetary(compute='_compute_amounts', string='Diferencia')
    bank_line_id = fields.Many2one('account.bank.statement.line', string='Movimiento bancario existente',
        domain="[('company_id', '=', company_id)]", ondelete='restrict')
    fee_bill_id = fields.Many2one('account.move', string='Factura de comisión (referencia)',
        domain="[('company_id', '=', company_id), ('move_type', '=', 'in_invoice')]", ondelete='restrict')
    note = fields.Text(string='Observaciones / comprobantes')
    state = fields.Selection([('draft', 'Por revisar'), ('reviewed', 'Revisado')], default='draft', required=True, readonly=True)
    reviewed_by_id = fields.Many2one('res.users', readonly=True)
    reviewed_at = fields.Datetime(readonly=True)

    _reference_unique = models.Constraint('unique(company_id, payment_method_id, name)',
        'La referencia ya fue registrada para este método de pago.')
    _bank_line_unique = models.Constraint('unique(bank_line_id)', 'El depósito ya está vinculado a otra liquidación.')

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([dict(vals, state='draft', reviewed_by_id=False, reviewed_at=False) for vals in vals_list])

    @api.depends('payment_ids.amount', 'fee_base', 'fee_tax', 'other_adjustment', 'received_net')
    def _compute_amounts(self):
        for record in self:
            record.payment_count = len(record.payment_ids)
            record.gross_amount = sum(record.payment_ids.mapped('amount'))
            record.fee_total = record.fee_base + record.fee_tax
            record.expected_net = record.gross_amount - record.fee_total + record.other_adjustment
            record.difference = record.received_net - record.expected_net

    @api.constrains('fee_base', 'fee_tax', 'date_from', 'date_to', 'payment_method_id', 'company_id')
    def _check_settings(self):
        for record in self:
            if record.fee_base < 0 or record.fee_tax < 0 or record.date_from > record.date_to:
                raise ValidationError(_('Revisa las fechas y las comisiones; las comisiones no pueden ser negativas.'))
            if record.payment_method_id.company_id != record.company_id or record.payment_method_id.leyka_store_credit_payment:
                raise ValidationError(_('Selecciona un método de pago de esta compañía distinto de vales.'))

    def _assert_draft(self):
        self.ensure_one()
        self.check_access('write')
        self.env.cr.execute('SELECT id FROM leyka_payment_settlement WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset(['state'])
        if self.state != 'draft':
            raise UserError(_('Reabre la revisión antes de modificar esta liquidación.'))

    def action_collect_payments(self):
        self._assert_draft()
        try:
            zone = pytz.timezone(self.timezone)
        except pytz.UnknownTimeZoneError as error:
            raise UserError(_('La zona horaria no es válida.')) from error
        def boundary(day):
            return zone.localize(datetime.combine(day, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        payments = self.env['pos.payment'].search([
            ('payment_method_id', '=', self.payment_method_id.id),
            ('pos_order_id.company_id', '=', self.company_id.id),
            ('pos_order_id.state', 'in', ['paid', 'done', 'invoiced']),
            ('payment_date', '>=', boundary(self.date_from)),
            ('payment_date', '<', boundary(self.date_to + timedelta(days=1))),
            ('leyka_settlement_id', '=', False),
        ])
        if payments:
            self.env.cr.execute('SELECT id FROM pos_payment WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(payments.ids)])
            payments.invalidate_recordset(['leyka_settlement_id'])
            if payments.filtered('leyka_settlement_id'):
                raise UserError(_('Otra revisión acaba de incluir uno de los cobros. Actualiza e inténtalo de nuevo.'))
            if any(p.currency_id != self.currency_id for p in payments):
                raise UserError(_('Esta liquidación requiere cobros en la moneda de la compañía.'))
            payments.write({'leyka_settlement_id': self.id})
        return True

    def action_clear_payments(self):
        self._assert_draft()
        self.payment_ids.write({'leyka_settlement_id': False})
        return True

    def action_review(self):
        self._assert_draft()
        if not self.payment_ids:
            raise UserError(_('Incluye los cobros del POS antes de revisar.'))
        if not self.currency_id.is_zero(self.difference):
            raise UserError(_('El depósito recibido no coincide. Corrige los importes o documenta el ajuste.'))
        if self.other_adjustment and not self.note:
            raise UserError(_('Explica el motivo de los otros ajustes.'))
        if self.bank_line_id and (
                self.bank_line_id.company_id != self.company_id
                or self.bank_line_id.journal_id.currency_id not in (self.env['res.currency'], self.currency_id)
                or not self.currency_id.is_zero(self.bank_line_id.amount - self.received_net)):
            raise UserError(_('El movimiento bancario no coincide en compañía, moneda o importe.'))
        if self.fee_bill_id and (self.fee_bill_id.company_id != self.company_id or self.fee_bill_id.move_type != 'in_invoice'):
            raise UserError(_('La factura de comisión debe ser una compra de esta compañía.'))
        super().write({'state': 'reviewed', 'reviewed_by_id': self.env.uid, 'reviewed_at': fields.Datetime.now()})
        return True

    def action_reopen(self):
        self.check_access('write')
        return super().write({'state': 'draft', 'reviewed_by_id': False, 'reviewed_at': False})

    def write(self, vals):
        if set(vals) & {'state', 'reviewed_by_id', 'reviewed_at'}:
            raise UserError(_('Usa los botones de revisión para cambiar el estado.'))
        self.check_access('write')
        if self.ids:
            self.env.cr.execute('SELECT id FROM leyka_payment_settlement WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(self.ids)])
            self.invalidate_recordset(['state'])
        if any(r.state == 'reviewed' for r in self):
            raise UserError(_('Reabre la liquidación antes de editarla.'))
        if set(vals) & {'payment_method_id', 'company_id', 'date_from', 'date_to', 'timezone'} and any(r.payment_ids for r in self):
            raise UserError(_('Libera los cobros antes de cambiar los filtros de la liquidación.'))
        return super().write(vals)

    def unlink(self):
        if any(r.state == 'reviewed' for r in self):
            raise UserError(_('No puedes borrar una revisión confirmada.'))
        return super().unlink()


class PosPayment(models.Model):
    _inherit = 'pos.payment'

    leyka_settlement_id = fields.Many2one('leyka.payment.settlement', copy=False, readonly=True, index=True, ondelete='set null')

    def write(self, vals):
        financial = {'amount', 'payment_method_id', 'pos_order_id', 'payment_date'}
        if set(vals) & financial and self.filtered('leyka_settlement_id'):
            for payment in self.filtered('leyka_settlement_id'):
                for key in set(vals) & financial:
                    current = payment[key].id if key.endswith('_id') else payment[key]
                    if current != vals[key]:
                        raise UserError(_('Libera el cobro de su liquidación antes de modificar sus importes o referencias.'))
        if 'leyka_settlement_id' in vals:
            if not self.env.user.has_group('account.group_account_manager'):
                raise AccessError(_('Se requieren permisos de responsable de Contabilidad para asignar liquidaciones.'))
            if self.mapped('leyka_settlement_id').filtered(lambda s: s.state == 'reviewed'):
                raise UserError(_('El cobro pertenece a una liquidación revisada.'))
            target = self.env['leyka.payment.settlement'].browse(vals['leyka_settlement_id']).exists() if vals['leyka_settlement_id'] else False
            if target:
                target.check_access('write')
                if any(p.leyka_settlement_id and p.leyka_settlement_id != target for p in self):
                    raise ValidationError(_('Libera primero los cobros incluidos en otra liquidación.'))
                if target.state != 'draft' or any(
                        p.company_id != target.company_id or p.payment_method_id != target.payment_method_id
                        or p.currency_id != target.currency_id or p.pos_order_id.state not in ('paid', 'done', 'invoiced')
                        for p in self):
                    raise ValidationError(_('Los cobros no corresponden a la liquidación.'))
        return super().write(vals)

    def unlink(self):
        if self.filtered('leyka_settlement_id'):
            raise UserError(_('Libera primero los cobros de su liquidación.'))
        return super().unlink()
