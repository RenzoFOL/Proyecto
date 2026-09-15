import secrets
import string

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare


_CODE_ALPHABET = string.ascii_uppercase + string.digits


class LeykaStoreCredit(models.Model):
    _name = "leyka.store.credit"
    _description = "Vale de tienda Leyka"
    _order = "create_date desc, id desc"
    _rec_name = "code"

    code = fields.Char(required=True, copy=False, readonly=True, index=True)
    holder_id = fields.Many2one(
        "leyka.voucher.holder",
        required=True,
        ondelete="restrict",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    amount_initial = fields.Monetary(required=True, readonly=True)
    balance = fields.Monetary(required=True, readonly=True, copy=False)
    active = fields.Boolean(default=True, copy=False)
    state = fields.Selection(
        [
            ("active", "Activo"),
            ("used", "Consumido"),
            ("cancelled", "Cancelado"),
            ("expired", "Vencido"),
        ],
        compute="_compute_state",
        string="Estado",
    )
    expiration_date = fields.Date(
        string="Vencimiento",
        help="Vacío significa que el vale no caduca.",
    )
    origin_order_id = fields.Many2one(
        "pos.order",
        string="Orden POS de origen",
        ondelete="set null",
        index=True,
    )
    origin_reference = fields.Char(index=True)
    note = fields.Text()
    transaction_ids = fields.One2many(
        "leyka.store.credit.transaction",
        "credit_id",
        string="Movimientos",
        readonly=True,
    )
    replaced_by_id = fields.Many2one(
        "leyka.store.credit",
        string="Reemplazado por",
        readonly=True,
        copy=False,
    )
    replaces_id = fields.Many2one(
        "leyka.store.credit",
        string="Reemplaza a",
        readonly=True,
        copy=False,
    )

    _code_uniq = models.Constraint("unique(code)", "El código del vale ya existe.")
    _initial_positive = models.Constraint(
        "CHECK(amount_initial > 0)", "El importe inicial debe ser mayor que cero."
    )
    _balance_nonnegative = models.Constraint(
        "CHECK(balance >= 0)", "El saldo del vale no puede ser negativo."
    )

    @api.depends("active", "balance", "expiration_date")
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for credit in self:
            if not credit.active:
                credit.state = "cancelled"
            elif credit.expiration_date and credit.expiration_date < today:
                credit.state = "expired"
            elif credit.currency_id.is_zero(credit.balance):
                credit.state = "used"
            else:
                credit.state = "active"

    @api.model
    def _new_code(self):
        return "LK-" + "-".join(
            "".join(secrets.choice(_CODE_ALPHABET) for _unused in range(4))
            for _group in range(3)
        )

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for incoming in vals_list:
            vals = dict(incoming)
            vals.setdefault("code", self._new_code())
            vals.setdefault("balance", vals.get("amount_initial", 0.0))
            prepared.append(vals)
        credits = super().create(prepared)
        transaction_model = self.env["leyka.store.credit.transaction"].sudo()
        for credit in credits:
            transaction_model.create(
                {
                    "credit_id": credit.id,
                    "operation": "issue",
                    "amount": credit.amount_initial,
                    "balance_after": credit.balance,
                    "note": _("Emisión inicial"),
                    "user_id": self.env.user.id,
                }
            )
        return credits

    def _lock_and_read_balance(self):
        self.ensure_one()
        self.flush_recordset(["balance", "active"])
        self.env.cr.execute(
            "SELECT balance, active FROM leyka_store_credit WHERE id = %s FOR UPDATE",
            [self.id],
        )
        row = self.env.cr.fetchone()
        if not row:
            raise UserError(_("El vale ya no existe."))
        return float(row[0]), bool(row[1])

    def _assert_usable(self, active):
        self.ensure_one()
        if not active:
            raise UserError(_("El vale está cancelado."))
        if self.expiration_date and self.expiration_date < fields.Date.context_today(self):
            raise UserError(_("El vale está vencido."))

    def apply_movement(self, amount, operation, pos_order=None, note=None):
        self.ensure_one()
        self.check_access("write")
        if operation not in {"redeem", "adjustment", "refund_to_credit"}:
            raise ValidationError(_("Tipo de movimiento no permitido."))
        current_balance, active = self._lock_and_read_balance()
        self._assert_usable(active)
        new_balance = self.currency_id.round(current_balance + amount)
        if float_compare(
            new_balance,
            0.0,
            precision_rounding=self.currency_id.rounding,
        ) < 0:
            available = "%s %.2f" % (self.currency_id.symbol or "", current_balance)
            raise UserError(_("Saldo insuficiente. Disponible: %s") % available)
        self.write({"balance": new_balance})
        return self.env["leyka.store.credit.transaction"].sudo().create(
            {
                "credit_id": self.id,
                "operation": operation,
                "amount": amount,
                "balance_after": new_balance,
                "pos_order_id": pos_order.id if pos_order else False,
                "note": note,
                "user_id": self.env.user.id,
            }
        )

    def redeem(self, amount, pos_order=None, note=None):
        if amount <= 0:
            raise ValidationError(_("El importe a usar debe ser mayor que cero."))
        return self.apply_movement(
            -amount,
            "redeem",
            pos_order=pos_order,
            note=note,
        )

    def action_cancel(self):
        if not self.env.user.has_group("leyka_local_core.group_leyka_manager"):
            raise AccessError(_("Solo un responsable puede cancelar vales."))
        for credit in self:
            current_balance, active = credit._lock_and_read_balance()
            if not active:
                continue
            credit.write({"active": False, "balance": 0.0})
            self.env["leyka.store.credit.transaction"].sudo().create(
                {
                    "credit_id": credit.id,
                    "operation": "cancel",
                    "amount": -current_balance,
                    "balance_after": 0.0,
                    "note": _("Cancelación autorizada"),
                    "user_id": self.env.user.id,
                }
            )

    def action_reissue(self):
        self.ensure_one()
        if not self.env.user.has_group("leyka_local_core.group_leyka_manager"):
            raise AccessError(_("Solo un responsable puede reponer vales."))
        current_balance, active = self._lock_and_read_balance()
        self._assert_usable(active)
        if self.currency_id.is_zero(current_balance):
            raise UserError(_("No se puede reponer un vale sin saldo."))
        replacement = self.create(
            {
                "holder_id": self.holder_id.id,
                "company_id": self.company_id.id,
                "amount_initial": current_balance,
                "balance": current_balance,
                "origin_order_id": self.origin_order_id.id,
                "origin_reference": self.origin_reference,
                "replaces_id": self.id,
                "note": _("Reposición del vale perdido %s") % self.code,
            }
        )
        self.write({"active": False, "balance": 0.0, "replaced_by_id": replacement.id})
        self.env["leyka.store.credit.transaction"].sudo().create(
            {
                "credit_id": self.id,
                "operation": "reissue",
                "amount": -current_balance,
                "balance_after": 0.0,
                "note": _("Saldo transferido a %s") % replacement.code,
                "user_id": self.env.user.id,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "leyka.store.credit",
            "res_id": replacement.id,
            "view_mode": "form",
            "target": "current",
        }


class LeykaStoreCreditTransaction(models.Model):
    _name = "leyka.store.credit.transaction"
    _description = "Movimiento de vale Leyka"
    _order = "create_date desc, id desc"
    _rec_name = "credit_id"

    credit_id = fields.Many2one(
        "leyka.store.credit",
        required=True,
        ondelete="restrict",
        index=True,
    )
    operation = fields.Selection(
        [
            ("issue", "Emisión"),
            ("redeem", "Uso"),
            ("refund_to_credit", "Devolución a vale"),
            ("adjustment", "Ajuste"),
            ("cancel", "Cancelación"),
            ("reissue", "Reposición"),
        ],
        required=True,
        index=True,
    )
    amount = fields.Monetary(
        required=True,
        help="Positivo aumenta el saldo; negativo lo reduce.",
    )
    balance_after = fields.Monetary(required=True)
    currency_id = fields.Many2one(
        related="credit_id.currency_id",
        store=True,
        readonly=True,
    )
    holder_id = fields.Many2one(
        related="credit_id.holder_id",
        store=True,
        readonly=True,
    )
    pos_order_id = fields.Many2one("pos.order", ondelete="set null", index=True)
    user_id = fields.Many2one("res.users", required=True, readonly=True)
    note = fields.Char()
