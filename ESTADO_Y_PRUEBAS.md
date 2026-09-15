> Actualización: ver ETAPA_2_OPERACION_LOCAL.md para los tres módulos nuevos de compras/inventario, contabilidad de vales y resumen. Los límites de esta primera etapa que se detallan abajo corresponden a la entrega anterior.

# Leyka · entrega de desarrollo 19.0.3

## Incluido

- Base local: titular simplificado por nombre/teléfono, vales, movimientos y reposición de códigos.
- Cambios POS: búsqueda de venta original, cambio inmediato, cobro de diferencia, vale por sobrante y búsqueda/canje por código/nombre/teléfono.
- Emisión y canje en la misma transacción de base de datos que la venta. Una falla de saldo revierte el guardado de esa venta.
- Recibo de vale con código, QR, titular y teléfono. Los datos quedan guardados para reimpresión.
- Clasificación de devolución sin lote/serie hacia ubicaciones de cuarentena, dañado o garantía. Los productos con seguimiento requieren clasificación manual.
- Compras XML CFDI: importación individual/lote, detección de UUID repetido, cotejo de RFC, clasificación y factura o nota de crédito de proveedor en borrador tras revisión. Se bloquean totales inconsistentes e impuestos aún sin mapear.
- Instalador Windows: copia de archivos con respaldo y restauración ante errores. No modifica base de datos, credenciales ni servicios.

## Antes de la prueba en tu Odoo

1. Usa una copia de la base de datos y respáldala.
2. Detén Odoo, ejecuta el instalador y elige una carpeta incluida en `addons_path`. También puedes extraer el ZIP en esa carpeta.
3. Reinicia Odoo. En modo desarrollador, actualiza la lista de aplicaciones y quita el filtro «Aplicaciones» al buscar módulos técnicos.
4. Instala o actualiza, en este orden: `leyka_local_core`, `leyka_pos_exchange`, `leyka_cfdi_purchase`.
5. Asigna al responsable el grupo «Operación Leyka / Responsable». Revisa la política de cada categoría.
6. En el POS, verifica el producto «Vale Leyka emitido», las tres ubicaciones y un método exclusivo de pago con «Usar para vales Leyka». No conviertas tu método Mercado Pago o efectivo en el método de vales.
7. Recarga por completo el POS después de actualizar.

Los módulos contienen Python y requieren instalación en el servidor. La opción «Importar módulo» de la interfaz puede no aceptar este tipo de paquete; el instalador coloca los archivos en la carpeta del servidor.

## Prueba de aceptación

- Venta de $100 → cambio por $120: cobra $20 con los pagos normales.
- Venta de $100 → cambio por $80: crea un vale de $20 con nombre/teléfono.
- Venta de $100 → vale: imprime un código con $100.
- Busca ese vale por teléfono, paga $40 y verifica saldo $60.
- Reintenta la sincronización/reimpresión: verifica que no se duplique el vale ni el canje.
- Clasifica una pieza como dañada: verifica una sola transferencia a «Leyka - Dañados y merma».
- Importa dos veces el mismo XML: la segunda importación debe quedar bloqueada.
- Comprueba el recibo real con Leyka Direct Print y la térmica POS-5890A-L.

## Validación y límites

Se ejecutan pruebas de instalación y negocio en Odoo 19 Community con PostgreSQL. El instalador tiene pruebas de respaldo, rechazo de rutas fuera del paquete y recuperación ante fallo; la compilación Windows ejecuta además una instalación temporal del EXE.

Queda pendiente validar visualmente el POS y la impresora física del usuario. El cierre contable de vales aún requiere configurar las cuentas apropiadas del producto de emisión y del método de pago; no debe usarse en caja real hasta verificar esa conciliación. Esta entrega no es el módulo SAT ni una declaración de impuestos.

## Próximas etapas acordadas

1. Completar y probar cierre contable de vales, compras/recepciones y conciliación local.
2. Perfil fiscal con RFC/razón social/régimen, IVA y estimaciones ISR fundamentadas en normativa vigente, con desglose verificable y revisión contable.
3. Comisiones, depósitos y devoluciones de Mercado Pago; registro manual flexible para Stori Tap.
4. Editor del ticket y personalización del catálogo POS.
5. Mercado Libre y sitio web con servidor/dominio, al final.

La integración Mercado Pago Orders API, el túnel de webhooks y Leyka Direct Print ya usados en la tienda son componentes externos a estos tres módulos y deben conservarse.
