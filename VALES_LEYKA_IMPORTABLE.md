# Vales Leyka · Odoo 19 Community

Un único módulo: `leyka_pos_vales`. El ZIP se importa desde Odoo; no se copia a addons y no requiere un instalador EXE. Utiliza los programas de tarjetas de regalo de Community, campos personalizados, reglas de automatización importables y componentes del POS. No contiene clases Python de servidor.

## Requisitos e instalación

1. Haz una copia de la base de la tienda y prueba primero en esa copia. No mezcles esta prueba con el antiguo módulo experimental `leyka_pos_exchange`; no desinstales módulos con movimientos reales sin revisar los datos.
2. En Odoo 19 Community, como administrador, ve a **Aplicaciones → Importar módulo** y carga `leyka_pos_vales_Odoo19.zip`. No descomprimas el archivo. Sin datos de demostración.
3. Se requieren los módulos Community `pos_loyalty` (tarjetas de regalo del POS) y `base_automation` (reglas de automatización). El importador instala las dependencias disponibles. No requiere Enterprise, Studio ni `account_accountant`. El POS usa internamente componentes técnicos `account` de Community; eso no significa contratar la aplicación de Contabilidad Enterprise.
4. Sal de la interfaz del POS y vuelve a entrar para cargar sus nuevos recursos. Si conservas una pestaña antigua, recarga con Ctrl+F5. No cierres la sesión de caja solamente para actualizar la pestaña.
5. En **POS → Productos → Tarjetas de regalo y monederos**, comprueba el programa **Vales Leyka · Cambios en tienda**: activo, moneda MXN, empresa de la tienda, disponible en tu POS. No cambies su tipo, reglas, recompensa, producto ni establezcas fecha de vencimiento.

## Emitir un vale

1. Desde una orden vacía: **⋮ → Cambios / vales → Emitir vale por devolución**.
2. Busca la venta pagada original. Selecciona únicamente las piezas y cantidades aceptadas y pulsa el botón nativo **Reembolso**.
3. Captura nombre, teléfono mexicano de 10 dígitos y motivo. Confirma la revisión física y que la mercancía puede volver al inventario vendible.
4. El módulo añade el vale por el importe aceptado, conservando los precios, impuestos y descuentos por línea originales. El total queda en **cero**.
5. Pulsa **Validar**, sin elegir efectivo ni Mercado Pago. Se registra la devolución nativa, vuelve la mercancía al inventario y se emite el código. Se intenta imprimir el comprobante con la impresora habitual del POS.

Una compra de dos piezas de $100 puede dar un vale de $100 si se devuelve solo una. No se concede siempre el total de la venta: se concede el total de las piezas aceptadas.

## Canjear, consultar y recuperar

- Agrega los productos de una nueva compra; abre **⋮ → Cambios / vales → Buscar, canjear o reimprimir**.
- Busca por código completo, teléfono completo o parte del nombre. Compara nombre y teléfono con el titular; conocer un nombre no verifica identidad.
- Pulsa **Canjear en esta compra**. Vale de $100 + compra de $40 = saldo de $60. Vale de $100 + compra de $140 = cobro normal de $40 por efectivo o terminal. El importe canjeado utiliza el tratamiento nativo de tarjeta de regalo de Odoo, no un descuento porcentual comercial nuevo.
- El mismo código conserva el saldo restante. Sin caducidad. La reimpresión no crea un nuevo saldo.
- Si hubo una interrupción después de validar la devolución y antes de crear la tarjeta, busca al titular y pulsa **Recuperar vale de esta devolución**. No crees otra devolución para solucionar una impresión fallida.
- También existe **POS → Vales Leyka**, con titular, teléfono, saldo, devolución de origen e historial.

## Alcance de esta primera versión

- Nombre y teléfono en el vale, sin RFC, dirección, correo obligatorio ni alta de cliente formal.
- Una venta original por devolución. Devoluciones parciales y totales de mercancía apta para volver al inventario.
- Bloqueos de cantidades repetidas/excesivas, importe incoherente, saldo negativo, datos faltantes y devolución de dinero dentro del flujo de vales.
- Conexión con el servidor Odoo obligatoria para emitir, consultar, recuperar o canjear. No ofrece canje offline.
- Las ventas originales que contienen líneas de recompensas/promociones o pagos con otro vale quedan bloqueadas para emitir nuevos vales en esta versión. Su devolución necesita distribuir el descuento o saldo correctamente; no se calcula un importe aproximado.
- Las piezas dañadas, instaladas y garantías no se ingresan a cuarentena automáticamente. Este flujo exige que estén aptas para venderse; no lo uses para mercancía dañada.
- No modifica CFDI, declaraciones, IVA/ISR, Mercado Pago, Stori ni otras devoluciones fuera del flujo guiado. La decisión sobre si procede el cambio corresponde a la revisión de la tienda.
- No hace falta un nuevo EXE. Si Leyka Direct Print ya funciona, se utiliza ese servicio de impresión. Sin un puente o impresora configurada, Odoo puede abrir el diálogo de impresión del navegador.

## Verificación

La prueba automatizada importa el ZIP dos veces por `_import_zipfile`, sin añadir el módulo a `addons_path`. Verifica emisión, reintento, titular obligatorio, canje parcial, saldo negativo, duplicación de devoluciones, caducidad y bloqueo de efectivo. La prueba de navegador recorre los tres puntos, devolución, captura del titular, recibo y canje con un usuario de caja.

El entorno de pruebas es Odoo 19 Community con PostgreSQL en Linux. La impresión física de tu térmica y tu base Windows deben comprobarse en tu copia antes de operar con clientes.

Fuente del flujo nativo: https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/use.html

Importador: https://github.com/odoo/odoo/blob/19.0/addons/base_import_module/models/ir_module.py
