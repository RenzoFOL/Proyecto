import { registry } from "@web/core/registry";
import * as Product from "@point_of_sale/../tests/pos/tours/utils/product_screen_util";
import * as Chrome from "@point_of_sale/../tests/pos/tours/utils/chrome_util";
import * as Dialog from "@point_of_sale/../tests/generic_helpers/dialog_util";
import * as Ticket from "@point_of_sale/../tests/pos/tours/utils/ticket_screen_util";
import * as Payment from "@point_of_sale/../tests/pos/tours/utils/payment_screen_util";
import * as Receipt from "@point_of_sale/../tests/pos/tours/utils/receipt_screen_util";
import * as Loyalty from "@pos_loyalty/../tests/tours/utils/pos_loyalty_util";

registry.category("web_tour.tours").add("leyka_vales_issue_redeem", {
    steps: () => [
        Chrome.startPoS(), Dialog.confirm("Open Register"),
        Product.clickDisplayedProduct("Pieza Leyka QA"),
        Loyalty.finalizeOrder("Cash", "100"),
        Product.clickControlButton("Cambios / vales"),
        { trigger: ".leyka-vales button:contains('Emitir vale')", run: "click" },
        Ticket.selectOrder("001"), Product.clickNumpad("1"), Ticket.confirmRefund(),
        { trigger: "#leyka-holder", run: "text Titular Prueba" },
        { trigger: "#leyka-phone", run: "text 2225238163" },
        { trigger: "#leyka-reason", run: "text Pieza sin instalar, cambio aprobado" },
        { trigger: "#leyka-review", run: "click" },
        { trigger: ".leyka-vales button:contains('Continuar')", run: "click" },
        Payment.isShown(), Payment.clickValidate(),
        { trigger: ".receipt-screen .leyka-vale-ticket:contains('Titular Prueba')" },
        { trigger: ".receipt-screen .leyka-code", run() {
            if (!/^LK-[A-F0-9]{20}$/.test(this.anchor.textContent.trim())) throw new Error("Bad random code");
        } },
        Receipt.clickNextOrder(),
        Product.clickDisplayedProduct("Repuesto Leyka QA"),
        Product.clickControlButton("Cambios / vales"),
        { trigger: ".leyka-vales button:contains('Buscar, canjear')", run: "click" },
        { trigger: "#leyka-search", run: "text 2225238163" },
        { trigger: ".leyka-vales button:contains('Buscar')", run: "click" },
        { trigger: ".leyka-vales button:contains('Canjear en esta compra')", run: "click" },
        Loyalty.orderTotalIs("0.0"),
        Product.clickPayButton(), Payment.clickValidate(),
        Receipt.clickNextOrder(),
    ].flat(),
});
