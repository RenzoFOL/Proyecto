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
