# Part of Odoo. See LICENSE file for full copyright and licensing details.

import threading

from odoo import api, models, tools, _
from odoo.exceptions import ValidationError


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _is_delivered_timesheet(self):
        """ Check if the product is a delivered timesheet """
        self.ensure_one()
        return self.type == 'service' and self.service_policy == 'delivered_timesheet'

    @api.onchange('type', 'service_type', 'service_policy')
    def _onchange_service_fields(self):
        hour_uom = self.env.ref('uom.product_uom_hour')
        for record in self:
            default_uom_id = self.env['ir.default']._get_model_defaults('product.product').get('uom_id')
            default_uom = self.env['uom.uom'].browse(default_uom_id)
            if record.type == 'service' and record.service_type == 'timesheet' and \
               not (record._origin.service_policy and record.service_policy == record._origin.service_policy):
                if default_uom and default_uom._has_common_reference(hour_uom):
                    record.uom_id = default_uom
                else:
                    record.uom_id = hour_uom
            elif record._origin.uom_id:
                record.uom_id = record._origin.uom_id
            elif default_uom:
                record.uom_id = default_uom
            else:
                record.uom_id = self.product_tmpl_id.default_get(['uom_id']).get('uom_id')

    @api.onchange('service_policy')
    def _onchange_service_policy(self):
        self._inverse_service_policy()
        vals = self.product_tmpl_id._get_onchange_service_policy_updates(self.service_tracking,
                                                                        self.service_policy,
                                                                        self.project_id,
                                                                        self.project_template_id)
        if vals:
            self.update(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_master_data(self):
        time_product = self.env.ref('sale_timesheet.time_product')
        if time_product in self:
            raise ValidationError(_('The %s product is required by the Timesheets app and cannot be archived, deleted nor linked to a company.', time_product.name))

    def write(self, vals):
        # timesheet product can't be deleted, archived or linked to a company
        if ('active' in vals and not vals['active']) or ('company_id' in vals and vals['company_id']):
            time_product = self.env.ref('sale_timesheet.time_product')
            if time_product in self:
                raise ValidationError(_('The %s product is required by the Timesheets app and cannot be archived, deleted nor linked to a company.', time_product.name))
        return super().write(vals)
