/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";

patch(ControlButtons.prototype, {
    async onClickLeykaChanges() {
        const order = this.pos.getOrder();
        const partner = order.getPartner();
        order.leyka_exchange_payload = { stage: "selecting" };
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
                destinationOrder: order,
            },
        });
    },
});
