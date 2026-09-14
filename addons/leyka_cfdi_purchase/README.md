# Leyka Compras CFDI

Importa XML CFDI o lotes ZIP sin extraer archivos al sistema.

## Controles

- Rechaza entidades externas, DTD y acceso de red.
- Máximo 10 MB por XML, 50 MB por ZIP y 100 XML por lote.
- UUID único por compañía.
- Compara el RFC receptor con el RFC configurado en Odoo.
- Conserva el XML original como adjunto.
- Crea la factura de proveedor únicamente después de aprobación.
- Los productos no reconocidos quedan como «Compra CFDI por clasificar» para revisión.

La clasificación separa mercancía, equipo de oficina, terminales, servicios y gastos.
