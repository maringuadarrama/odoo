# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class AccountAnalyticApplicability(models.Model):
    """Inherit AccountAnalyticApplicability"""
    _inherit = "account.analytic.applicability"
    _description = "Analytic Plan's Applicabilities"


    business_domain = fields.Selection(
        selection_add=[
            ("purchase_order", "Purchase Order"),
        ],
        ondelete={"purchase_order": "cascade"},
    )
