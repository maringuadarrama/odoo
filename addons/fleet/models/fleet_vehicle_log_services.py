# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class FleetVehicleLogServices(models.Model):
    _name = 'fleet.vehicle.log.services'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Services for vehicles'
    _rec_name = 'product_id'


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
    odometer_uom_id = fields.Many2one(
        related='vehicle_id.odometer_uom_id',
        string='Unit',
        readonly=True,
    )
    vendor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Vendor',
    )
    driver_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Driver',
        compute='_compute_driver_id', store=True,
        readonly=False,
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Service Type',
        required=True,
        default=lambda self: self.env.ref(
            'fleet.type_service_service_7',
            raise_if_not_found=False
        ),
        ondelete='restrict',
    )
    odometer = fields.Float(
        string='Odometer Value',
        help='Odometer measure of the vehicle at the moment of this log',
    )
    active = fields.Boolean(default=True)
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
    date = fields.Date(
        default=fields.Date.context_today,
        help='Date when the cost has been executed',
    )
    amount = fields.Monetary('Cost')
    inv_ref = fields.Char('Vendor Reference')
    notes = fields.Text()


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
    def _compute_driver_id(self):
        for log in self:
            log.driver_id = log.vehicle_id.driver_id
