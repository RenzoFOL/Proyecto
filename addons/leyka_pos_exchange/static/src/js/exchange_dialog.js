/** @odoo-module */

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class LeykaExchangeDialog extends Component {
    static template = "leyka_pos_exchange.ExchangeDialog";
    static components = { Dialog };
    static props = {
        title: String,
        balanceText: String,
        initialName: { type: String, optional: true },
        initialPhone: { type: String, optional: true },
        getPayload: Function,
        close: Function,
    };

    setup() {
        this.state = useState({
            holderName: this.props.initialName || "",
            holderPhone: this.props.initialPhone || "",
            reason: "change_mind",
            physicalCondition: "unopened",
            disposition: "resalable",
            note: "",
        });
    }

    get isValid() {
        const digits = this.state.holderPhone.replace(/\D/g, "");
        return Boolean(this.state.holderName.trim() && digits.length >= 8);
    }

    confirm() {
        if (!this.isValid) {
            return;
        }
        this.props.getPayload({
            holder_name: this.state.holderName.trim(),
            holder_phone: this.state.holderPhone.trim(),
            reason: this.state.reason,
            physical_condition: this.state.physicalCondition,
            disposition: this.state.disposition,
            note: this.state.note.trim(),
        });
        this.props.close();
    }
}
