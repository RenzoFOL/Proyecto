# Leyka Local Core

Núcleo para Odoo 19 Community.

## Incluye

- Titular simplificado con nombre y teléfono obligatorios.
- Vinculación opcional posterior con un cliente formal.
- Vales sin caducidad por defecto.
- Saldo parcial, cancelación y reposición de código perdido.
- Historial inmutable de movimientos.
- Bloqueo de fila al consumir saldo para impedir doble uso concurrente.
- Separación por compañía y permisos de operador/responsable.

## Seguridad

No contiene credenciales. La cancelación y reposición requieren el grupo **Responsable Leyka**.
