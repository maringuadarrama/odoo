from odoo import fields, models


class StockRoute(models.Model):
    _inherit = "stock.route"

    sale_selectable = fields.Boolean("Selectable on Sales Order Line")
