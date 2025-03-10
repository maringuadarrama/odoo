# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class StockValuationLayer(models.Model):
    _inherit = "stock.valuation.layer"

    def _get_layer_price_unit(self):
        """This function returns the value of product in a layer per unit, relative to the aml
        the function is designed to be overriden to add logic to price unit calculation
        :param layer: the layer the price unit is derived from"""
        return self.value / self.quantity
