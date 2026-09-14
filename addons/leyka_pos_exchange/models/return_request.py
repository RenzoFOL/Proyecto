import re

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
            ("exchange", "Cambio terminado"),
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
        string="Valor devuelto",
    )
    credit_amount = fields.Monetary(
        string="Saldo convertido en vale",
        readonly=True,
        copy=False,
    )
    validation_note = fields.Text(string="Validación física")
    manager_note = fields.Text(string="Autorización/observaciones")
    validated_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    validated_at = fields.Datetime(readonly=True, copy=False)
    credit_id = fields.Many2one(
        "leyka.store.credit",
        string="Vale emitido",
        readonly=True,
        copy=False,
    )
    replacement_order_id = fields.Many2one(
        "pos.order",
        string="Orden de cambio",
        readonly=True,
        copy=False,
        index=True,
    )
    refund_reference = fields.Char(
        string="Referencia de reembolso",
        readonly=True,
        copy=False,
    )

    _sql_constraints = [
        (
            "leyka_return_replacement_order_uniq",
            "unique(replacement_order_id)",
            "Esta orden POS ya fue procesada como cambio Leyka.",
        ),
    ]

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

    def _actor_user(self):
        actor_id = self.env.context.get("leyka_actor_user_id")
        return self.env["res.users"].browse(actor_id).exists() if actor_id else self.env.user

    def _check_request_quantities(self):
        actor = self._actor_user()
        is_manager = actor.has_group("leyka_local_core.group_leyka_manager")
        today = fields.Date.context_today(self)
        for request in self:
            if not request.line_ids:
                raise ValidationError(_("Agrega por lo menos un producto."))
            sale_date = fields.Date.to_date(request.pos_order_id.date_order)
            for line in request.line_ids:
                already = self.env["leyka.return.request.line"].sudo().search(
                    [
                        ("id", "!=", line.id),
                        ("order_line_id", "=", line.order_line_id.id),
                        ("request_id.state", "not in", ("draft", "rejected", "cancelled")),
                    ]
                )
                remaining = abs(line.order_line_id.qty) - sum(already.mapped("quantity"))
                if float_compare(
                    line.quantity,
                    remaining,
                    precision_rounding=line.order_line_id.product_id.uom_id.rounding,
                ) > 0:
                    raise ValidationError(
                        _(
                            "La cantidad de %(product)s excede lo disponible para cambio (%(remaining)s).",
                            product=line.product_id.display_name,
                            remaining=remaining,
                        )
                    )

                category = line.product_id.categ_id
                days_elapsed = (today - sale_date).days if sale_date else 0
                policy_errors = []
                if not category.leyka_allow_return:
                    policy_errors.append(_("la categoría no permite cambios"))
                if category.leyka_return_days >= 0 and days_elapsed > category.leyka_return_days:
                    policy_errors.append(
                        _("venció el plazo de %(days)s días", days=category.leyka_return_days)
                    )
                if category.leyka_requires_unopened and line.physical_condition != "unopened":
                    policy_errors.append(_("requiere empaque cerrado"))
                if policy_errors and not is_manager:
                    raise AccessError(
                        _(
                            "%(product)s requiere autorización de responsable: %(reason)s.",
                            product=line.product_id.display_name,
                            reason=", ".join(policy_errors),
                        )
                    )

    def action_validate(self):
        actor = self._actor_user()
        for request in self:
            if request.state != "draft":
                raise UserError(_("Solo se puede validar una solicitud en borrador."))
            request._check_request_quantities()
            if request.request_type == "refund" and not actor.has_group(
                "leyka_local_core.group_leyka_manager"
            ):
                raise AccessError(_("El reembolso de dinero requiere autorización del responsable."))
            request.write(
                {
                    "state": "validated",
                    "validated_by_id": actor.id,
                    "validated_at": fields.Datetime.now(),
                }
            )
        return True

    def action_prepare_exchange(self):
        for request in self:
            if request.state != "validated":
                raise UserError(_("Primero valida físicamente la devolución."))
            request.state = "exchange"
        return True

    def _issue_credit(self):
        self.ensure_one()
        if self.state != "validated":
            raise UserError(_("Primero valida físicamente la devolución."))
        value = self.credit_amount or self.amount
        if self.currency_id.is_zero(value) or value < 0:
            raise UserError(_("El valor del vale debe ser mayor que cero."))
        actor = self._actor_user()
        credit = self.env["leyka.store.credit"].sudo().with_context(
            leyka_actor_user_id=actor.id
        ).create(
            {
                "holder_id": self.holder_id.id,
                "company_id": self.company_id.id,
                "amount_initial": value,
                "balance": value,
                "origin_order_id": self.pos_order_id.id,
                "origin_reference": self.pos_order_id.pos_reference,
                "note": _("Emitido por solicitud %s") % self.name,
            }
        )
        issue_movements = credit.transaction_ids.filtered(
            lambda movement: movement.operation == "issue"
        )
        issue_movements.write(
            {"return_request_id": self.id, "user_id": actor.id}
        )
        self.write({"credit_id": credit.id, "state": "credit"})
        return credit

    def action_issue_credit(self):
        self.ensure_one()
        credit = self._issue_credit()
        return {
            "type": "ir.actions.act_window",
            "res_model": "leyka.store.credit",
            "res_id": credit.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_mark_refunded(self):
        actor = self._actor_user()
        if not actor.has_group("leyka_local_core.group_leyka_manager"):
            raise AccessError(_("Solo un responsable puede registrar reembolsos."))
        for request in self:
            if request.state != "validated":
                raise UserError(_("Primero valida físicamente la devolución."))
            if not request.refund_reference:
                raise ValidationError(_("Captura la referencia del reembolso."))
            request.state = "refund"
        return True

    def action_reject(self):
        self.filtered(lambda request: request.state == "draft").write({"state": "rejected"})
        return True

    def action_cancel(self):
        for request in self:
            if request.state in {"credit", "refund"}:
                raise UserError(_("No se cancela una solicitud ya liquidada; crea una corrección."))
            request.state = "cancelled"
        return True

    def _pos_result(self):
        self.ensure_one()
        credit = self.credit_id
        return {
            "return_request_id": self.id,
            "request_name": self.name,
            "state": self.state,
            "credit_code": credit.code if credit else False,
            "credit_amount": credit.amount_initial if credit else 0.0,
            "credit_balance": credit.balance if credit else 0.0,
            "holder_name": self.holder_id.name,
            "holder_phone": self.holder_id.phone,
        }

    @api.model
    def finalize_from_pos(self, refund_order_id, payload):
        actor = self.env.user
        if not (
            actor.has_group("point_of_sale.group_pos_user")
            or actor.has_group("leyka_local_core.group_leyka_operator")
        ):
            raise AccessError(_("No tienes permiso para procesar cambios desde el POS."))

        refund_order = self.env["pos.order"].browse(int(refund_order_id)).exists()
        if not refund_order:
            raise UserError(_("No se encontró la orden POS del cambio."))
        existing = self.sudo().search(
            [("replacement_order_id", "=", refund_order.id)], limit=1
        )
        if existing:
            return existing._pos_result()
        if not refund_order.config_id.leyka_enable_changes:
            raise UserError(_("Los cambios Leyka no están habilitados en este punto de venta."))

        refund_lines = refund_order.lines.filtered(
            lambda line: line.refunded_orderline_id and line.qty < 0
        )
        if not refund_lines:
            raise UserError(_("La orden no contiene productos vinculados a un ticket original."))
        original_orders = refund_lines.mapped("refunded_orderline_id.order_id")
        if len(original_orders) != 1:
            raise UserError(_("Procesa un solo ticket original por cada cambio."))
        original_order = original_orders[0]
        if original_order.company_id != refund_order.company_id:
            raise UserError(_("El ticket original pertenece a otra compañía."))

        name = (payload or {}).get("holder_name", "").strip()
        phone = (payload or {}).get("holder_phone", "").strip()
        normalized_phone = re.sub(r"\D", "", phone)
        if not name or len(normalized_phone) < 8:
            raise ValidationError(_("Captura nombre y teléfono válido del cliente."))

        holder_model = self.env["leyka.voucher.holder"].sudo()
        holder = holder_model.search(
            [
                ("phone_normalized", "=", normalized_phone),
                ("company_id", "=", refund_order.company_id.id),
            ],
            limit=1,
        )
        if not holder:
            holder = holder_model.create(
                {
                    "name": name,
                    "phone": phone,
                    "company_id": refund_order.company_id.id,
                }
            )

        credit_product = refund_order.config_id.leyka_credit_product_id
        if not credit_product:
            raise UserError(_("Configura el producto técnico de vales en el punto de venta."))
        credit_lines = refund_order.lines.filtered(
            lambda line: line.product_id == credit_product and line.qty > 0
        )
        credit_amount = sum(credit_lines.mapped("price_subtotal_incl"))
        amount_without_credit = sum(
            (refund_order.lines - credit_lines).mapped("price_subtotal_incl")
        )
        expected_credit = max(0.0, -amount_without_credit)
        if float_compare(
            credit_amount,
            expected_credit,
            precision_rounding=refund_order.currency_id.rounding,
        ) != 0:
            raise ValidationError(
                _("El importe del vale no coincide con el saldo real del cambio.")
            )

        grouped = {}
        for refund_line in refund_lines:
            original_line = refund_line.refunded_orderline_id
            grouped[original_line.id] = grouped.get(original_line.id, 0.0) + abs(
                refund_line.qty
            )
        physical_condition = (payload or {}).get("physical_condition", "unopened")
        disposition = (payload or {}).get("disposition", "resalable")
        line_commands = [
            (
                0,
                0,
                {
                    "order_line_id": original_line_id,
                    "quantity": quantity,
                    "physical_condition": physical_condition,
                    "disposition": disposition,
                    "condition_note": (payload or {}).get("note"),
                },
            )
            for original_line_id, quantity in grouped.items()
        ]
        request = self.sudo().with_context(leyka_actor_user_id=actor.id).create(
            {
                "request_type": "credit" if credit_amount else "exchange",
                "reason": (payload or {}).get("reason", "change_mind"),
                "company_id": refund_order.company_id.id,
                "pos_order_id": original_order.id,
                "replacement_order_id": refund_order.id,
                "holder_id": holder.id,
                "credit_amount": credit_amount,
                "validation_note": (payload or {}).get("note"),
                "line_ids": line_commands,
            }
        )
        request.action_validate()
        if credit_amount:
            request._issue_credit()
        else:
            request.action_prepare_exchange()
        refund_order.sudo().write({"leyka_return_request_id": request.id})
        return request._pos_result()


class LeykaReturnRequestLine(models.Model):
    _name = "leyka.return.request.line"
    _description = "Producto de solicitud de cambio"
    _order = "id"

    request_id = fields.Many2one(
        "leyka.return.request", required=True, ondelete="cascade", index=True
    )
    order_line_id = fields.Many2one(
        "pos.order.line",
        string="Línea original",
        required=True,
        ondelete="restrict",
        domain="[('order_id', '=', parent.pos_order_id)]",
    )
    product_id = fields.Many2one(
        related="order_line_id.product_id", store=True, readonly=True
    )
    quantity = fields.Float(required=True, default=1.0)
    unit_paid = fields.Monetary(
        compute="_compute_return_amount", store=True, string="Precio realmente pagado"
    )
    return_amount = fields.Monetary(
        compute="_compute_return_amount", store=True, string="Valor reconocido"
    )
    currency_id = fields.Many2one(
        related="request_id.currency_id", store=True, readonly=True
    )
    physical_condition = fields.Selection(
        [
            ("unopened", "Cerrado/sin instalar"),
            ("opened_complete", "Abierto completo"),
            ("used", "Usado/instalado"),
            ("damaged", "Dañado"),
        ],
        required=True,
        default="unopened",
        string="Condición",
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
    condition_note = fields.Char(string="Detalle físico")

    @api.depends("quantity", "order_line_id.qty", "order_line_id.price_subtotal_incl")
    def _compute_return_amount(self):
        for line in self:
            sold_qty = abs(line.order_line_id.qty)
            line.unit_paid = (
                abs(line.order_line_id.price_subtotal_incl) / sold_qty if sold_qty else 0.0
            )
            line.return_amount = line.unit_paid * line.quantity

    @api.onchange("order_line_id")
    def _onchange_order_line_id(self):
        if self.order_line_id:
            self.disposition = self.order_line_id.product_id.categ_id.leyka_default_disposition

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("La cantidad debe ser mayor que cero."))
