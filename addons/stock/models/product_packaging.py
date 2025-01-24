# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ProductPackaging(models.Model):
    _inherit = 'product.packaging'


    package_type_id = fields.Many2one(
        comodel_name='stock.package.type',
        string='Package Type',
    )
    route_ids = fields.Many2many(
        'stock.route',
        'stock_route_packaging',
        'packaging_id',
        'route_id',
        string='Routes',
        domain=[('packaging_selectable', '=', True)],
        help='Depending on the modules installed, this will allow you to define the route of '
             'the product in this packaging: whether it will be bought, manufactured, '
             'replenished on order, etc.',
    )
