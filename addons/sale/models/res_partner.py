from odoo import api, fields, models
from odoo.osv import expression

from odoo.addons.base.models.res_partner import WARNING_HELP, WARNING_MESSAGE


class ResPartner(models.Model):
    """Extends the 'res.partner' model to include sales-related functionalities and tracking.

    This module adds fields and methods to track the number of sales orders associated with a partner,
    manage sales warnings, and compute credit-to-invoice amounts. It also ensures that partners with
    issued sales orders cannot be edited or deleted under certain conditions."""

    _inherit = "res.partner"

    # ------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------

    sale_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Salesperson",
        compute="_compute_sale_user_id",
        store=True,
        precompute=True,  # avoid queries post-create
        readonly=False,
        help="The internal user in charge of this contact.",
    )
    sale_warn = fields.Selection(
        WARNING_MESSAGE,
        string="Sales Warnings",
        default="no-message",
        help=WARNING_HELP,
    )
    sale_warn_msg = fields.Text("Message for Sales Order")
    sale_order_ids = fields.One2many(
        comodel_name="sale.order",
        inverse_name="partner_id",
        string="Sales Order",
    )
    count_sale_order = fields.Integer(
        string="Sale Order Count",
        compute="_compute_count_sale_order",
        groups="sales_team.group_sale_salesman",
    )

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

    # -----------------------------------------------------------
    # COMPUTE METHODS
    # -----------------------------------------------------------

    @api.depends("parent_id")
    def _compute_sale_user_id(self):
        """Synchronize sales rep with parent if partner is a person"""
        for partner in self.filtered(
            lambda partner: not partner.user_id
            and partner.company_type == "person"
            and partner.parent_id.user_id
        ):
            partner.user_id = partner.parent_id.user_id

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
            domain=expression.AND(
                [
                    self._get_sale_order_domain_count(),
                    [("partner_id", "in", all_partners.ids)],
                ]
            ),
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
    # TOOLS
    # -----------------------------------------------------------

    @api.model
    def _get_sale_order_domain_count(self):
        return []

    # -----------------------------------------------------------
    # VALIDATIONS
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
                            ("state", "=", "sale"),
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
