{
    "name": "Leyka · Vales en el POS",
    "summary": "Devoluciones por vale, titular, teléfono y canje parcial",
    "version": "19.0.1.0.0",
    "author": "Leyka Motors",
    "license": "LGPL-3",
    "category": "Sales/Point of Sale",
    "depends": ["pos_loyalty", "base_automation"],
    "data": ["data/fields.xml", "data/program.xml", "data/guards.xml", "data/views.xml"],
    "assets": {
        "point_of_sale._assets_pos": [
            "leyka_pos_vales/static/src/vales.js",
            "leyka_pos_vales/static/src/vales.xml",
            "leyka_pos_vales/static/src/vales.css",
        ],
    },
    "installable": True,
    "application": True,
}
