/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { patch } from "@web/core/utils/patch";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { LeykaExchangeDialog } from "./exchange_dialog";

patch(PosOrder.prototype, {
    waitForPushOrder() {
        const usesStoreCredit = this.payment_ids.some(
            (line) => line.payment_method_id.leyka_store_credit_payment && line.leyka_credit_code
        );
        return Boolean(this.leyka_exchange_payload?.stage === "prepared" || usesStoreCredit) || super.waitForPushOrder(...arguments);
    },
});

patch(OrderPaymentValidation.prototype, {
    async askBeforeValidation() {
        const allowed = await super.askBeforeValidation(...arguments);
        if (allowed === false) {
            return false;
        }
        const order = this.order;
        const flow = order.leyka_exchange_payload;
        if (!flow) {
            return allowed;
        }
        const refundLines = order.lines.filter(
            (line) => line.refunded_orderline_id && line.qty < 0
        );
        if (!refundLines.length) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Cambio incompleto"),
                body: _t("Selecciona por lo menos un producto del ticket original."),
            });
            return false;
        }
        if (flow.stage === "prepared") {
            return true;
        }

        const voucherAmount = Math.max(0, -order.priceIncl);
        const partner = order.getPartner();
        const payload = await makeAwaitable(this.pos.dialog, LeykaExchangeDialog, {
            title: _t("Validar cambio / vale"),
            balanceText: this.pos.env.utils.formatCurrency(voucherAmount),
            initialName: partner?.name || "",
            initialPhone: partner?.phone || partner?.mobile || "",
        });
        if (!payload) {
            return false;
        }

        if (voucherAmount > 0) {
            const product = this.pos.config.leyka_credit_product_id;
            if (!product) {
                this.pos.dialog.add(AlertDialog, {
                    title: _t("Falta configuración"),
                    body: _t("Selecciona el producto técnico de vales en la configuración del POS."),
                });
                return false;
            }
            for (const paymentLine of [...order.payment_ids]) {
                order.removePaymentline(paymentLine);
            }
            await this.pos.addLineToOrder(
                {
                    product_id: product,
                    product_tmpl_id: product.product_tmpl_id,
                    price_unit: voucherAmount,
                    qty: 1,
                },
                order,
                { merge: false, force: true },
                false
            );
        }
        order.leyka_exchange_payload = {
            ...payload,
            voucher_amount: voucherAmount,
            stage: "prepared",
        };
        return true;
    },

    async beforePostPushOrderResolve(order, orderServerIds) {
        const parentResult = await super.beforePostPushOrderResolve(...arguments);
        if (parentResult === false) {
            return parentResult;
        }
        if (order.leyka_exchange_payload?.stage === "prepared") {
            const result = await this.pos.data.call(
                "leyka.return.request",
                "finalize_from_pos",
                [[], order.id, order.leyka_exchange_payload]
            );
            order.leykaVoucherResult = result;
            order.leyka_exchange_payload = {
                ...order.leyka_exchange_payload,
                stage: "completed",
                return_request_id: result.return_request_id,
            };
        }
        if (
            order.payment_ids.some(
                (line) => line.payment_method_id.leyka_store_credit_payment && line.leyka_credit_code
            )
        ) {
            order.leykaCreditRedemptions = await this.pos.data.call(
                "leyka.store.credit",
                "finalize_pos_redemptions",
                [[], order.id]
            );
        }
        return true;
    },

    async afterOrderValidation() {
        const regularPrintWillRun = this.canPrintReceipt;
        const result = await super.afterOrderValidation(...arguments);
        if (this.order.leykaVoucherResult?.credit_code && !regularPrintWillRun) {
            await this.pos.printReceipt({ order: this.order });
        }
        return result;
    },
});
