from odoo import Command
from odoo.addons.point_of_sale.tests.common import CommonPosTest
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestLeykaPosExchange(CommonPosTest):
    def setUp(self):
        super().setUp()
        self.config = self.pos_config_usd
        self.config.leyka_enable_changes = True
        self.config.leyka_credit_product_id = self.env.ref(
            "leyka_pos_exchange.product_leyka_store_credit"
        )
        self.bank_payment_method.leyka_store_credit_payment = True
        self.config.payment_method_ids |= self.bank_payment_method
        product_category = self.env["product.category"].create(
            {"name": "Categoría prueba Leyka"}
        )
        self.product = self.env["product.product"].create(
            {
                "name": "Relay Leyka",
                "available_in_pos": True,
                "type": "consu",
                "is_storable": True,
                "categ_id": product_category.id,
                "list_price": 100.0,
                "standard_price": 60.0,
                "taxes_id": [Command.clear()],
            }
        )
        self.open_new_session()

    def _sync_order(self, data):
        self.env["pos.order"].sync_from_ui([data])
        return self.env["pos.order"].search([("uuid", "=", data["uuid"])], limit=1)

    def test_exchange_issues_idempotent_named_credit(self):
        original_data = self.create_ui_order_data([(self.product, 1)])
        original = self._sync_order(original_data)
        original_line = original.lines
        credit_product = self.config.leyka_credit_product_id
        payload = {
            "holder_name": "Cliente Prueba",
            "holder_phone": "55 1234 5678",
            "reason": "change_mind",
            "physical_condition": "unopened",
            "disposition": "resalable",
            "stage": "prepared",
        }
        refund_data = self.create_ui_order_data(
            [
                {
                    "product": self.product,
                    "quantity": -1,
                    "refunded_orderline_id": original_line.id,
                },
                {
                    "product": credit_product,
                    "quantity": 1,
                    "price_unit": 100.0,
                    "price_subtotal": 100.0,
                    "price_subtotal_incl": 100.0,
                    "tax_ids": [Command.clear()],
                },
            ],
            pos_order_ui_args={
                "is_refund": True,
                "leyka_exchange_payload": payload,
            },
            payments=[],
        )
        refund_order = self._sync_order(refund_data)

        result = self.env["leyka.return.request"].finalize_from_pos(
            refund_order.id, payload
        )
        repeated = self.env["leyka.return.request"].finalize_from_pos(
            refund_order.id, payload
        )

        self.assertEqual(result["return_request_id"], repeated["return_request_id"])
        self.assertEqual(result["credit_amount"], 100.0)
        self.assertEqual(result["holder_phone"], "55 1234 5678")
        self.assertEqual(
            self.env["leyka.return.request"].search_count(
                [("replacement_order_id", "=", refund_order.id)]
            ),
            1,
        )

    def test_credit_redemption_is_idempotent(self):
        holder = self.env["leyka.voucher.holder"].create(
            {"name": "Titular Vale", "phone": "5511112233"}
        )
        credit = self.env["leyka.store.credit"].create(
            {"holder_id": holder.id, "amount_initial": 100.0, "balance": 100.0}
        )
        payment_method = self.bank_payment_method
        sale_data = self.create_ui_order_data(
            [(self.product, 1)],
            payments=[(payment_method, 40.0), (self.cash_payment_method, 60.0)],
        )
        sale_data["payment_ids"][0][2]["leyka_credit_code"] = credit.code
        order = self._sync_order(sale_data)

        model = self.env["leyka.store.credit"]
        first = model.finalize_pos_redemptions(order.id)
        second = model.finalize_pos_redemptions(order.id)

        self.assertEqual(first[0]["used"], 40.0)
        self.assertEqual(second[0]["used"], 40.0)
        self.assertEqual(credit.balance, 60.0)
        self.assertEqual(
            credit.transaction_ids.filtered(
                lambda movement: movement.operation == "redeem"
                and movement.pos_order_id == order
            ).mapped("amount"),
            [-40.0],
        )
