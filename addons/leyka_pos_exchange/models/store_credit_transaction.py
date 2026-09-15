from odoo import fields, models


class LeykaStoreCreditTransaction(models.Model):
    _inherit = "leyka.store.credit.transaction"

    return_request_id = fields.Many2one(
        "leyka.return.request",
        string="Solicitud de cambio",
        ondelete="set null",
        index=True,
    )
