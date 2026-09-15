from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class Company(models.Model):
    _inherit = 'res.company'

    leyka_credit_liability_id = fields.Many2one('account.account', string='Pasivo de vales Leyka',
        domain="[('account_type', '=', 'liability_current'), ('company_ids', 'in', id)]")
    leyka_credit_adjustment_journal_id = fields.Many2one('account.journal', string='Diario de ajustes de vales',
        domain="[('type', '=', 'general'), ('company_id', '=', id)]")
    leyka_credit_adjustment_account_id = fields.Many2one('account.account', string='Contrapartida de ajustes de vales',
        domain="[('company_ids', 'in', id)]")

    @api.constrains('leyka_credit_liability_id')
    def _check_credit_account(self):
        for company in self:
            account = company.leyka_credit_liability_id
            if account and (account.account_type != 'liability_current' or company not in account.company_ids):
                raise ValidationError(_('Selecciona una cuenta de pasivo circulante de esta compañía.'))

    def _leyka_credit_account(self):
        self.ensure_one()
        if not self.leyka_credit_liability_id:
            raise UserError(_('Configura la cuenta de pasivo de vales en la compañía antes de contabilizar.'))
        return self.leyka_credit_liability_id


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    def _prepare_base_line_for_taxes_computation(self):
        result = super()._prepare_base_line_for_taxes_computation()
        if self.product_id == self.order_id.config_id.leyka_credit_product_id:
            if self.tax_ids_after_fiscal_position:
                raise ValidationError(_('El producto técnico de vales debe estar sin impuestos.'))
            account = self.company_id.leyka_credit_liability_id
            if account:
                result['account_id'] = account
        return result


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def _get_invoice_lines_values(self, line_values, pos_line, move_type):
        result = super()._get_invoice_lines_values(line_values, pos_line, move_type)
        if pos_line.product_id == pos_line.order_id.config_id.leyka_credit_product_id:
            result['account_id'] = pos_line.company_id._leyka_credit_account().id
        return result


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _create_account_move(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        for session in self:
            orders = session._get_closed_orders()
            if (orders.lines.filtered(lambda line: line.product_id == session.config_id.leyka_credit_product_id)
                    or orders.payment_ids.payment_method_id.filtered('leyka_store_credit_payment')):
                session.company_id._leyka_credit_account()
                methods = orders.payment_ids.payment_method_id.filtered('leyka_store_credit_payment')
                for method in methods:
                    if method.type != 'bank' or method.split_transactions or method.use_payment_terminal:
                        raise UserError(_('El método de vales debe usar un diario bancario, sin terminal y sin identificar cliente. El módulo contabiliza el canje contra el pasivo, sin crear depósito bancario.'))
        return super()._create_account_move(balancing_account, amount_to_balance, bank_payment_method_diffs)

    def _create_bank_payment_moves(self, data):
        # Keep Odoo's invoice-payment reconciliation, but route store credit
        # directly to the liability. Never create a bank payment for a voucher.
        credit_amounts = {}
        for method in list(data['combine_receivables_bank']):
            if method.leyka_store_credit_payment:
                if (data.get('bank_payment_method_diffs') or {}).get(method.id):
                    raise UserError(_('Los vales no admiten diferencias de cierre bancario.'))
                credit_amounts[method] = data['combine_receivables_bank'].pop(method)
        result = super()._create_bank_payment_moves(data)
        for method, amounts in credit_amounts.items():
            values = self._debit_amounts({
                'account_id': self.company_id._leyka_credit_account().id,
                'move_id': self.move_id.id,
                'name': _('Canje de vales Leyka: %s') % method.name,
            }, amounts['amount'], amounts['amount_converted'])
            data['MoveLine'].create(values)
        return result


class StoreCreditTransaction(models.Model):
    _inherit = 'leyka.store.credit.transaction'

    adjustment_move_id = fields.Many2one('account.move', readonly=True, copy=False,
                                        string='Asiento de ajuste manual')

    def action_prepare_adjustment(self):
        self.ensure_one()
        self.check_access('read')
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Se requieren permisos de responsable de contabilidad.'))
        self.env.cr.execute('SELECT id FROM leyka_store_credit_transaction WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset(['adjustment_move_id'])
        if not self.adjustment_move_id:
            if self.pos_order_id or self.return_request_id or self.operation == 'reissue' or (
                    self.operation == 'issue' and self.credit_id.replaces_id):
                raise UserError(_('Este movimiento se contabiliza por el POS o es una reposición sin cambio de saldo.'))
            if not self.amount:
                raise UserError(_('Este movimiento no cambia el saldo.'))
            company = self.credit_id.company_id
            account = company._leyka_credit_account()
            journal = company.leyka_credit_adjustment_journal_id
            offset = company.leyka_credit_adjustment_account_id
            if not journal or not offset:
                raise UserError(_('Configura el diario general y la contrapartida de ajustes de vales en la compañía.'))
            if journal.company_id != company or journal.type != 'general' or company not in offset.company_ids:
                raise UserError(_('El diario y la contrapartida deben pertenecer a esta compañía.'))
            if offset == account:
                raise UserError(_('La contrapartida debe ser distinta del pasivo de vales.'))
            amount = self.amount
            move = self.env['account.move'].with_company(company).create({
                'journal_id': journal.id, 'date': fields.Date.to_date(self.create_date),
                'ref': '%s / %s' % (self.credit_id.code, self.operation),
                'line_ids': [(0, 0, {'account_id': account.id,
                    'debit': max(-amount, 0), 'credit': max(amount, 0), 'name': self.credit_id.code}),
                    (0, 0, {'account_id': offset.id,
                    'debit': max(amount, 0), 'credit': max(-amount, 0), 'name': _('Revisar contrapartida de vale')})],
            })
            self.sudo().adjustment_move_id = move
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move',
                'res_id': self.adjustment_move_id.id, 'view_mode': 'form'}
