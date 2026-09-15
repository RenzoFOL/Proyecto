from odoo import Command
from odoo.addons.point_of_sale.tests.common import TestPoSCommon
from odoo.tests import tagged
from odoo.exceptions import UserError, ValidationError


@tagged("post_install", "-at_install")
class TestLeykaPosExchange(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.env.user.group_ids |= self.env.ref("leyka_local_core.group_leyka_manager")
        self.config = self.basic_config
        self.bank_payment_method = self.bank_pm1
        self.cash_payment_method = self.cash_pm1
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
        self.env["stock.quant"].sudo()._update_available_quantity(
            self.product, self.config.picking_type_id.default_location_src_id, 10.0
        )
        self.open_new_session()

    def _sync_order(self, data):
        self.env["pos.order"].sync_from_ui([data])
        return self.env["pos.order"].search([("uuid", "=", data["uuid"])], limit=1)

    def _make_exchange(self, disposition="resalable"):
        original_data = self.create_ui_order_data([(self.product, 1)])
        original = self._sync_order(original_data)
        original_line = original.lines
        credit_product = self.config.leyka_credit_product_id
        payload = {
            "holder_name": "Cliente Prueba",
            "holder_phone": "55 1234 5678",
            "reason": "change_mind",
            "physical_condition": "unopened",
            "disposition": disposition,
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
        return refund_order, payload, result

    def test_exchange_issues_idempotent_named_credit(self):
        refund_order, payload, result = self._make_exchange()
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

    def test_damaged_return_routes_once(self):
        refund_order, payload, result = self._make_exchange("damaged")
        request = self.env["leyka.return.request"].browse(result["return_request_id"])
        request.action_route_returned_stock()
        request.action_route_returned_stock()
        self.assertEqual(request.stock_routing_state, "done")
        self.assertEqual(len(request.routing_picking_ids), 1)
        self.assertEqual(request.routing_picking_ids.state, "done")
        self.assertEqual(request.routing_picking_ids.location_dest_id,
                         self.config.leyka_damaged_location_id)
        self.assertEqual(request.routing_picking_ids.move_ids.quantity, 1)

    def test_credit_failure_rolls_back_sale(self):
        holder = self.env["leyka.voucher.holder"].create(
            {"name": "Saldo limitado", "phone": "5511112234"}
        )
        credit = self.env["leyka.store.credit"].create(
            {"holder_id": holder.id, "amount_initial": 20.0}
        )
        data = self.create_ui_order_data(
            [(self.product, 1)],
            payments=[(self.bank_payment_method, 40.0), (self.cash_payment_method, 60.0)],
        )
        data["payment_ids"][0][2]["leyka_credit_code"] = credit.code
        order_uuid = data["uuid"]
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self._sync_order(data)
        self.assertFalse(self.env["pos.order"].search([("uuid", "=", order_uuid)]))
        self.assertEqual(credit.balance, 20.0)

    def test_missing_voucher_code_rejects_sale(self):
        data = self.create_ui_order_data(
            [(self.product, 1)], payments=[(self.bank_payment_method, 100.0)]
        )
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._sync_order(data)

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
