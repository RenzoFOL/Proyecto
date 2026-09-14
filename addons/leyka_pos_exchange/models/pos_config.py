from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    leyka_enable_changes = fields.Boolean(
        string="Cambios y vales Leyka",
        default=True,
    )
    leyka_require_holder = fields.Boolean(
        string="Exigir nombre y teléfono para vales",
        default=True,
    )
    leyka_manager_refund_only = fields.Boolean(
        string="Reembolso de dinero solo con responsable",
        default=True,
    )
