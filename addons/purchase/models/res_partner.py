# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.addons.base.models.res_partner import WARNING_MESSAGE, WARNING_HELP


class ResPartner(models.Model):
    """Inherit ResPartner"""
    _inherit = "res.partner"


    buyer_id = fields.Many2one(
        comodel_name="res.users",
        string="Buyer",
    )
    property_purchase_currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Supplier Currency",
        company_dependent=True,
        help="This currency will be used for purchases from the current partner",
    )
    purchase_warn = fields.Selection(
        WARNING_MESSAGE,
        string="Purchase Order Warning",
        default="no-message",
        help=WARNING_HELP,
    )
    purchase_warn_msg = fields.Text("Message for Purchase Order")
    receipt_reminder_email = fields.Boolean(
        string="Receipt Reminder",
        company_dependent=True,
        help="Automatically send a confirmation email to the vendor X days before the "
             "expected receipt date, asking him to confirm the exact date."
    )
    reminder_date_before_receipt = fields.Integer(
        string="Days Before Receipt",
        company_dependent=True,
        help="Number of days to send reminder email before the promised receipt date",
    )
    count_purchase_order = fields.Integer(
        string="Purchase Order Count",
        compute="_compute_count_purchase_order",
        groups="purchase.group_purchase_user",
    )


    # ------------------------------------------------------------
    # COMPUTE METHODS
    # ------------------------------------------------------------

    def _compute_count_purchase_order(self):
        self.count_purchase_order = 0
        if not self.env.user._has_group("purchase.group_purchase_user"):
            return

        # retrieve all children partners and prefetch "parent_id" on them
        all_partners = self.with_context(active_test=False).search_fetch(
            [("id", "child_of", self.ids)],
            ["parent_id"],
        )
        purchase_order_groups = self.env["purchase.order"]._read_group(
            domain=[("partner_id", "in", all_partners.ids)],
            groupby=["partner_id"], aggregates=["__count"],
        )
        self_ids = set(self._ids)
        for partner, count in purchase_order_groups:
            while partner:
                if partner.id in self_ids:
                    partner.count_purchase_order += count
                partner = partner.parent_id


    # ------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------

    @api.model
    def _commercial_fields(self):
        return super()._commercial_fields()
