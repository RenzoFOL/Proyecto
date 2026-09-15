from odoo import fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    leyka_exchange_payload = fields.Json(
        string="Datos de cambio Leyka",
        copy=False,
    )
    leyka_return_request_id = fields.Many2one(
        "leyka.return.request",
        string="Solicitud de cambio Leyka",
        readonly=True,
        copy=False,
        index=True,
    )

    def _force_create_picking_real_time(self):
        return bool(self.leyka_exchange_payload) or super()._force_create_picking_real_time()

    def _process_saved_order(self, draft):
        result = super()._process_saved_order(draft)
        if not draft and self.state in ("paid", "done", "invoiced"):
            # These mutations share the same database transaction as the POS sale.
            # If balance or policy validation fails, the entire sync rolls back.
            if self.leyka_exchange_payload:
                self.env["leyka.return.request"].finalize_from_pos(
                    self.id, self.leyka_exchange_payload
                )
            if any(self.payment_ids.payment_method_id.mapped("leyka_store_credit_payment")):
                self.env["leyka.store.credit"].finalize_pos_redemptions(self.id)
        return result
