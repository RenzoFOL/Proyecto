# Leyka POS Cambios y Vales

Flujo integrado con el POS de Odoo 19 Community para la política local de Leyka Motors.

- Busca el ticket original y reconoce el precio realmente pagado, incluidos descuentos.
- Permite agregar en la misma orden los productos que el cliente llevará en el cambio.
- Cobra normalmente cuando el nuevo producto cuesta más.
- Emite un vale por la diferencia cuando el nuevo producto cuesta menos.
- No entrega efectivo desde el flujo local de cambios.
- Exige nombre y teléfono simplificados; el vale puede localizarse si se pierde el código.
- Imprime automáticamente código, QR, titular, teléfono y saldo del vale.
- Registra condición física y destino: venta, cuarentena, merma o garantía.
- Evita devolver más unidades de las compradas y aplica la política por categoría.
- Mantiene una relación auditable entre ticket original, orden de cambio y vale.

Antes de usarlo, abre la configuración del punto de venta y comprueba que **Cambios y vales Leyka** esté activo y que el producto técnico sea **Vale Leyka emitido**.

La cuenta contable definitiva del producto técnico se configurará en el módulo de conciliación/fiscal antes de producción.
