# Leyka Motors — Suite Odoo 19 Community

Suite modular para la operación local de Leyka Motors en Odoo 19 Community.

## Módulos en desarrollo

| Módulo | Función | Estado |
|---|---|---|
| `leyka_local_core` | Titulares simples, vales, saldos y auditoría | Implementado |
| `leyka_pos_exchange` | Cambios, diferencias, vales nominativos, impresión y canje por código/nombre/teléfono | Integración POS en pruebas |
| `leyka_cfdi_purchase` | Importación XML/ZIP y factura de proveedor borrador | Primera versión |
| Conciliación y control fiscal | POS, Mercado Pago, Stori, IVA e ISR estimado | Siguiente fase |
| Mercado Libre | Pedidos, comisiones y conciliación | Fase final |
| Sitio web | Despliegue público con dominio dedicado | Fase final |

## Principios

- Compatible con Odoo 19 Community.
- Operación local primero; servicios externos mediante adaptadores independientes.
- Ningún token, contraseña, RFC real ni clave fiscal dentro del repositorio.
- Las cifras fiscales serán auxiliares de control y conciliación; no sustituyen la revisión del contador.
- Todo movimiento de vales, cambios y ajustes queda auditado.
- En la tienda local no se devuelve efectivo: el flujo normal termina en cambio o vale.

## Instalación de desarrollo

1. Copia las carpetas de `addons/` a una ruta incluida en `addons_path`.
2. Reinicia el servicio de Odoo.
3. Activa modo desarrollador y actualiza la lista de aplicaciones.
4. Instala primero **Leyka Local Core**, después **Leyka POS Cambios y Vales** y **Leyka Compras CFDI**.
5. Asigna al personal los grupos **Operador Leyka** o **Responsable Leyka**.
6. En cada POS verifica el producto técnico **Vale Leyka emitido** y cierra/abre la sesión para recargar los recursos.

Los ZIP generados por GitHub Actions se publican en el artefacto **Leyka-Local-Suite-Odoo19**.

## Rama de trabajo

`codex/leyka-local-suite-v0.1`

No se debe usar en producción hasta que las pruebas de instalación, permisos, POS, inventario y contabilidad terminen correctamente.
