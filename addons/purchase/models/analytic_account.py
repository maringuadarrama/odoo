# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class AccountAnalyticAccount(models.Model):
    """Inherit AccountAnalyticAccount"""
    _inherit = "account.analytic.account"


    count_purchase_order = fields.Integer(
        string="Purchase Order Count",
        compute="_compute_count_purchase_order",
    )


    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends("line_ids")
    def _compute_count_purchase_order(self):
        for account in self:
            account.count_purchase_order = self.env["purchase.order"].search_count([
                ("order_line_ids.invoice_line_ids.analytic_line_ids.account_id", "in", account.ids)
            ])


    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------

    def action_view_purchase_orders(self):
        self.ensure_one()
        purchase_orders = self.env["purchase.order"].search([
            ("order_line_ids.invoice_line_ids.analytic_line_ids.account_id", "=", self.id)
        ])
        result = {
            "name": _("Purchase Orders"),
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": [["id", "in", purchase_orders.ids]],
        }
        if len(purchase_orders) == 1:
            result["view_mode"] = "form"
            result["res_id"] = purchase_orders.id
        return result
