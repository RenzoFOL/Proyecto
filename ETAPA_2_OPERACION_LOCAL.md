# Leyka: compras, inventario y control local

Esta etapa agrega tres módulos a los tres existentes. Mercado Libre y el sitio web permanecen al final. La instalación requiere Odoo 19 Community en el servidor Windows y los permisos de Compras, Inventario y Contabilidad para las tareas correspondientes.

## Dónde aparece

- Leyka Operación → CFDI de compras → Compra e inventario.
- Leyka Operación → Mi tienda: resumen (responsable de Contabilidad).
- Leyka Operación → Cambios y vales → Movimientos contables.
- Ajustes → Compañías → tu compañía → Vales Leyka (responsable de Contabilidad).

## Compras e inventario

1. Importa el XML y revisa el RFC, conceptos, IVA y total.
2. Asigna cada concepto a su producto Odoo. Para mercancía, debe tener seguimiento de inventario. Las cantidades XML se interpretan en la unidad del producto: verifica cajas, paquetes y piezas antes de aprobar.
3. Aprueba el documento y pulsa Crear / abrir compra. Se crea una solicitud de presupuesto en borrador, no una recepción confirmada.
4. Revisa y confirma la compra desde Odoo. Odoo crea la recepción correspondiente.
5. Al recibir, captura solo las cantidades que llegaron y valida la recepción. Odoo conserva pendientes los faltantes mediante entregas parciales.
6. Crea la factura desde el XML o la compra: ambos botones apuntan al mismo documento. La factura queda en borrador, vinculada a las líneas de compra. No se publica ni paga automáticamente.
7. Para una nota de crédito, indica descuento/ajuste de precio o devolución física. Relaciona el XML original. Si hay devolución, abre la recepción original y usa la acción estándar Devolver, revisa las cantidades y valida el traslado. La nota de crédito no retira inventario automáticamente.

Si una factura ya se creó antes de instalar esta etapa, no se crea otra compra automáticamente: se requiere vincular la compra existente desde Contabilidad. No hay conversión automática de unidades SAT ni importación de XML con retenciones o múltiples impuestos.

## Contabilidad de vales

Antes de cerrar sesiones con vales, asigna una cuenta de pasivo circulante exclusiva a la compañía. La cuenta debe pertenecer a esa compañía. La selección del código de cuenta corresponde a tu catálogo contable.

Configura un método POS exclusivo de vales: Usar para vales Leyka activado, diario de tipo Banco, sin terminal y sin Identificar cliente. El diario permite que Odoo muestre el método en su flujo de pago; este módulo sustituye la creación de pagos bancarios por el débito directo al pasivo. No reasignes el método Mercado Pago o Stori para usarlo como vale.

Al emitir $100: la devolución de mercancía se registra por sus líneas e impuestos; el producto técnico acredita $100 al pasivo de vales. Al canjear $40: el cierre debita $40 de ese pasivo; quedan $60 pendientes. El producto técnico de vales debe estar sin impuestos. El tratamiento fiscal final de los documentos requiere revisión aparte.

Los movimientos manuales que alteran saldo (emisión fuera del POS, cancelación, ajuste) permiten preparar un asiento en borrador. Necesitan un diario general con cuenta de contrapartida: revisa la cuenta, motivo y fecha antes de publicarlo. Reponer un código no altera el saldo total ni genera otro asiento. Los movimientos provenientes del POS no generan un segundo asiento manual.

Las sesiones históricas ya cerradas no se reescriben. El saldo previo a la instalación debe conciliarse mediante un asiento de apertura revisado. No cambies de cuenta de pasivo a mitad de la operación sin reclasificar su saldo.

## Mi tienda: resumen

Elige fechas, compañía y zona horaria y pulsa Actualizar resumen. El reporte consulta tickets pagados, finalizados o facturados, sin volver a sumar sus facturas. Separa ventas positivas, devoluciones, venta neta sin impuestos, impuestos registrados, costos guardados por Odoo, cobros y canjes. Si hay costos pendientes, no muestra utilidad bruta. Si hay costo cero, lo señala para revisión.

Compras incluye facturas y notas de crédito contabilizadas por fecha de factura. No significa IVA acreditable ni flujo de efectivo. Los documentos en borrador y las recepciones pendientes se muestran por separado. El saldo de vales se compara con el pasivo contabilizado a la fecha de corte; las sesiones abiertas y ajustes pendientes pueden explicar diferencias.

El costo utilizado debe estar correctamente configurado en Odoo. No se resta IVA automáticamente de un costo cargado con impuestos ni se reemplaza el costo histórico por el costo actual del catálogo.

## Validación requerida antes de caja real

- XML de mercancía → compra → recepción parcial → recepción restante → una sola factura.
- Venta $100 → cambio/vale $100 → uso de $40 → cierre con pasivo restante $60.
- Canje con factura de cliente: factura saldada y sin depósito bancario ficticio.
- Resumen sin duplicar facturas POS ni sumar el producto técnico como venta.
- Prueba visual de cambios/vale y comprobación en la impresora física.

Las pruebas automatizadas se ejecutan en GitHub Actions con Odoo 19 Community y PostgreSQL, y el instalador se compila y prueba en Windows. Consulta el resultado del commit que acompañe la descarga.

## Pendiente tras esta etapa

Conciliación de depósitos/comisiones Mercado Pago y captura Stori; perfil fiscal y cálculo revisable de IVA/ISR; editor del ticket; diseño del POS; compatibilidad de refacciones; Mercado Libre y web al final.

## Referencias técnicas verificadas

- [Órdenes de compra Odoo 19](https://github.com/odoo/odoo/blob/19.0/addons/purchase/models/purchase_order.py)
- [Líneas de compra y unidades Odoo 19](https://github.com/odoo/odoo/blob/19.0/addons/purchase/models/purchase_order_line.py)
- [Cierre contable POS Odoo 19](https://github.com/odoo/odoo/blob/19.0/addons/point_of_sale/models/pos_session.py)
- [Pagos POS y conciliación de facturas](https://github.com/odoo/odoo/blob/19.0/addons/point_of_sale/models/pos_payment.py)
