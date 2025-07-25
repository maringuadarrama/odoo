# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResourceResource(models.Model):
    _inherit = 'resource.resource'

    im_status = fields.Char(related='user_id.im_status')

    def get_avatar_card_data(self, fields):
        return self.env['resource.resource'].search_read(
            domain=[('id', 'in', self.ids)],
        )
