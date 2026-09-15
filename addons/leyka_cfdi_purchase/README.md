# Leyka Compras CFDI

Importa XML CFDI o lotes ZIP sin extraer archivos al sistema.

## Controles

- Rechaza entidades externas, DTD y acceso de red.
- Máximo 10 MB por XML, 50 MB por ZIP y 100 XML por lote.
- UUID único por compañía.
- Compara el RFC receptor con el RFC configurado en Odoo.
- Conserva el XML original como adjunto.
- Crea la factura de proveedor únicamente después de aprobación.
- Los CFDI de egreso generan una nota de crédito de proveedor en borrador.
- Bloquea la creación si falta un impuesto o el total calculado no coincide con el XML.
- Los documentos con retenciones, cuotas o múltiples traslados por concepto requieren revisión y mapeo contable; se conserva el XML sin crear un asiento incompleto.
- Los productos no reconocidos quedan como «Compra CFDI por clasificar» para revisión.

La clasificación separa mercancía, equipo de oficina, terminales, servicios y gastos.
