# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = "sale.order"


    count_purchase_order = fields.Integer(
        string="Number of Purchase Order Generated",
        compute="_compute_count_purchase_order",
        groups="purchase.group_purchase_user",
    )


    @api.depends("order_line_ids.purchase_line_ids.order_id")
    def _compute_count_purchase_order(self):
        for order in self:
            order.count_purchase_order = len(order._get_purchase_orders())

    def _hook_action_confirm(self):
        result = super(SaleOrder, self)._hook_action_confirm()
        for order in self:
            order.order_line_ids.sudo()._purchase_service_generation()
        return result

    def action_cancel(self):
        result = super().action_cancel()
        # When a sale person cancel a SO, he might not have the rights to write
        # on PO. But we need the system to create an activity on the PO (so "write"
        # access), hence the `sudo`.
        self.sudo()._activity_cancel_on_purchase()
        return result

    def action_view_purchase_orders(self):
        self.ensure_one()
        purchase_order_ids = self._get_purchase_orders().ids
        action = {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
        }
        if len(purchase_order_ids) == 1:
            action.update({
                "view_mode": "form",
                "res_id": purchase_order_ids[0],
            })
        else:
            action.update({
                "name": _("Purchase Order generated from %s", self.name),
                "domain": [("id", "in", purchase_order_ids)],
                "view_mode": "list,form",
            })
        return action

    def _get_purchase_orders(self):
        return self.order_line_ids.purchase_line_ids.order_id

    def _activity_cancel_on_purchase(self):
        """If some SO are cancelled, we need to put an activity on their generated purchase.
        If sale lines of different sale orders impact different purchase,
        we only want one activity to be attached."""
        # map PO -> recordset of SOL as {purchase.order: set(sale.orde.liner)}
        purchase_to_notify_map = {}
        purchase_order_lines = self.env["purchase.order.line"].search([
            ("sale_line_id", "in", self.mapped("order_line_ids").ids),
            ("state", "!=", "cancel")
        ])

        for purchase_line in purchase_order_lines:
            purchase_to_notify_map.setdefault(purchase_line.order_id, self.env["sale.order.line"])
            purchase_to_notify_map[purchase_line.order_id] |= purchase_line.sale_line_id

        for purchase_order, sale_order_lines in purchase_to_notify_map.items():
            purchase_order._activity_schedule_with_view("mail.mail_activity_data_warning",
                user_id=purchase_order.user_id.id or self.env.uid,
                views_or_xmlid="sale_purchase.exception_purchase_on_sale_cancellation",
                render_context={
                    "sale_orders": sale_order_lines.mapped("order_id"),
                    "sale_order_lines": sale_order_lines,
            })
