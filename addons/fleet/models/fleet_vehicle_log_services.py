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
        compute="_compute_vehicle_id", store=True,
        readonly=False,
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
    account_move_line_id = fields.Many2one(
        comodel_name='account.move.line'
    )
    account_move_state = fields.Selection(
        related='account_move_line_id.parent_state'
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
    amount = fields.Monetary(
        string='Cost',
        compute="_compute_amount", store=True,
        readonly=False,
        inverse="_inverse_amount",
        tracking=True
    )
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

    @api.ondelete(at_uninstall=False)
    def _unlink_if_no_linked_bill(self):
        if self.env.context.get('ignore_linked_bill_constraint'):
            return
        if any(log.account_move_line_id for log in self):
            raise UserError(_(
                "You cannot delete log services records because one or more of them were bill created."
            ))

    @api.depends('account_move_line_id.vehicle_id')
    def _compute_vehicle_id(self):
        for log in self:
            # We avoid emptying the vehicle_id as it is a required field
            if not log.account_move_line_id.vehicle_id:
                continue
            log.vehicle_id = log.account_move_line_id.vehicle_id

    @api.depends('account_move_line_id.price_subtotal')
    def _compute_amount(self):
        for log in self:
            log.amount = log.account_move_line_id.debit

    @api.depends('vehicle_id')
    def _compute_driver_id(self):
        for log in self:
            log.driver_id = log.vehicle_id.driver_id

    def _inverse_amount(self):
        if any(service.account_move_line_id for service in self):
            raise UserError(_(
                "You cannot modify amount of services linked to an account move line. "
                "Do it on the related accounting entry instead."
            ))

    def action_open_account_move(self):
        self.ensure_one()
        return {
            'name': _('Bill'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'target': 'current',
            'view_mode': 'form',
            'res_id': self.account_move_line_id.move_id.id,
        }