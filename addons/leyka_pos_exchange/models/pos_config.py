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
        default=lambda self: self.env.ref(
            "leyka_pos_exchange.product_leyka_store_credit",
            raise_if_not_found=False,
        ),
    )
    leyka_quarantine_location_id = fields.Many2one(
        "stock.location",
        string="Ubicación de cuarentena",
        domain="[('usage', '=', 'internal'), ('company_id', 'in', (False, company_id))]",
        check_company=True,
    )
    leyka_damaged_location_id = fields.Many2one(
        "stock.location",
        string="Ubicación de dañados/merma",
        domain="[('usage', '=', 'internal'), ('company_id', 'in', (False, company_id))]",
        check_company=True,
    )
    leyka_supplier_warranty_location_id = fields.Many2one(
        "stock.location",
        string="Ubicación de garantía proveedor",
        domain="[('usage', '=', 'internal'), ('company_id', 'in', (False, company_id))]",
        check_company=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        configs = super().create(vals_list)
        configs._leyka_ensure_stock_locations()
        return configs

    def _leyka_ensure_stock_locations(self):
        location_model = self.env["stock.location"].sudo()
        field_names = {
            "leyka_quarantine_location_id": "Leyka - Cuarentena",
            "leyka_damaged_location_id": "Leyka - Dañados y merma",
            "leyka_supplier_warranty_location_id": "Leyka - Garantía proveedor",
        }
        for config in self.sudo():
            warehouse = config.picking_type_id.warehouse_id
            parent = warehouse.view_location_id
            if not parent:
                continue
            values = {}
            for field_name, location_name in field_names.items():
                if config[field_name]:
                    continue
                location = location_model.search(
                    [
                        ("name", "=", location_name),
                        ("location_id", "=", parent.id),
                        ("company_id", "in", [False, config.company_id.id]),
                    ],
                    limit=1,
                )
                if not location:
                    location = location_model.create(
                        {
                            "name": location_name,
                            "usage": "internal",
                            "location_id": parent.id,
                            "company_id": config.company_id.id,
                        }
                    )
                values[field_name] = location.id
            if values:
                config.write(values)
        return True

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
        self.search([])._leyka_ensure_stock_locations()
        return True

    def _get_special_products(self):
        products = super()._get_special_products()
        credit_product = self.env.ref(
            "leyka_pos_exchange.product_leyka_store_credit",
            raise_if_not_found=False,
        )
        return products | credit_product if credit_product else products
