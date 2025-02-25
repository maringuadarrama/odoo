# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_round


class ProductProduct(models.Model):
    _inherit = "product.product"

    # ------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------

    # Boolean
    product_catalog_product_is_in_sale_order = fields.Boolean(
        compute="_compute_product_is_in_sale_order",
        search="_search_product_is_in_sale_order",
    )

    # ------------------------------------------------------------
    # COMPUTE METHODS
    # ------------------------------------------------------------

    @api.depends_context("order_id")
    def _compute_product_is_in_sale_order(self):
        order_id = self.env.context.get("order_id")
        if not order_id:
            self.product_catalog_product_is_in_sale_order = False
            return

        read_group_data = self.env["sale.order.line"]._read_group(
            domain=[("order_id", "=", order_id)],
            groupby=["product_id"],
            aggregates=["__count"],
        )
        data = {product.id: count for product, count in read_group_data}
        for product in self:
            product.product_catalog_product_is_in_sale_order = bool(data.get(product.id, 0))
