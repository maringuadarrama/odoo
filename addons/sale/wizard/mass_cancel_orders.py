# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class SaleMassCancelOrders(models.TransientModel):
    """Wizard for canceling multiple sale orders or quotations at once.

    This module provides a wizard to select and cancel multiple sale orders or quotations in bulk.
    It includes checks to ensure only draft or sent orders are canceled and prevents cancellation
    of confirmed or done orders.
    """
    _name = 'sale.mass.cancel.orders'
    _description = "Cancel multiple quotations"

    # ------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------
    
    # Many2many
    sale_order_ids = fields.Many2many(
        string="Sale orders to cancel",
        comodel_name='sale.order',
        default=lambda self: self.env.context.get('active_ids'),
        relation='sale_order_mass_cancel_wizard_rel',
    )

    # Integer
    count_sale_orders = fields.Integer(compute='_compute_count_sale_orders')

    # Boolean
    has_confirmed_order = fields.Boolean(compute='_compute_has_confirmed_order')

    # ------------------------------------------------------------
    # COMPUTE METHODS
    # ------------------------------------------------------------

    @api.depends('sale_order_ids')
    def _compute_count_sale_orders(self):
        for wizard in self:
            wizard.count_sale_orders = len(wizard.sale_order_ids)

    @api.depends('sale_order_ids')
    def _compute_has_confirmed_order(self):
        for wizard in self:
            wizard.has_confirmed_order = bool(
                wizard.sale_order_ids.filtered(lambda so: so.state in ['sale', 'done'])
            )

    # ------------------------------------------------------------
    # ACTION METHODS
    # ------------------------------------------------------------
    def action_mass_cancel(self):
        self.sale_order_ids._action_cancel()
