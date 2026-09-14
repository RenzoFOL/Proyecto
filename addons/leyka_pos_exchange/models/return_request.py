from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare


class LeykaReturnRequest(models.Model):
    _name = "leyka.return.request"
    _description = "Solicitud de cambio o vale"
    _order = "create_date desc, id desc"
    _rec_name = "name"

    name = fields.Char(
        default=lambda self: _("Nuevo"),
        required=True,
        copy=False,
        readonly=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("validated", "Validado"),
            ("exchange", "Cambio preparado"),
            ("credit", "Vale emitido"),
            ("refund", "Reembolso excepcional"),
            ("rejected", "Rechazado"),
            ("cancelled", "Cancelado"),
        ],
        default="draft",
        required=True,
        copy=False,
        index=True,
    )
    request_type = fields.Selection(
        [
            ("exchange", "Cambio inmediato"),
            ("credit", "Vale de tienda"),
            ("refund", "Reembolso excepcional"),
        ],
        required=True,
        default="exchange",
    )
    reason = fields.Selection(
        [
            ("defect", "Defecto o vicio"),
            ("wrong_product", "Producto incorrecto"),
            ("change_mind", "Cambio de preferencia"),
            ("warranty", "Garantía"),
            ("other", "Otro"),
        ],
        required=True,
        default="change_mind",
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
    pos_order_id = fields.Many2one(
        "pos.order",
        string="Ticket original",
        required=True,
        ondelete="restrict",
        index=True,
    )
    holder_id = fields.Many2one(
        "leyka.voucher.holder",
        string="Titular simplificado",
        required=True,
        ondelete="restrict",
        index=True,
    )
    line_ids = fields.One2many(
        "leyka.return.request.line",
        "request_id",
        string="Productos",
        copy=True,
    )
    amount = fields.Monetary(
        compute="_compute_amount",
        store=True,
        string="Valor reconocido",
    )
    validation_note = fields.Text(string="Validación física")
    manager_note = fields.Text(string="Autorización/observaciones")
    validated_by_id = fields.Many2one(
        "res.users",
        readonly=True,
        copy=False,
    )
    validated_at = fields.Datetime(readonly=True, copy=False)
    credit_id = fields.Many2one(
        "leyka.store.credit",
        string="Vale emitido",
        readonly=True,
        copy=False,
    )
    replacement_order_id = fields.Many2one(
        "pos.order",
        string="Nueva orden",
        readonly=True,
        copy=False,
    )
    refund_reference = fields.Char(
        string="Referencia de reembolso",
        readonly=True,
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("Nuevo")) == _("Nuevo"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "leyka.return.request"
                ) or _("Nuevo")
        return super().create(vals_list)

    @api.depends("line_ids.return_amount")
    def _compute_amount(self):
        for request in self:
            request.amount = sum(request.line_ids.mapped("return_amount"))

    @api.onchange("pos_order_id")
    def _onchange_pos_order_id(self):
        if self.pos_order_id and not self.holder_id:
            partner = self.pos_order_id.partner_id
            if partner and partner.phone:
                holder = self.env["leyka.voucher.holder"].search(
                    [
                        ("partner_id", "=", partner.id),
                        ("company_id", "=", self.company_id.id),
                    ],
                    limit=1,
                )
                if holder:
                    self.holder_id = holder

    def _check_request_quantities(self):
        for request in self:
            if not request.line_ids:
                raise ValidationError(_("Agrega por lo menos un producto."))
            for line in request.line_ids:
                already = self.env["leyka.return.request.line"].search(
                    [
                        ("id", "!=", line.id),
                        ("order_line_id", "=", line.order_line_id.id),
                        (
                            "request_id.state",
                            "not in",
                            ("draft", "rejected", "cancelled"),
                        ),
                    ]
                )
                remaining = abs(line.order_line_id.qty) - sum(
                    already.mapped("quantity")
                )
                if float_compare(
                    line.quantity,
                    remaining,
                    precision_rounding=line.order_line_id.product_id.uom_id.rounding,
                ) > 0:
                    raise ValidationError(
                        _(
                            "La cantidad de %(product)s excede lo disponible "
                            "para cambio (%(remaining)s).",
                            product=line.product_id.display_name,
                            remaining=remaining,
                        )
                    )

    def action_validate(self):
        for request in self:
            if request.state != "draft":
                raise UserError(_("Solo se puede validar una solicitud en borrador."))
            request._check_request_quantities()
            if request.request_type == "refund" and not self.env.user.has_group(
                "leyka_local_core.group_leyka_manager"
            ):
                raise AccessError(
                    _("El reembolso de dinero requiere autorización del responsable.")
                )
            request.write(
                {
                    "state": "validated",
                    "validated_by_id": self.env.user.id,
                    "validated_at": fields.Datetime.now(),
                }
            )

    def action_prepare_exchange(self):
        for request in self:
            if request.state != "validated":
                raise UserError(_("Primero valida físicamente la devolución."))
            request.state = "exchange"

    def action_issue_credit(self):
        self.ensure_one()
        if self.state != "validated":
            raise UserError(_("Primero valida físicamente la devolución."))
        if self.currency_id.is_zero(self.amount):
            raise UserError(_("El valor del vale debe ser mayor que cero."))
        credit = self.env["leyka.store.credit"].create(
            {
                "holder_id": self.holder_id.id,
                "company_id": self.company_id.id,
                "amount_initial": self.amount,
                "balance": self.amount,
                "origin_order_id": self.pos_order_id.id,
                "origin_reference": self.pos_order_id.pos_reference,
                "note": _("Emitido por solicitud %s") % self.name,
            }
        )
        credit.transaction_ids.filtered(
            lambda movement: movement.operation == "issue"
        ).write({"return_request_id": self.id})
        self.write({"credit_id": credit.id, "state": "credit"})
        return {
            "type": "ir.actions.act_window",
            "res_model": "leyka.store.credit",
            "res_id": credit.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_mark_refunded(self):
        if not self.env.user.has_group("leyka_local_core.group_leyka_manager"):
            raise AccessError(_("Solo un responsable puede registrar reembolsos."))
        for request in self:
            if request.state != "validated":
                raise UserError(_("Primero valida físicamente la devolución."))
            if not request.refund_reference:
                raise ValidationError(_("Captura la referencia del reembolso."))
            request.state = "refund"

    def action_reject(self):
        self.filtered(lambda request: request.state == "draft").write(
            {"state": "rejected"}
        )

    def action_cancel(self):
        for request in self:
            if request.state in {"credit", "refund"}:
                raise UserError(
                    _("No se cancela una solicitud ya liquidada; crea una corrección.")
                )
            request.state = "cancelled"


class LeykaReturnRequestLine(models.Model):
    _name = "leyka.return.request.line"
    _description = "Producto de solicitud de cambio"
    _order = "id"

    request_id = fields.Many2one(
        "leyka.return.request",
        required=True,
        ondelete="cascade",
        index=True,
    )
    order_line_id = fields.Many2one(
        "pos.order.line",
        string="Línea original",
        required=True,
        ondelete="restrict",
        domain="[('order_id', '=', parent.pos_order_id)]",
    )
    product_id = fields.Many2one(
        related="order_line_id.product_id",
        store=True,
        readonly=True,
    )
    quantity = fields.Float(required=True, default=1.0)
    unit_paid = fields.Monetary(
        compute="_compute_return_amount",
        store=True,
        string="Precio realmente pagado",
    )
    return_amount = fields.Monetary(
        compute="_compute_return_amount",
        store=True,
        string="Valor reconocido",
    )
    currency_id = fields.Many2one(
        related="request_id.currency_id",
        store=True,
        readonly=True,
    )
    disposition = fields.Selection(
        [
            ("resalable", "Reintegrar a venta"),
            ("quarantine", "Cuarentena/revisión"),
            ("damaged", "Dañado/merma"),
            ("supplier_warranty", "Garantía con proveedor"),
        ],
        required=True,
        default="resalable",
    )
    condition_note = fields.Char(string="Condición física")

    @api.depends(
        "quantity",
        "order_line_id.qty",
        "order_line_id.price_subtotal_incl",
    )
    def _compute_return_amount(self):
        for line in self:
            sold_qty = abs(line.order_line_id.qty)
            line.unit_paid = (
                abs(line.order_line_id.price_subtotal_incl) / sold_qty
                if sold_qty
                else 0.0
            )
            line.return_amount = line.unit_paid * line.quantity

    @api.onchange("order_line_id")
    def _onchange_order_line_id(self):
        if self.order_line_id:
            category = self.order_line_id.product_id.categ_id
            self.disposition = category.leyka_default_disposition

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("La cantidad debe ser mayor que cero."))
