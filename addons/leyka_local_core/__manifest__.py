{
    "name": "Leyka Local Core",
    "summary": "Núcleo local para titulares simplificados, vales y auditoría",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "author": "Leyka Motors",
    "license": "LGPL-3",
    "depends": ["base", "contacts", "account", "point_of_sale"],
    "data": [
        "security/leyka_security.xml",
        "security/ir.model.access.csv",
        "views/voucher_holder_views.xml",
        "views/store_credit_views.xml",
        "views/menus.xml"
    ],
    "installable": True,
    "application": True,
    "auto_install": False
}
