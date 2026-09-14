/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";

patch(ControlButtons.prototype, {
    async onClickLeykaChanges() {
        const order = this.pos.getOrder();
        const partner = order.getPartner();
        const searchDetails = partner
            ? { fieldName: "PARTNER", searchTerm: partner.name }
            : {};
        this.notification.add(
            "Busca el ticket original y selecciona los productos a devolver. El valor se calculará con el precio realmente pagado.",
            { type: "info", title: "Cambios y vales Leyka" }
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
