import re

from odoo import api, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.osv import expression
from odoo.tools.float_utils import float_compare


class LeykaStoreCreditPos(models.Model):
    _inherit = "leyka.store.credit"

    @api.model
    def _check_pos_access(self):
        if not (
            self.env.user.has_group("point_of_sale.group_pos_user")
            or self.env.user.has_group("leyka_local_core.group_leyka_operator")
        ):
            raise AccessError(_("No tienes permiso para consultar vales desde el POS."))

    @api.model
    def lookup_for_pos(self, term):
        self._check_pos_access()
        term = (term or "").strip()
        if len(term) < 3:
            raise ValidationError(_("Escribe por lo menos 3 caracteres."))
        digits = re.sub(r"\D", "", term)
        alternatives = [
            [("code", "ilike", term)],
            [("holder_id.name", "ilike", term)],
            [("holder_id.phone", "ilike", term)],
        ]
        if digits:
            alternatives.append([("holder_id.phone_normalized", "ilike", digits)])
        domain = expression.AND(
            [
                [
                    ("company_id", "=", self.env.company.id),
                    ("active", "=", True),
                    ("balance", ">", 0),
                ],
                expression.OR(alternatives),
            ]
        )
        credits = self.sudo().search(domain, order="create_date desc", limit=20)
        return [
            {
                "id": credit.id,
                "code": credit.code,
                "holder_name": credit.holder_id.name,
                "holder_phone": credit.holder_id.phone,
                "balance": credit.balance,
                "expiration_date": credit.expiration_date.isoformat()
                if credit.expiration_date
                else False,
            }
            for credit in credits
            if credit.state == "active"
        ]

    @api.model
    def finalize_pos_redemptions(self, pos_order_id):
        self._check_pos_access()
        actor = self.env.user
        order = self.env["pos.order"].browse(int(pos_order_id)).exists()
        if not order:
            raise UserError(_("No se encontró la orden POS para aplicar el vale."))
        order.check_access("write")
        if order.company_id not in self.env.companies:
            raise AccessError(_("La orden pertenece a otra compañía."))
        if order.state not in ("paid", "done", "invoiced"):
            raise ValidationError(_("Primero confirma la venta."))
        self.env.cr.execute("SELECT id FROM pos_order WHERE id = %s FOR UPDATE", [order.id])
        payments = order.payment_ids.filtered(
            lambda payment: payment.payment_method_id.leyka_store_credit_payment
        )
        if any(not payment.leyka_credit_code for payment in payments):
            raise ValidationError(_("Selecciona un vale para cada pago Leyka."))
        if len(payments.mapped("leyka_credit_code")) != len(set(payments.mapped("leyka_credit_code"))):
            raise ValidationError(_("Usa una sola línea de pago por cada vale."))
        if payments and (order.amount_total < 0 or any(p.amount < 0 for p in order.payment_ids)):
            raise ValidationError(_("El canje de un vale no permite devolución de dinero."))
        if sum(payments.mapped("amount")) > order.amount_total + order.currency_id.rounding / 2:
            raise ValidationError(_("Los vales no pueden exceder el total de la venta."))
        results = []
        for payment in payments.sorted("leyka_credit_code"):
            if payment.amount <= 0:
                raise ValidationError(_("Un vale no puede usarse para devolver efectivo."))
            credit = self.sudo().search(
                [
                    ("code", "=ilike", payment.leyka_credit_code.strip()),
                    ("company_id", "=", order.company_id.id),
                ],
                limit=1,
            )
            if not credit:
                raise UserError(_("El vale %s no existe.") % payment.leyka_credit_code)
            if credit.currency_id != order.currency_id:
                raise ValidationError(_("El vale y la venta deben usar la misma moneda."))
            credit._lock_and_read_balance()
            prior = self.env["leyka.store.credit.transaction"].sudo().search(
                [
                    ("credit_id", "=", credit.id),
                    ("pos_order_id", "=", order.id),
                    ("operation", "=", "redeem"),
                ],
                limit=1,
            )
            if prior:
                if float_compare(
                    abs(prior.amount),
                    payment.amount,
                    precision_rounding=order.currency_id.rounding,
                ) != 0:
                    raise ValidationError(_("La orden ya usó ese vale por otro importe."))
            else:
                movement = credit.sudo().redeem(
                    payment.amount,
                    pos_order=order,
                    note=_("Canje en %s") % order.pos_reference,
                )
                movement.write({"user_id": actor.id})
            results.append(
                {
                    "code": credit.code,
                    "used": payment.amount,
                    "balance": credit.balance,
                }
            )
        return results
