# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    "Inherit ResConfigSettings"
    _inherit = "res.config.settings"


    days_to_purchase = fields.Float(
        related="company_id.days_to_purchase", readonly=False
    )
    module_stock_dropshipping = fields.Boolean("Dropshipping")
    is_installed_sale = fields.Boolean(string="Is the Sale Module Installed")


    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        res.update(
            is_installed_sale=self.env["ir.module.module"].search(
                [("name", "=", "sale"), ("state", "=", "installed")]
            ).id,
        )
        return res
