# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ProductPackaging(models.Model):
    _inherit = 'product.packaging'


    sales = fields.Boolean(
        string='Sales',
        default=True,
        help='If true, the packaging can be used for sales orders',
    )
