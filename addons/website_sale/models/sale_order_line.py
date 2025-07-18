# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    name_short = fields.Char(compute='_compute_name_short')
    shop_warning = fields.Char(string="Warning")

    #=== COMPUTE METHODS ===#

    @api.depends('product_id.display_name')
    def _compute_name_short(self):
        """ Compute a short name for this sale order line, to be used on the website where we don't have much space.
            To keep it short, instead of using the first line of the description, we take the product name without the internal reference.
        """
        for record in self:
            record.name_short = record.product_id.with_context(display_default_code=False).display_name

    #=== BUSINESS METHODS ===#

    def get_description_following_lines(self):
        return self.name.splitlines()[1:]

    def _get_order_date(self):
        self.ensure_one()
        if self.order_id.website_id and self.state == 'draft':
            # cart prices must always be computed based on the current time, not on the order
            # creation date.
            return fields.Datetime.now()
        return super()._get_order_date()

    def _get_shop_warning(self, clear=True):
        self.ensure_one()
        warn = self.shop_warning
        if clear:
            self.shop_warning = ''
        return warn

    def _get_displayed_unit_price(self):
        show_tax = self.order_id.website_id.show_line_subtotals_tax_selection
        tax_display = 'total_excluded' if show_tax == 'tax_excluded' else 'total_included'

        return self.tax_ids.compute_all(
            self.price_unit, self.currency_id, 1, self.product_id, self.order_partner_id,
        )[tax_display]

    def _get_displayed_quantity(self):
        rounded_uom_qty = round(self.product_uom_qty,
                                self.env['decimal.precision'].precision_get('Product Unit'))
        return int(rounded_uom_qty) == rounded_uom_qty and int(rounded_uom_qty) or rounded_uom_qty

    def _show_in_cart(self):
        self.ensure_one()
        # Exclude delivery & section/note lines from showing up in the cart
        return not self.is_delivery and not bool(self.display_type) and not bool(self.combo_item_id)

    def _is_reorder_allowed(self):
        self.ensure_one()
        return bool(self.product_id) and self.product_id._is_add_to_cart_allowed()

    def _get_cart_display_price(self):
        self.ensure_one()
        price_type = (
            'price_subtotal'
            if self.order_id.website_id.show_line_subtotals_tax_selection == 'tax_excluded'
            else 'price_total'
        )
        return sum(self._get_lines_with_price().mapped(price_type))
