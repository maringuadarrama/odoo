# Part of Odoo. See LICENSE file for full copyright and licensing details.

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_round


class ProductProduct(models.Model):
    _name = 'product.product'
    _inherit = 'product.product'


    purchased_product_qty = fields.Float(
        string='Purchased',
        digits='Product Unit of Measure',
        compute='_compute_purchased_product_qty',
    )
    is_in_purchase_order = fields.Boolean(
        compute='_compute_is_in_purchase_order',
        search='_search_is_in_purchase_order',
    )


    def _compute_purchased_product_qty(self):
        date_from = fields.Datetime.to_string(
            fields.Date.context_today(self) - relativedelta(years=1)
        )
        domain = [
            ('order_id.state', 'in', ['purchase', 'done']),
            ('product_id', 'in', self.ids),
            ('order_id.date_approve', '>=', date_from),
        ]
        order_lines = self.env['purchase.order.line']._read_group(
            domain,
            ['product_id'],
            ['product_uom_qty:sum']
        )
        purchased_data = {product.id: qty for product, qty in order_lines}
        for product in self:
            if not product.id:
                product.purchased_product_qty = 0.0
                continue

            product.purchased_product_qty = float_round(
                purchased_data.get(product.id, 0),
                precision_rounding=product.uom_id.rounding
            )

    @api.depends_context('order_id')
    def _compute_is_in_purchase_order(self):
        order_id = self.env.context.get('order_id')
        if not order_id:
            self.is_in_purchase_order = False
            return

        read_group_data = self.env['purchase.order.line']._read_group(
            domain=[('order_id', '=', order_id)],
            groupby=['product_id'],
            aggregates=['__count'],
        )
        data = {product.id: count for product, count in read_group_data}
        for product in self:
            product.is_in_purchase_order = bool(data.get(product.id, False))

    def _search_is_in_purchase_order(self, operator, value):
        if operator not in ['=', '!='] or not isinstance(value, bool):
            raise UserError(_('Operation not supported'))

        product_ids = self.env['purchase.order.line'].search([
            ('order_id', 'in', [self.env.context.get('order_id', '')]),
        ]).product_id.ids
        return [('id', 'in', product_ids)]

    def _get_backend_root_menu_ids(self):
        return super()._get_backend_root_menu_ids() + [
            self.env.ref('purchase.menu_purchase_root').id
        ]

    def action_view_po(self):
        action = self.env['ir.actions.actions']._for_xml_id('purchase.action_purchase_history')
        action['domain'] = [
            '&',
            ('state', 'in', ['purchase', 'done']),
            ('product_id', 'in', self.ids),
        ]
        action['display_name'] = _('Purchase History for %s', self.display_name)
        return action
