/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/core/dialog/dialog";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

const SKU = "LEYKA-VALE-DEV";
const FIELD_NAMES = ["holder", "phone", "reason", "reviewed", "code", "pending"];
const CARD_FIELDS = ["id", "code", "points", "source_pos_order_id", "program_id", "x_leyka_vale_holder", "x_leyka_vale_phone"];
const isValeLine = (line) => line.product_id?.default_code === SKU;
const programFor = (pos) => pos.models["loyalty.program"].find(
    (p) => p.program_type === "gift_card" && p.trigger_product_ids.some((v) => v.default_code === SKU)
);
export function normalizePhone(value) {
    let digits = String(value || "").replace(/\D/g, "");
    if (digits.length === 12 && digits.startsWith("52")) digits = digits.slice(2);
    return digits;
}
export function randomValeCode() {
    // 80 random bits. No names, phone numbers or sequential IDs in the code.
    const bytes = crypto.getRandomValues(new Uint8Array(10));
    return "LK-" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("").toUpperCase();
}
function inform(pos, body) {
    pos.dialog.add(AlertDialog, { title: "Vales Leyka", body });
}
function orderFields(order) {
    return Object.fromEntries(FIELD_NAMES.map((n) => ["x_leyka_vale_" + n, order["x_leyka_vale_" + n]]));
}
patch(PosOrder, {
    extraFields: {
        ...(PosOrder.extraFields || {}),
        ...Object.fromEntries(FIELD_NAMES.map((n) => ["x_leyka_vale_" + n, {
            name: "x_leyka_vale_" + n, model: "pos.order",
            type: ["reviewed", "pending"].includes(n) ? "boolean" : n === "reason" ? "text" : "char", local: false,
        }])),
    },
});

export class ValeReceipt extends Component {
    static template = "leyka_pos_vales.ValeReceipt";
    static props = { card: Object, amount: Number, reprint: Boolean };
    money(value) { return this.env.utils.formatCurrency(value); }
}

