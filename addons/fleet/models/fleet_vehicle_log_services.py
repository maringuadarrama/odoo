# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FleetVehicleLogServices(models.Model):
    _name = 'fleet.vehicle.log.services'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'service_type_id'
    _description = 'Services for vehicles'


    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
    )
    vehicle_id = fields.Many2one(
        comodel_name='fleet.vehicle',
        string='Vehicle',
        required=True,
    )
    manager_id = fields.Many2one(
        related='vehicle_id.manager_id',
        store=True,
        string='Fleet Manager',
    )
    odometer_unit = fields.Selection(
        related='vehicle_id.odometer_unit',
        string='Unit',
        readonly=True,
    )
    odometer_id = fields.Many2one(
        comodel_name='fleet.vehicle.odometer',
        string='Odometer',
        help='Odometer measure of the vehicle at the moment of this log',
    )
    odometer = fields.Float(
        string='Odometer Value',
        compute='_compute_odometer',
        inverse='_set_odometer',
        help='Odometer measure of the vehicle at the moment of this log',
    )
    vendor_id = fields.Many2one('res.partner', 'Vendor')
    purchaser_id = fields.Many2one('res.partner', string='Driver', compute='_compute_purchaser_id', store=True, readonly=False)
    service_type_id = fields.Many2one(
        'fleet.service.type',
        'Service Type',
        required=True,
        default=lambda self: self.env.ref(
            'fleet.type_service_service_7',
            raise_if_not_found=False
        ),
    )
    date = fields.Date(
        default=fields.Date.context_today,
        help='Date when the cost has been executed',
    )
    state = fields.Selection(
        [
            ('new', 'New'),
            ('running', 'Running'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Stage',
        default='new',
        group_expand=True,
        tracking=True
    )
    description = fields.Char('Description')
    amount = fields.Monetary('Cost')
    inv_ref = fields.Char('Vendor Reference')
    notes = fields.Text()
    active = fields.Boolean(default=True)


    @api.model_create_multi
    def create(self, vals_list):
        for data in vals_list:
            if 'odometer' in data and not data['odometer']:
                # if received value for odometer is 0, then remove it from the
                # data as it would result to the creation of a
                # odometer log with 0, which is to be avoided
                del data['odometer']
        return super(FleetVehicleLogServices, self).create(vals_list)

    @api.depends('vehicle_id')
    def _compute_purchaser_id(self):
        for service in self:
            service.purchaser_id = service.vehicle_id.driver_id

    def _compute_odometer(self):
        self.odometer = 0
        for record in self:
            if record.odometer_id:
                record.odometer = record.odometer_id.value

    def _set_odometer(self):
        for record in self:
            if not record.odometer:
                raise UserError(_('Emptying the odometer value of a vehicle is not allowed.'))
            odometer = self.env['fleet.vehicle.odometer'].create({
                'value': record.odometer,
                'date': record.date or fields.Date.context_today(record),
                'vehicle_id': record.vehicle_id.id
            })
            self.odometer_id = odometer
