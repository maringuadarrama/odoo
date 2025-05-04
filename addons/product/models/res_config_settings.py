from odoo import api, fields, models
from odoo.tools.translate import _


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    group_uom = fields.Boolean(
        string="Units of Measure & Packagings",
        implied_group="uom.group_uom",
    )
    group_product_variant = fields.Boolean(
        string="Variants",
        implied_group="product.group_product_variant",
    )
    group_product_pricelist = fields.Boolean(
        string="Pricelists",
        implied_group="product.group_product_pricelist",
    )
    product_weight_in_lbs = fields.Selection(
        [
            ("0", "Kilograms"),
            ("1", "Pounds"),
        ],
        string="Weight unit of measure",
        default="0",
        config_parameter="product.weight_in_lbs",
    )
    product_volume_volume_in_cubic_feet = fields.Selection(
        [
            ("0", "Cubic Meters"),
            ("1", "Cubic Feet"),
        ],
        string="Volume unit of measure",
        default="0",
        config_parameter="product.volume_in_cubic_feet",
    )
    module_loyalty = fields.Boolean(
        string="Promotions, Coupons, Gift Card & Loyalty Program",
    )

    @api.onchange("group_product_pricelist")
    def _onchange_group_sale_pricelist(self):
        if not self.group_product_pricelist:
            active_pricelist = (
                self.env["product.pricelist"]
                .sudo()
                .search_count([("active", "=", True)], limit=1)
            )
            if active_pricelist:
                return {
                    "warning": {
                        "message": _(
                            "You are deactivating the pricelist feature. "
                            "Every active pricelist will be archived."
                        )
                    }
                }

    def set_values(self):
        had_group_pl = self.default_get(["group_product_pricelist"])[
            "group_product_pricelist"
        ]
        super().set_values()
        if self.group_product_pricelist and not had_group_pl:
            self.env["res.company"]._activate_or_create_pricelists()
        elif not self.group_product_pricelist:
            self.env["product.pricelist"].sudo().search([]).action_archive()
