from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    purchase_price = fields.Float(
        string="Cost",
        digits="Product Price",
        compute="_compute_purchase_price",
        store=True,
        precompute=True,
        readonly=False,
        copy=False,
        groups="base.group_user",
    )
    margin = fields.Float(
        string="Margin",
        digits="Product Price",
        compute="_compute_margin",
        store=True,
        precompute=True,
        groups="base.group_user",
    )
    margin_percent = fields.Float(
        string="Margin (%)",
        compute="_compute_margin",
        store=True,
        precompute=True,
        groups="base.group_user",
    )


    @api.depends("product_id", "company_id", "currency_id", "product_uom_id")
    def _compute_purchase_price(self):
        for line in self:
            if not line.product_id:
                line.purchase_price = 0.0
                continue
            line = line.with_company(line.company_id)

            # Convert the cost to the line UoM
            product_cost = line.product_id.uom_id._compute_price(
                line.product_id.standard_price,
                line.product_uom_id,
            )

            line.purchase_price = line._convert_to_sol_currency(
                product_cost, line.product_id.cost_currency_id
            )

    @api.depends("price_subtotal", "product_uom_qty", "purchase_price")
    def _compute_margin(self):
        for line in self:
            line.margin = line.price_subtotal - (
                line.purchase_price * line.product_uom_qty
            )
            line.margin_percent = (
                line.price_subtotal and line.margin / line.price_subtotal
            )
