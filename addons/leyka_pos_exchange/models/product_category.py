from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    leyka_allow_return = fields.Boolean(
        string="Permitir cambios",
        default=True,
    )
    leyka_return_days = fields.Integer(
        string="Días para cambio",
        default=30,
    )
    leyka_requires_unopened = fields.Boolean(
        string="Requerir empaque cerrado",
        default=False,
    )
    leyka_default_disposition = fields.Selection(
        [
            ("resalable", "Reintegrar a venta"),
            ("quarantine", "Cuarentena/revisión"),
            ("damaged", "Dañado/merma"),
            ("supplier_warranty", "Garantía con proveedor"),
        ],
        string="Destino predeterminado",
        default="resalable",
        required=True,
    )
