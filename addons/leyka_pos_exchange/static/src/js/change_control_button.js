/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";

patch(ControlButtons.prototype, {
    async onClickLeykaChanges() {
        const order = this.pos.getOrder();
        const partner = order.getPartner();
        const searchDetails = partner
            ? { fieldName: "PARTNER", searchTerm: partner.name }
            : {};
        this.notification.add(
            _t(
                "Busca el ticket original y marca los productos. Después agrega aquí los productos del cambio; el POS calculará la diferencia o creará el vale."
            ),
            { type: "info", title: _t("Cambios y vales Leyka") }
        );
        this.pos.navigate("TicketScreen", {
            stateOverride: {
                filter: "SYNCED",
                search: searchDetails,
                leykaChanges: true,
            },
        });
    },
});

patch(TicketScreen.prototype, {
    async addAdditionalRefundInfo(order, destinationOrder) {
        await super.addAdditionalRefundInfo(...arguments);
        if (this.props.stateOverride?.leykaChanges) {
            destinationOrder.leyka_exchange_payload = { stage: "selecting" };
            // Refund lines retain their original links, while the difference uses
            // the normal sale/payment flow (including card terminals).
            destinationOrder.is_refund = false;
        }
    },
    async onDoRefund() {
        const result = await super.onDoRefund(...arguments);
        const order = this.pos.getOrder();
        if (this.props.stateOverride?.leykaChanges &&
            order?.leyka_exchange_payload?.stage === "selecting" &&
            order.lines.some((line) => line.refunded_orderline_id && line.qty < 0)) {
            order.setScreenData({ name: "ProductScreen" });
            this.pos.navigate("ProductScreen", { orderUuid: order.uuid });
        }
        return result;
    },
});
