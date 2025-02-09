# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class FleetVehicleAssignationLog(models.Model):
    _name = "fleet.vehicle.assignation.log"
    _description = "Drivers history on a vehicle"
    _order = "create_date desc, date_start desc"


    vehicle_id = fields.Many2one('fleet.vehicle', string="Vehicle", required=True)
    driver_id = fields.Many2one('hr.employee', string="Driver", required=True)
    date_start = fields.Date(string="Start Date")
    date_end = fields.Date(string="End Date")
    attachment_number = fields.Integer('Number of Attachments', compute='_compute_attachment_number')


    @api.depends('driver_id', 'vehicle_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'{rec.vehicle_id.name} - {rec.driver_id.name}'

    def _compute_attachment_number(self):
        attachment_data = self.env['ir.attachment']._read_group(
            [
                ('res_model', '=', 'fleet.vehicle.log.assignation'),
                ('res_id', 'in', self.ids)
            ],
            ['res_id'],
            ['__count']
        )
        attachment = dict(attachment_data)
        for doc in self:
            doc.attachment_number = attachment.get(doc.id, 0)

    def action_get_attachment_view(self):
        self.ensure_one()
        res = self.env['ir.actions.act_window']._for_xml_id('base.action_attachment')
        res['views'] = [[self.env.ref('fleet.view_attachment_kanban_inherit_fleet').id, 'kanban']]
        res['domain'] = [
            ('res_model', '=', 'fleet.vehicle.log.assignation'),
            ('res_id', 'in', self.ids)
        ]
        res['context'] = {
            'default_res_model': 'fleet.vehicle.log.assignation',
            'default_res_id': self.id
        }
        return res
