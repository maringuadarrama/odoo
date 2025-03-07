# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class AccountAnalyticApplicability(models.Model):
    """Extends the 'account.analytic.applicability' model to include applicability for sale orders.

    This module adds a new business domain option ('sale_order') to the analytic applicability model,
    allowing analytic plans to be applied specifically to sale orders."""
    _inherit = "account.analytic.applicability"
    _description = "Analytic Plan's Applicabilities"


    # ------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------

    business_domain = fields.Selection(
        selection_add=[
            ("sale_order", "Sale Order"),
        ],
        ondelete={
            "sale_order": "cascade"
        },
    )
