# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class ProductSupplierinfo(models.Model):
    _inherit = 'product.supplierinfo'


    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        self.currency_id = (
            self.partner_id.property_purchase_currency_id.id
            or self.env.company.currency_id.id
        )
