import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class LeykaVoucherHolder(models.Model):
    _name = "leyka.voucher.holder"
    _description = "Titular simplificado de cambio o vale"
    _order = "name, id"
    _rec_name = "name"

    name = fields.Char(required=True, index=True)
    phone = fields.Char(required=True, index=True)
    phone_normalized = fields.Char(
        compute="_compute_phone_normalized",
        store=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Cliente formal vinculado",
        ondelete="set null",
        index=True,
    )
    note = fields.Text()
    active = fields.Boolean(default=True)
    credit_ids = fields.One2many(
        "leyka.store.credit",
        "holder_id",
        string="Vales",
    )
    total_balance = fields.Monetary(
        compute="_compute_total_balance",
        string="Saldo total",
        currency_field="currency_id",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        readonly=True,
    )

    @api.depends("phone")
    def _compute_phone_normalized(self):
        for holder in self:
            holder.phone_normalized = re.sub(r"\D", "", holder.phone or "")

    @api.depends("credit_ids.balance", "credit_ids.active")
    def _compute_total_balance(self):
        for holder in self:
            holder.total_balance = sum(
                holder.credit_ids.filtered("active").mapped("balance")
            )

    @api.constrains("name", "phone_normalized")
    def _check_identity(self):
        for holder in self:
            if not (holder.name or "").strip():
                raise ValidationError(_("El nombre del titular es obligatorio."))
            if len(holder.phone_normalized or "") < 8:
                raise ValidationError(
                    _("El teléfono debe contener por lo menos 8 dígitos.")
                )

    @api.model
    def name_search(self, name="", domain=None, operator="ilike", limit=100):
        domain = list(domain or [])
        if name:
            digits = re.sub(r"\D", "", name)
            search_domain = ["|", ("name", operator, name), ("phone", operator, name)]
            if digits:
                search_domain = [
                    "|",
                    "|",
                    ("name", operator, name),
                    ("phone", operator, name),
                    ("phone_normalized", operator, digits),
                ]
            domain = search_domain + domain
        records = self.search(domain, limit=limit)
        return [(record.id, record.display_name) for record in records]
