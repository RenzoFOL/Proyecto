# Leyka POS Cambios y Vales

Flujo integrado con el POS de Odoo 19 Community para la política local de Leyka Motors.

- Busca el ticket original y reconoce el precio realmente pagado, incluidos descuentos.
- Permite agregar en la misma orden los productos que el cliente llevará en el cambio.
- Cobra normalmente cuando el nuevo producto cuesta más.
- Emite un vale por la diferencia cuando el nuevo producto cuesta menos.
- No entrega efectivo desde el flujo local de cambios.
- Exige nombre y teléfono simplificados; el vale puede localizarse si se pierde el código.
- Imprime automáticamente código, QR, titular, teléfono y saldo del vale.
- Permite buscar un vale por código, nombre o teléfono y usarlo como pago parcial o total.
- Registra condición física y destino: venta, cuarentena, merma o garantía.
- Crea automáticamente ubicaciones internas separadas para cuarentena, dañados y garantía de proveedor.
- Después de la devolución, mueve los productos sin lote/serie a su ubicación de clasificación y deja trazabilidad del movimiento.
- Los productos con lote o número de serie quedan marcados para clasificación manual para evitar mover la unidad equivocada.
- Evita devolver más unidades de las compradas y aplica la política por categoría.
- Mantiene una relación auditable entre ticket original, orden de cambio y vale.

Antes de usarlo, abre la configuración del punto de venta y comprueba que **Cambios y vales Leyka** esté activo y que el producto técnico sea **Vale Leyka emitido**.

En esa misma configuración puedes cambiar las tres ubicaciones de clasificación. Si el movimiento de devolución todavía no se ha completado cuando termina el cobro, la solicitud queda **Pendiente** y Odoo vuelve a intentarlo automáticamente cada cinco minutos.

Para canjear saldos, crea o selecciona un método de pago contablemente apropiado, activa **Usar para vales Leyka** y agrégalo al POS. El módulo fiscal configurará después la cuenta de pasivo definitiva para que la emisión y el canje no se mezclen con efectivo o banco.

La cuenta contable definitiva del producto técnico se configurará en el módulo de conciliación/fiscal antes de producción.
