from odoo import api, fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    leyka_store_credit_payment = fields.Boolean(
        string="Usar para vales Leyka",
        help="Al seleccionarlo en el POS pedirá un código, nombre o teléfono y descontará el saldo del vale.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + ["leyka_store_credit_payment"]
