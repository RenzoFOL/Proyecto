{
    "name": "Leyka POS Cambios y Vales",
    "summary": "Cambios, devoluciones, garantías y vales para tienda local",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "author": "Leyka Motors",
    "license": "LGPL-3",
    "depends": ["leyka_local_core", "stock", "point_of_sale"],
    "data": [
        "security/ir.model.access.csv",
        "data/return_sequence.xml",
        "views/product_category_views.xml",
        "views/pos_config_views.xml",
        "views/return_request_views.xml",
        "views/menus.xml"
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "leyka_pos_exchange/static/src/js/change_control_button.js",
            "leyka_pos_exchange/static/src/xml/change_control_button.xml"
        ]
    },
    "installable": True,
    "application": False,
    "auto_install": False
}
