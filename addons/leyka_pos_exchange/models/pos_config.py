from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    leyka_enable_changes = fields.Boolean(
        string="Cambios y vales Leyka",
        default=True,
    )
    leyka_require_holder = fields.Boolean(
        string="Exigir nombre y teléfono",
        default=True,
    )
    leyka_manager_refund_only = fields.Boolean(
        string="Reembolso de dinero solo con responsable",
        default=True,
    )
    leyka_credit_product_id = fields.Many2one(
        "product.product",
        string="Producto técnico para emitir vales",
        domain="[('type', '=', 'service')]",
        help="Producto sin impuestos usado para equilibrar la orden cuando queda saldo a favor del cliente.",
        copy=False,
    )

    @api.model
    def _leyka_initialize_credit_product(self):
        product = self.env.ref(
            "leyka_pos_exchange.product_leyka_store_credit",
            raise_if_not_found=False,
        )
        if product:
            self.search([("leyka_credit_product_id", "=", False)]).write(
                {"leyka_credit_product_id": product.id}
            )
        return True

    def _get_special_products(self):
        products = super()._get_special_products()
        credit_product = self.env.ref(
            "leyka_pos_exchange.product_leyka_store_credit",
            raise_if_not_found=False,
        )
        return products | credit_product if credit_product else products
