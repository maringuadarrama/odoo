# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ProductPackaging(models.Model):
    _inherit = 'product.packaging'


    purchase = fields.Boolean(
        string='Purchase',
        default=True,
        help='If true, the packaging can be used for purchase orders',
    )
