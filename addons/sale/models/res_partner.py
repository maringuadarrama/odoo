# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.osv import expression

from odoo.addons.base.models.res_partner import WARNING_HELP, WARNING_MESSAGE


class ResPartner(models.Model):
    """Extends the 'res.partner' model to include sales-related functionalities and tracking.

    This module adds fields and methods to track the number of sales orders associated with a partner,
    manage sales warnings, and compute credit-to-invoice amounts. It also ensures that partners with
    issued sales orders cannot be edited or deleted under certain conditions.
    """

    _inherit = "res.partner"

    # ------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------

    # Integer
    count_sale_order = fields.Integer(
        string="Sale Order Count",
        groups="sales_team.group_sale_salesman",
        compute="_compute_count_sale_order",
    )

    # One2many
    sale_order_ids = fields.One2many("sale.order", "partner_id", "Sales Order")

    # Selection
    sale_warn = fields.Selection(WARNING_MESSAGE, "Sales Warnings", default="no-message", help=WARNING_HELP)

    # Text
    sale_warn_msg = fields.Text("Message for Sales Order")

    # -----------------------------------------------------------
    # HELPERS
    # -----------------------------------------------------------

    def _has_order(self, partner_domain):
        self.ensure_one()
        sale_order = (
            self.env["sale.order"]
            .sudo()
            .search(
                expression.AND(
                    [
                        partner_domain,
                        [
                            ("state", "in", ("sent", "sale")),
                        ],
                    ]
                ),
                limit=1,
            )
        )
        return bool(sale_order)

    def _can_edit_name(self):
        """Can't edit `name` if there is (non draft) issued SO."""
        return super()._can_edit_name() and not self._has_order(
            [
                ("partner_invoice_id", "=", self.id),
                ("partner_id", "=", self.id),
            ]
        )

    def can_edit_vat(self):
        """Can't edit `vat` if there is (non draft) issued SO."""
        return super().can_edit_vat() and not self._has_order(
            [("partner_id", "child_of", self.commercial_partner_id.id)]
        )

    # -----------------------------------------------------------
    # TOOLS
    # -----------------------------------------------------------

    @api.model
    def _get_sale_order_domain_count(self):
        return []

    # -----------------------------------------------------------
    # COMPUTE METHODS
    # -----------------------------------------------------------

    def _compute_count_sale_order(self):
        self.count_sale_order = 0
        if not self.env.user.has_group("sales_team.group_sale_salesman"):
            return

        # retrieve all children partners and prefetch 'parent_id' on them
        all_partners = self.with_context(active_test=False).search_fetch(
            [("id", "child_of", self.ids)],
            ["parent_id"],
        )
        sale_order_groups = self.env["sale.order"]._read_group(
            domain=expression.AND([self._get_sale_order_domain_count(), [("partner_id", "in", all_partners.ids)]]),
            groupby=["partner_id"],
            aggregates=["__count"],
        )
        self_ids = set(self._ids)

        for partner, count in sale_order_groups:
            while partner:
                if partner.id in self_ids:
                    partner.count_sale_order += count
                partner = partner.parent_id

    # -----------------------------------------------------------
    # CORE METHODS
    # -----------------------------------------------------------

    def unlink(self):
        # Unlink draft/cancelled SO so that the partner can be removed from database
        self.env["sale.order"].sudo().search(
            [
                ("state", "in", ["draft", "cancel"]),
                "|",
                "|",
                ("partner_id", "in", self.ids),
                ("partner_invoice_id", "in", self.ids),
                ("partner_shipping_id", "in", self.ids),
            ]
        ).unlink()  # TODO: Review business cases where should be deleted an order
        return super().unlink()
