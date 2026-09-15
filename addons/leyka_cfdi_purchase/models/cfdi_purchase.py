import base64
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from lxml import etree

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


MAX_XML_SIZE = 10 * 1024 * 1024


def _normalized_rfc(value):
    return re.sub(r"[^A-Z0-9&Ñ]", "", (value or "").upper())


def _decimal(value, default="0"):
    try:
        number = Decimal(value or default)
        if not number.is_finite():
            raise InvalidOperation
        return number
    except InvalidOperation as error:
        raise ValidationError(_("El CFDI contiene un importe inválido: %s") % value) from error


def _first(node, xpath):
    records = node.xpath(xpath)
    return records[0] if records else None


class LeykaCfdiPurchase(models.Model):
    _name = "leyka.cfdi.purchase"
    _description = "CFDI de compra Leyka"
    _order = "invoice_date desc, id desc"
    _rec_name = "display_reference"

    display_reference = fields.Char(
        compute="_compute_display_reference",
        store=True,
        index=True,
    )
    uuid = fields.Char(string="UUID", required=True, copy=False, index=True)
    version = fields.Char()
    series = fields.Char(string="Serie")
    folio = fields.Char()
    invoice_date = fields.Datetime(string="Fecha CFDI", required=True)
    document_type = fields.Selection(
        [
            ("I", "Ingreso"),
            ("E", "Egreso"),
            ("P", "Pago"),
            ("T", "Traslado"),
            ("N", "Nómina"),
        ],
        string="Tipo",
        required=True,
    )
    currency_name = fields.Char(string="Moneda")
    subtotal = fields.Monetary(required=True)
    discount = fields.Monetary()
    tax_transferred = fields.Monetary(string="Impuestos trasladados")
    tax_withheld = fields.Monetary(string="Impuestos retenidos")
    total = fields.Monetary(required=True)
    issuer_rfc = fields.Char(string="RFC emisor", required=True, index=True)
    issuer_name = fields.Char(string="Emisor")
    issuer_tax_regime = fields.Char(string="Régimen emisor")
    receiver_rfc = fields.Char(string="RFC receptor", required=True, index=True)
    receiver_name = fields.Char(string="Receptor")
    receiver_cfdi_use = fields.Char(string="Uso CFDI")
    receiver_tax_regime = fields.Char(string="Régimen receptor")
    payment_method = fields.Char(string="Método de pago")
    payment_form = fields.Char(string="Forma de pago")
    expedition_place = fields.Char(string="Lugar de expedición")
    classification = fields.Selection(
        [
            ("merchandise", "Mercancía para venta"),
            ("office_equipment", "Equipo de oficina"),
            ("terminal_fee", "Uso/comisión de terminal"),
            ("service", "Servicio"),
            ("expense", "Gasto operativo"),
            ("other", "Por clasificar"),
        ],
        required=True,
        default="other",
        index=True,
    )
    state = fields.Selection(
        [
            ("review", "Por revisar"),
            ("approved", "Aprobado"),
            ("billed", "Factura creada"),
            ("rejected", "Rechazado"),
        ],
        default="review",
        required=True,
        copy=False,
        index=True,
    )
    review_note = fields.Text(string="Observaciones")
    file_name = fields.Char(required=True)
    xml_file = fields.Binary(
        string="XML original",
        attachment=True,
        required=True,
        copy=False,
    )
    line_ids = fields.One2many(
        "leyka.cfdi.purchase.line",
        "cfdi_id",
        string="Conceptos",
        copy=False,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    company_currency_id = fields.Many2one(
        related="company_id.currency_id",
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    vendor_bill_id = fields.Many2one(
        "account.move",
        string="Factura de proveedor",
        readonly=True,
        copy=False,
        ondelete="set null",
    )

    _uuid_company_uniq = models.Constraint(
        "unique(uuid, company_id)", "Este UUID ya fue importado para la compañía."
    )

    @api.depends("issuer_name", "series", "folio", "uuid")
    def _compute_display_reference(self):
        for cfdi in self:
            number = "".join(filter(None, [cfdi.series, cfdi.folio]))
            cfdi.display_reference = " - ".join(
                filter(None, [number or cfdi.uuid, cfdi.issuer_name])
            )

    @api.model
    def parse_xml_payload(self, payload, file_name):
        if not payload:
            raise ValidationError(_("El archivo XML está vacío."))
        if len(payload) > MAX_XML_SIZE:
            raise ValidationError(_("El XML supera el límite de 10 MB."))
        parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
            huge_tree=False,
            recover=False,
            remove_comments=False,
        )
        try:
            root = etree.fromstring(payload, parser=parser)
        except (etree.XMLSyntaxError, ValueError) as error:
            raise ValidationError(_("XML inválido: %s") % error) from error
        if root.getroottree().docinfo.doctype:
            raise ValidationError(_("No se permiten DTD ni entidades en un CFDI."))
        if etree.QName(root).localname != "Comprobante":
            raise ValidationError(_("El archivo no es un comprobante CFDI."))

        issuer = _first(root, "./*[local-name()='Emisor']")
        receiver = _first(root, "./*[local-name()='Receptor']")
        stamp = _first(
            root,
            ".//*[local-name()='Complemento']/*[local-name()='TimbreFiscalDigital']",
        )
        taxes = _first(root, "./*[local-name()='Impuestos']")
        if issuer is None or receiver is None or stamp is None:
            raise ValidationError(
                _("El CFDI no contiene Emisor, Receptor o Timbre Fiscal Digital.")
            )

        currency_code = root.get("Moneda") or self.env.company.currency_id.name
        currency = self.env["res.currency"].search(
            [("name", "=", currency_code)],
            limit=1,
        )
        if not currency:
            raise ValidationError(_("Activa y configura la moneda %s antes de importar.") % currency_code)

        line_commands = []
        for concept in root.xpath(
            "./*[local-name()='Conceptos']/*[local-name()='Concepto']"
        ):
            transferred = _first(
                concept,
                "./*[local-name()='Impuestos']/*[local-name()='Traslados']/*[local-name()='Traslado']",
            )
            tax_rate = Decimal("0")
            tax_object = concept.get("ObjetoImp")
            if transferred is not None and transferred.get("TipoFactor") == "Tasa":
                tax_rate = _decimal(transferred.get("TasaOCuota")) * Decimal("100")
            line_commands.append(
                (
                    0,
                    0,
                    {
                        "sat_product_code": concept.get("ClaveProdServ"),
                        "identification": concept.get("NoIdentificacion"),
                        "description": concept.get("Descripcion") or _("Sin descripción"),
                        "quantity": float(_decimal(concept.get("Cantidad"), "1")),
                        "sat_unit_code": concept.get("ClaveUnidad"),
                        "unit_name": concept.get("Unidad"),
                        "unit_price": float(_decimal(concept.get("ValorUnitario"))),
                        "line_subtotal": float(_decimal(concept.get("Importe"))),
                        "discount": float(_decimal(concept.get("Descuento"))),
                        "tax_object": tax_object,
                        "tax_rate": float(tax_rate),
                    },
                )
            )

        company_rfc = _normalized_rfc(self.env.company.vat)
        receiver_rfc = _normalized_rfc(receiver.get("Rfc"))
        notes = []
        if not company_rfc:
            notes.append(_("La compañía aún no tiene RFC configurado; verifica el receptor."))
        elif company_rfc != receiver_rfc:
            notes.append(
                _("ALERTA: el RFC receptor %(receiver)s no coincide con la compañía %(company)s.")
                % {"receiver": receiver_rfc, "company": company_rfc}
            )

        values = {
            "uuid": (stamp.get("UUID") or "").upper(),
            "version": root.get("Version"),
            "series": root.get("Serie"),
            "folio": root.get("Folio"),
            "invoice_date": datetime.fromisoformat(root.get("Fecha")),
            "document_type": root.get("TipoDeComprobante"),
            "currency_name": currency_code,
            "currency_id": currency.id,
            "subtotal": float(_decimal(root.get("SubTotal"))),
            "discount": float(_decimal(root.get("Descuento"))),
            "total": float(_decimal(root.get("Total"))),
            "tax_transferred": float(
                _decimal(taxes.get("TotalImpuestosTrasladados"))
                if taxes is not None
                else Decimal("0")
            ),
            "tax_withheld": float(
                _decimal(taxes.get("TotalImpuestosRetenidos"))
                if taxes is not None
                else Decimal("0")
            ),
            "issuer_rfc": _normalized_rfc(issuer.get("Rfc")),
            "issuer_name": issuer.get("Nombre"),
            "issuer_tax_regime": issuer.get("RegimenFiscal"),
            "receiver_rfc": receiver_rfc,
            "receiver_name": receiver.get("Nombre"),
            "receiver_cfdi_use": receiver.get("UsoCFDI"),
            "receiver_tax_regime": receiver.get("RegimenFiscalReceptor"),
            "payment_method": root.get("MetodoPago"),
            "payment_form": root.get("FormaPago"),
            "expedition_place": root.get("LugarExpedicion"),
            "file_name": file_name,
            "xml_file": base64.b64encode(payload),
            "line_ids": line_commands,
            "review_note": "\n".join(notes),
            "company_id": self.env.company.id,
        }
        if not values["uuid"]:
            raise ValidationError(_("El CFDI no contiene UUID."))
        if not values["line_ids"]:
            raise ValidationError(_("El CFDI no contiene conceptos."))
        return values

    @api.model
    def import_xml_payload(self, payload, file_name):
        return self.create(self.parse_xml_payload(payload, file_name))

    def action_approve(self):
        if not self.env.user.has_group("leyka_local_core.group_leyka_manager"):
            raise AccessError(_("Solo un responsable puede aprobar CFDI."))
        for cfdi in self:
            company_rfc = _normalized_rfc(cfdi.company_id.vat)
            if company_rfc and cfdi.receiver_rfc != company_rfc:
                raise ValidationError(
                    _("El RFC receptor no coincide con el RFC de la compañía.")
                )
            if cfdi.document_type not in {"I", "E"}:
                raise ValidationError(
                    _("Solo los CFDI de ingreso o egreso entran a compras.")
                )
            cfdi.state = "approved"

    def _find_or_create_supplier(self):
        self.ensure_one()
        supplier = self.env["res.partner"].search(
            [("vat", "=ilike", self.issuer_rfc)],
            limit=1,
        )
        if supplier:
            supplier.supplier_rank = max(supplier.supplier_rank, 1)
            return supplier
        return self.env["res.partner"].create(
            {
                "name": self.issuer_name or self.issuer_rfc,
                "vat": self.issuer_rfc,
                "company_type": "company",
                "supplier_rank": 1,
                "country_id": self.env.ref("base.mx").id,
            }
        )

    def _generic_purchase_product(self):
        product = self.env["product.product"].search(
            [("default_code", "=", "LEYKA-CFDI-UNMATCHED")],
            limit=1,
        )
        if product:
            return product
        template = self.env["product.template"].create(
            {
                "name": _("Compra CFDI por clasificar"),
                "default_code": "LEYKA-CFDI-UNMATCHED",
                "type": "service",
                "purchase_ok": True,
                "sale_ok": False,
            }
        )
        return template.product_variant_id

    def action_create_vendor_bill(self):
        with self.env.cr.savepoint():
            return self._create_checked_vendor_bill()

    def _create_checked_vendor_bill(self):
        self.ensure_one()
        self.check_access("write")
        self.env.cr.execute("SELECT id FROM leyka_cfdi_purchase WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset(["state", "vendor_bill_id"])
        if self.state != "approved":
            raise UserError(_("Aprueba el CFDI antes de crear la factura."))
        if self.vendor_bill_id:
            raise UserError(_("Este CFDI ya tiene una factura vinculada."))
        if self.document_type not in ("I", "E"):
            raise UserError(
                _("Solo se puede crear factura o nota de crédito de proveedor con CFDI de ingreso o egreso.")
            )
        if self.tax_withheld:
            raise UserError(_("Este CFDI contiene retenciones. Requiere configurar sus impuestos antes de crear la factura."))
        parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
        root = etree.fromstring(base64.b64decode(self.xml_file), parser)
        for concept in root.xpath("./*[local-name()='Conceptos']/*[local-name()='Concepto']"):
            taxes = concept.xpath("./*[local-name()='Impuestos']/*[local-name()='Traslados']/*")
            if len(taxes) > 1 or any(tax.get("Impuesto") != "002" or tax.get("TipoFactor") == "Cuota" for tax in taxes):
                raise UserError(_("El CFDI tiene impuestos adicionales al IVA simple. Requiere revisión contable."))
        supplier = self._find_or_create_supplier()
        generic_product = self._generic_purchase_product()
        invoice_lines = []
        for line in self.line_ids:
            product = line.product_id
            if not product and line.identification:
                product = self.env["product.product"].search(
                    [
                        "|",
                        ("default_code", "=", line.identification),
                        ("barcode", "=", line.identification),
                    ],
                    limit=1,
                )
            product = product or generic_product
            tax = self.env["account.tax"].search(
                [
                    ("company_id", "=", self.company_id.id),
                    ("type_tax_use", "=", "purchase"),
                    ("amount", "=", line.tax_rate),
                    ("amount_type", "=", "percent"),
                    ("price_include", "=", False),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if line.tax_rate and not tax:
                raise UserError(_("Configura un impuesto de compra del %s%%, excluido del precio.") % line.tax_rate)
            discount_percent = (
                (line.discount / line.line_subtotal) * 100
                if line.line_subtotal
                else 0.0
            )
            invoice_lines.append((0, 0, self._prepare_leyka_bill_line(
                line, product, tax, discount_percent
            )))
        bill = self.env["account.move"].create(
            {
                "move_type": "in_refund" if self.document_type == "E" else "in_invoice",
                "partner_id": supplier.id,
                "invoice_date": fields.Date.to_date(self.invoice_date),
                "ref": self.uuid,
                "currency_id": self.currency_id.id,
                "company_id": self.company_id.id,
                "invoice_line_ids": invoice_lines,
            }
        )
        if not self.currency_id.is_zero(bill.amount_total - self.total):
            raise ValidationError(_("El total calculado por Odoo no coincide con el XML. Revisa productos, descuentos e impuestos."))
        self.write({"vendor_bill_id": bill.id, "state": "billed"})
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": bill.id,
            "view_mode": "form",
            "target": "current",
        }

    def _prepare_leyka_bill_line(self, line, product, tax, discount_percent):
        return {
            "product_id": product.id,
            "name": line.description,
            "quantity": line.quantity,
            "price_unit": line.unit_price,
            "discount": discount_percent,
            "tax_ids": [(6, 0, tax.ids)],
        }


class LeykaCfdiPurchaseLine(models.Model):
    _name = "leyka.cfdi.purchase.line"
    _description = "Concepto CFDI de compra"
    _order = "id"

    cfdi_id = fields.Many2one(
        "leyka.cfdi.purchase",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sat_product_code = fields.Char(string="Clave SAT")
    identification = fields.Char(string="SKU/identificación", index=True)
    description = fields.Char(required=True)
    quantity = fields.Float(required=True)
    sat_unit_code = fields.Char(string="Clave unidad SAT")
    unit_name = fields.Char(string="Unidad")
    unit_price = fields.Monetary(required=True)
    line_subtotal = fields.Monetary(required=True)
    discount = fields.Monetary()
    tax_object = fields.Char(string="Objeto de impuesto")
    tax_rate = fields.Float(string="Tasa IVA %")
    product_id = fields.Many2one(
        "product.product",
        string="Producto Odoo",
        ondelete="set null",
        help="Confirma o asigna el producto antes de crear la factura.",
    )
    currency_id = fields.Many2one(
        related="cfdi_id.currency_id",
        store=True,
        readonly=True,
    )
