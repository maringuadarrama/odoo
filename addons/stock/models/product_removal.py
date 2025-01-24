# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class RemovalStrategy(models.Model):
    _name = 'product.removal'
    _description = 'Removal Strategy'


    name = fields.Char(
        string='Name',
        required=True,
        translate=True,
    )
    method = fields.Char(
        string='Method',
        required=True,
        translate=True,
        help='FIFO, LIFO...',
    )
