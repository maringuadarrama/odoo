# Part of Odoo. See LICENSE file for full copyright and licensing details.

from dateutil.relativedelta import relativedelta

from odoo import api, _, fields, models
from odoo.exceptions import UserError


class FleetVehicleLog(models.Model):
    _name = 'fleet.vehicle.log'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Logs for vehicles'


    def compute_next_year_date(self, strdate):
        start_date = fields.Date.from_string(strdate)
        return fields.Date.to_string(start_date + relativedelta(years=1))


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
    driver_id = fields.Many2one(
        related='vehicle_id.driver_id', string='Driver',
    )
    manager_id = fields.Many2one(
        related='vehicle_id.manager_id',
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
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        ondelete='restrict',
    )
    service_ids = fields.Many2many(
        comodel_name='product.product',
        string="Included Services",
        help='When the log is of type \'Contract\' here the included services can be specified'
    )
    account_move_line_id = fields.Many2one(
        comodel_name='account.move.line'
    )
    account_move_state = fields.Selection(
        related='account_move_line_id.parent_state'
    )
    odometer = fields.Float(
        string='Odometer Value',
        required=True,
        help='Odometer measure of the vehicle at the moment of this log',
    )
    active = fields.Boolean(default=True)
    log_type = fields.Selection(
        [
            ('service', 'Service'),
            ('contract', 'Contract'),
            ('driver', 'Change driver'),
        ],
        string='Log type',
        default='service',
        tracking=True,
        help='Technical name used to classify the log types',
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
    date = fields.Date(
        default=fields.Date.context_today,
        help='Date when the cost has been executed',
    )
    date_start = fields.Date(
        string='Start Date',
        default=fields.Date.context_today,
        tracking=True,
        help='Date when the coverage of the contract begins',
    )
    date_end = fields.Date(
        string='Expiration Date',
        default=lambda self: self.compute_next_year_date(fields.Date.context_today(self)),
        tracking=True,
        help='Date when the coverage of the contract expirates '
             '(by default, one year after begin date)',
    )
    amount = fields.Monetary(
        string='Cost',
        compute="_compute_amount", store=True,
        readonly=False,
        inverse="_inverse_amount",
        tracking=True,
    )
    inv_ref = fields.Char('Vendor Reference')
    notes = fields.Text()
    days_left = fields.Integer(string='Warning Date', compute='_compute_days_left')


    @api.ondelete(at_uninstall=False)
    def _unlink_if_no_linked_bill(self):
        if self.env.context.get('ignore_linked_bill_constraint'):
            return
        if any(log.account_move_line_id for log in self):
            raise UserError(_(
                "You cannot delete log services records because "
                "one or more of them were bill created."
            ))

    @api.depends('account_move_line_id.vehicle_id')
    def _compute_vehicle_id(self):
        for log in self:
            # We avoid emptying the vehicle_id as it is a required field
            if log.account_move_line_id.vehicle_id:
                log.vehicle_id = log.account_move_line_id.vehicle_id
            continue

    @api.depends('account_move_line_id.price_subtotal')
    def _compute_amount(self):
        for log in self:
            if log.account_move_line_id.vehicle_id:
                log.amount = log.account_move_line_id.debit
            continue

    def _inverse_amount(self):
        if any(log.account_move_line_id for log in self):
            raise UserError(_(
                "You cannot modify amount of services linked to an account move line. "
                "Do it on the related accounting entry instead."
            ))

    @api.depends('date_end')
    def _compute_days_left(self):
        today = fields.Date.from_string(fields.Date.today())
        for log in self:
            if log.date_end:
                renew_date = fields.Date.from_string(log.date_end)
                diff_time = (renew_date - today).days
                log.days_left = diff_time if diff_time > 0 else 0
            else:
                log.days_left = -1

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
