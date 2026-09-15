from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    leyka_return_request_id = fields.Many2one(
        "leyka.return.request",
        string="Solicitud de cambio Leyka",
        readonly=True,
        copy=False,
        index=True,
    )
