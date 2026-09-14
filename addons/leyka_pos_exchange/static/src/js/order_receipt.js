/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { generateQRCodeDataUrl } from "@point_of_sale/utils";

patch(OrderReceipt.prototype, {
    get leykaVoucherQr() {
        const code = this.order.leykaVoucherResult?.credit_code;
        return code ? generateQRCodeDataUrl(code) : false;
    },
});