export class ValesDialog extends Component {
    static template = "leyka_pos_vales.ValesDialog";
    static components = { Dialog };
    static props = { close: Function, mode: { type: String, optional: true } };
    setup() {
        this.pos = usePos();
        const order = this.pos.getOrder();
        this.state = useState({
            mode: this.props.mode || "home", name: order?.x_leyka_vale_holder || "",
            phone: order?.x_leyka_vale_phone || "", reason: order?.x_leyka_vale_reason || "",
            reviewed: false, query: "", rows: [], pending: [], busy: false, error: "", searched: false,
        });
    }
    get refundAmount() {
        return Math.max(0, -(this.pos.getOrder()?.priceIncl || 0));
    }
    money(value) { return this.env.utils.formatCurrency(value); }
    async run(fn) {
        if (this.state.busy) return;
        this.state.busy = true;
        this.state.error = "";
        try { await fn(); }
        catch (error) { this.state.error = error?.data?.message || error.message || "No se pudo conectar con Odoo. Intenta de nuevo."; }
        finally { this.state.busy = false; }
    }
    startReturn() {
        const order = this.pos.getOrder();
        if (order.lines.some((l) => l.refunded_orderline_id) && order.priceIncl < 0) {
            order.x_leyka_vale_pending = true;
            this.state.mode = "issue";
            return;
        }
        if (order.lines.length) {
            this.state.error = "Termina o guarda la venta actual y abre una orden vacía para buscar la devolución.";
            return;
        }
        this.pos._leykaValeFlow = true;
        this.props.close();
        this.pos.navigate("TicketScreen", { stateOverride: { filter: "SYNCED", destinationOrder: order } });
        this.pos.notification.add("Busca la venta, selecciona las unidades aceptadas y pulsa Reembolso. Después capturaremos el titular del vale.", { type: "info" });
    }
    async issue() {
        await this.run(async () => {
            const order = this.pos.getOrder();
            const program = programFor(this.pos);
            const phone = normalizePhone(this.state.phone);
            if (this.state.name.trim().length < 3 || !/^\d{10}$/.test(phone) || this.state.reason.trim().length < 5 || !this.state.reviewed) {
                throw new Error("Escribe nombre, teléfono de 10 dígitos y motivo. Confirma la revisión física y que las piezas pueden volver a venderse.");
            }
            if (!program) throw new Error("No se cargó el programa Vales Leyka. Comprueba que su moneda coincide con el POS y vuelve a abrir el punto de venta.");
            if (order.finalized || order.payment_ids.length || order.lines.some(isValeLine) || !order.lines.length || order.lines.some((l) => !l.refunded_orderline_id || l.qty >= 0 || l.is_reward_line) || this.refundAmount <= 0) {
                throw new Error("Prepara una devolución de productos de una sola venta, sin pagos ni otros artículos.");
            }
            const source = order.lines[0].refunded_orderline_id.order_id;
            if (order.lines.some((l) => l.refunded_orderline_id.order_id.id !== source.id)) throw new Error("Selecciona productos de una sola venta.");
            if (source.lines.some((l) => l.is_reward_line)) throw new Error("Esta venta utilizó promociones o vales. Esta primera versión requiere revisión del importe neto por el encargado y no emitirá un vale automáticamente.");
            await this.pos.data.call("pos.config", "read", [[this.pos.config.id], ["id"]]);
            const amount = this.refundAmount;
            const previous = orderFields(order);
            Object.assign(order, {
                x_leyka_vale_holder: this.state.name.trim(), x_leyka_vale_phone: phone,
                x_leyka_vale_reason: this.state.reason.trim(), x_leyka_vale_reviewed: true,
                x_leyka_vale_code: order.x_leyka_vale_code || randomValeCode(),
            });
            const product = program.trigger_product_ids.find((v) => v.default_code === SKU);
            let line;
            try {
                line = await this.pos.addLineToCurrentOrder({ product_id: product, price_unit: amount }, {
                    price_unit: amount, merge: false, giftBarcode: order.x_leyka_vale_code,
                }, false);
                if (!line) throw new Error("No se pudo agregar el vale. No se ha emitido ningún saldo.");
                line.gift_code = order.x_leyka_vale_code;
                order.is_refund = false;
                await this.pos.updatePrograms();
                if (Math.abs(order.priceIncl) > 0.01) throw new Error("El total debe quedar en cero. Revisa los impuestos del producto Vale Leyka.");
            } catch (error) {
                if (line) order.removeOrderline(line);
                Object.assign(order, previous);
                order.is_refund = true;
                throw error;
            }
            this.props.close();
            this.pos.navigate("PaymentScreen", { orderUuid: order.uuid });
            this.pos.notification.add("Total cero: pulsa Validar para emitir el vale. No selecciones efectivo ni terminal.", { type: "info" });
        });
    }
    async search() {
        await this.run(async () => {
            const q = this.state.query.trim();
            if (q.length < 3) throw new Error("Escribe al menos tres caracteres del nombre, el teléfono o el código completo.");
            const program = programFor(this.pos);
            if (!program) throw new Error("El programa Vales Leyka no está cargado en este POS.");
            const phone = normalizePhone(q);
            const filter = ["|", "|", ["code", "=ilike", q], ["x_leyka_vale_holder", "ilike", q], ["x_leyka_vale_phone", "=", phone]];
            this.state.rows = await this.pos.data.call("loyalty.card", "search_read", [[ ["program_id", "=", program.id], ...filter ], CARD_FIELDS], { limit: 25, order: "id desc" });
            // Paid refunds without a card can be recovered after a network interruption.
            const orders = await this.pos.data.call("pos.order", "search_read", [[
                ["company_id", "=", this.pos.company.id], ["state", "in", ["paid", "done", "invoiced"]],
                ["x_leyka_vale_code", "!=", false], "|", "|",
                ["x_leyka_vale_code", "=ilike", q], ["x_leyka_vale_holder", "ilike", q], ["x_leyka_vale_phone", "=", phone],
            ], ["id", "x_leyka_vale_holder", "x_leyka_vale_phone", "x_leyka_vale_code"]], { limit: 25, order: "id desc" });
            const existing = new Set(this.state.rows.map((c) => c.source_pos_order_id[0]));
            this.state.pending = orders.filter((o) => !existing.has(o.id));
            this.state.searched = true;
        });
    }
    async redeem(card) {
        await this.run(async () => {
            const order = this.pos.getOrder();
            if (order.finalized || order.priceIncl <= 0 || order.lines.some((l) => l.qty < 0 || isValeLine(l))) throw new Error("Agrega los productos de la nueva compra antes de canjear el vale.");
            const result = await this.pos.activateCode(card.code);
            if (typeof result === "string") throw new Error(result);
            this.props.close();
            this.pos.notification.add("Vale aplicado. Cobra la diferencia por el método habitual; el saldo que no se use permanece en el vale.", { type: "success" });
        });
    }
    async reprint(card) {
        await this.run(async () => {
            const result = await this.pos.printer.print(ValeReceipt, { card, amount: card.points, reprint: true }, this.pos.printOptions);
            if (!result) throw new Error("La impresión no se completó. Puedes intentar reimprimir: no se creará otro vale.");
        });
    }
    async recover(order) {
        await this.run(async () => { await this.pos.leykaEnsureVale(order.id); });
        if (!this.state.error) await this.search();
    }
}

