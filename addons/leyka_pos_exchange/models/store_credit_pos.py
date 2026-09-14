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
        payments = order.payment_ids.filtered(
            lambda payment: payment.payment_method_id.leyka_store_credit_payment
            and payment.leyka_credit_code
        )
        results = []
        for payment in payments:
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
