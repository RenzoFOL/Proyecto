from odoo import api, fields, models


class PosPayment(models.Model):
    _inherit = "pos.payment"

    leyka_credit_code = fields.Char(
        string="Vale Leyka",
        copy=False,
        index=True,
    )

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + ["leyka_credit_code"]
