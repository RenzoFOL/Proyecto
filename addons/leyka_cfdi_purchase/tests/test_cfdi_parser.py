from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from psycopg2 import IntegrityError
from odoo.tools import mute_logger
from ..models.cfdi_purchase import _decimal


CFDI = b"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
 xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
 Version="4.0" Fecha="2026-09-12T12:30:00" SubTotal="100.00"
 Total="116.00" Moneda="MXN" TipoDeComprobante="I">
 <cfdi:Emisor Rfc="AAA010101AAA" Nombre="PROVEEDOR PRUEBA" RegimenFiscal="601"/>
 <cfdi:Receptor Rfc="XAXX010101000" Nombre="LEYKA PRUEBA" UsoCFDI="G03"
  DomicilioFiscalReceptor="00000" RegimenFiscalReceptor="612"/>
 <cfdi:Conceptos>
  <cfdi:Concepto ClaveProdServ="26111700" NoIdentificacion="SKU-1"
   Cantidad="1" ClaveUnidad="H87" Descripcion="Producto" ValorUnitario="100.00"
   Importe="100.00" ObjetoImp="02">
   <cfdi:Impuestos><cfdi:Traslados>
    <cfdi:Traslado Base="100.00" Impuesto="002" TipoFactor="Tasa"
     TasaOCuota="0.160000" Importe="16.00"/>
   </cfdi:Traslados></cfdi:Impuestos>
  </cfdi:Concepto>
 </cfdi:Conceptos>
 <cfdi:Impuestos TotalImpuestosTrasladados="16.00"/>
 <cfdi:Complemento>
  <tfd:TimbreFiscalDigital UUID="11111111-2222-3333-4444-555555555555"/>
 </cfdi:Complemento>
</cfdi:Comprobante>
"""


class TestCfdiParser(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("base.MXN").active = True

    def test_secure_parse_extracts_purchase_data(self):
        self.env.company.vat = "XAXX010101000"
        values = self.env["leyka.cfdi.purchase"].parse_xml_payload(
            CFDI,
            "prueba.xml",
        )
        self.assertEqual(values["uuid"], "11111111-2222-3333-4444-555555555555")
        self.assertEqual(values["issuer_rfc"], "AAA010101AAA")
        self.assertEqual(values["receiver_rfc"], "XAXX010101000")
        self.assertEqual(values["total"], 116.0)
        self.assertEqual(values["line_ids"][0][2]["tax_rate"], 16.0)

    def test_rejects_doctype(self):
        xml = CFDI.replace(b'<cfdi:Comprobante', b'<!DOCTYPE Comprobante [<!ENTITY sample "x">]><cfdi:Comprobante', 1)
        with self.assertRaises(ValidationError):
            self.env["leyka.cfdi.purchase"].parse_xml_payload(xml, "dtd.xml")

    def test_rejects_non_finite_money(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaises(ValidationError):
                _decimal(value)

    def test_uuid_is_unique_in_database(self):
        model = self.env["leyka.cfdi.purchase"]
        model.import_xml_payload(CFDI, "original.xml")
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            model.import_xml_payload(CFDI, "duplicate.xml")
            model.flush_model()
