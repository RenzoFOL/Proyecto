/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { patch } from "@web/core/utils/patch";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        if (!paymentMethod.leyka_store_credit_payment) {
            return await super.addNewPaymentLine(...arguments);
        }
        if (this.currentOrder.isRefund) {
            this.dialog.add(AlertDialog, {
                title: _t("Vale no permitido"),
                body: _t("Los vales se usan para pagar ventas; nunca para entregar efectivo."),
            });
            return false;
        }
        const query = await makeAwaitable(this.dialog, TextInputPopup, {
            title: _t("Buscar vale Leyka"),
            placeholder: _t("Código, nombre o teléfono"),
        });
        if (!query) {
            return false;
        }
        const credits = await this.pos.data.call(
            "leyka.store.credit",
            "lookup_for_pos",
            [[], query]
        );
        if (!credits.length) {
            this.dialog.add(AlertDialog, {
                title: _t("Vale no encontrado"),
                body: _t("No hay un vale activo con saldo para esa búsqueda."),
            });
            return false;
        }
        let credit = credits[0];
        if (credits.length > 1) {
            credit = await makeAwaitable(this.dialog, SelectionPopup, {
                title: _t("Selecciona el vale"),
                list: credits.map((item) => ({
                    id: item.id,
                    label: `${item.code} — ${item.holder_name}`,
                    description: `${item.holder_phone} · ${this.env.utils.formatCurrency(item.balance)}`,
                    item,
                })),
            });
        }
        if (!credit) {
            return false;
        }
        if (this.paymentLines.some((line) => line.leyka_credit_code === credit.code)) {
            this.dialog.add(AlertDialog, {
                title: _t("Vale repetido"),
                body: _t("Ese vale ya está agregado a la orden."),
            });
            return false;
        }
        const amountDue = Math.max(0, this.currentOrder.remainingDue);
        const result = this.currentOrder.addPaymentline(paymentMethod);
        if (!result.status) {
            this.dialog.add(AlertDialog, { title: _t("Error"), body: result.data });
            return false;
        }
        const amount = Math.min(credit.balance, amountDue);
        result.data.setAmount(amount);
        result.data.leyka_credit_code = credit.code;
        result.data.leyka_credit_balance = credit.balance;
        this.numberBuffer.set(amount.toString());
        return true;
    },

    updateSelectedPaymentline(amount = false) {
        const line = this.selectedPaymentLine;
        const result = super.updateSelectedPaymentline(...arguments);
        if (line?.leyka_credit_code && line.amount > line.leyka_credit_balance) {
            line.setAmount(line.leyka_credit_balance);
            this.numberBuffer.set(line.leyka_credit_balance.toString());
            this.notification.add(
                _t("El importe se limitó al saldo disponible del vale."),
                { type: "warning" }
            );
        }
        return result;
    },
});
