{
    "name": "Leyka Compras CFDI",
    "summary": "Importación segura de XML/ZIP CFDI y creación controlada de facturas de proveedor",
    "version": "19.0.2.0.0",
    "category": "Accounting/Accounting",
    "author": "Leyka Motors",
    "license": "LGPL-3",
    "depends": ["leyka_local_core", "purchase", "account"],
    "data": [
        "security/cfdi_security.xml",
        "security/ir.model.access.csv",
        "views/cfdi_purchase_views.xml",
        "wizard/cfdi_import_wizard_views.xml",
        "views/menus.xml"
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "external_dependencies": {"python": ["lxml"]}
}