patch(ControlButtons.prototype, {
    clickLeykaVales() {
        this.props.close?.();
        this.pos.dialog.add(ValesDialog, {});
    },
});
patch(TicketScreen.prototype, {
    async onDoRefund() {
        const flow = this.pos._leykaValeFlow;
        await super.onDoRefund(...arguments);
        const order = this.pos.getOrder();
        if (flow && order.priceIncl < 0 && order.lines.some((l) => l.refunded_orderline_id)) {
            order.x_leyka_vale_pending = true;
            this.pos._leykaValeFlow = false;
            this.pos.navigate("ProductScreen", { orderUuid: order.uuid });
            this.pos.dialog.add(ValesDialog, { mode: "issue" });
        }
    },
});
patch(PosStore.prototype, {
    async leykaEnsureVale(orderId) {
        const program = programFor(this);
        const [order] = await this.data.call("pos.order", "read", [[orderId], ["state", "x_leyka_vale_code"]]);
        if (!order?.x_leyka_vale_code || !["paid", "done", "invoiced"].includes(order.state)) throw new Error("La devolución aún no está validada en Odoo.");
        const domain = [["program_id", "=", program.id], ["source_pos_order_id", "=", orderId]];
        let cards = await this.data.call("loyalty.card", "search_read", [domain, CARD_FIELDS]);
        if (!cards.length) {
            const lines = await this.data.call("pos.order.line", "search_read", [[
                ["order_id", "=", orderId], ["product_id.default_code", "=", SKU],
            ], ["price_subtotal_incl"]]);
            if (lines.length !== 1) throw new Error("No se encontró una emisión válida para recuperar.");
            const amount = lines[0].price_subtotal_incl;
            await this.data.call("pos.order", "confirm_coupon_programs", [orderId, {
                "-1": { program_id: program.id, points: amount, points_earned: amount, points_spent: 0,
                    code: order.x_leyka_vale_code, expiration_date: false },
            }]);
            cards = await this.data.call("loyalty.card", "search_read", [domain, CARD_FIELDS]);
        }
        if (cards.length !== 1) throw new Error("No se pudo confirmar el vale. Busca la devolución antes de intentar otra emisión.");
        return cards[0];
    },
    async postProcessLoyalty(order) {
        if (order.x_leyka_vale_code) {
            const program = programFor(this);
            for (const change of Object.values(order.uiState.couponPointChanges || {})) {
                if (change.program_id === program?.id) {
                    change.expiration_date = false;
                    change.code = order.x_leyka_vale_code;
                    change.barcode = order.x_leyka_vale_code;
                }
            }
        }
        const result = await super.postProcessLoyalty(...arguments);
        if (order.x_leyka_vale_code) order.uiState.leykaValeReceipt = await this.leykaEnsureVale(order.id);
        return result;
    },
    async printReceipt(options = {}) {
        const order = options.order || this.getOrder();
        if (order.x_leyka_vale_code) {
            try { order.uiState.leykaValeReceipt = await this.leykaEnsureVale(order.id); }
            catch (error) { inform(this, "No se imprimió un código sin confirmar. " + (error?.data?.message || error.message)); return false; }
        }
        return super.printReceipt(...arguments);
    },
});
patch(OrderPaymentValidation.prototype, {
    get canPrintReceipt() {
        return this.order.x_leyka_vale_code ? this.order.nb_print === 0 && this.order.isSynced : super.canPrintReceipt;
    },
    async validateOrder() {
        const order = this.order;
        const program = programFor(this.pos);
        const gift = order.lines.filter(isValeLine);
        const redeeming = order.lines.some((l) => l.reward_id?.program_id?.id === program?.id);
        if (gift.length || order.x_leyka_vale_code || order.x_leyka_vale_pending || redeeming) {
            try {
                await this.pos.data.call("pos.config", "read", [[this.pos.config.id], ["id"]]);
                if (gift.length || order.x_leyka_vale_code || order.x_leyka_vale_pending) {
                    if (gift.length !== 1 || !order.x_leyka_vale_reviewed || !order.x_leyka_vale_code || Math.abs(order.priceIncl) > 0.01 || order.payment_ids.some((p) => Math.abs(p.amount) > 0.001)) {
                        throw new Error("Emite el vale desde ⋮ → Cambios / vales. El total debe quedar en cero, sin reembolso de efectivo o terminal.");
                    }
                    for (const p of order.payment_ids.slice()) order.removePaymentline(p);
                }
                if (redeeming) {
                    const changes = {};
                    for (const line of order.lines.filter((l) => l.reward_id?.program_id?.id === program.id)) changes[line.coupon_id.id] = (changes[line.coupon_id.id] || 0) - line.points_cost;
                    const check = await this.pos.data.call("pos.order", "validate_coupon_programs", [[], changes, []]);
                    if (!check.successful) throw new Error(check.payload.message);
                }
            } catch (error) { inform(this.pos, error?.data?.message || error.message); return false; }
        }
        return super.validateOrder(...arguments);
    },
});
