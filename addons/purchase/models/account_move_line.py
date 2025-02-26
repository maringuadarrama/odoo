# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import fields, models


class AccountMoveLine(models.Model):
    """Inherit AccountMoveLine to add the link to a purchase order line"""
    _inherit = "account.move.line"


    is_downpayment = fields.Boolean()
    purchase_line_id = fields.Many2one(
        comodel_name="purchase.order.line",
        string="Purchase Order Line",
        copy=False,
        ondelete="set null",
        index="btree_not_null",
    )
    purchase_order_id = fields.Many2one(
        related="purchase_line_id.order_id",
        string="Purchase Order",
        readonly=True,
    )


    # -------------------------------------------------------------------------
    # HOOKS
    # -------------------------------------------------------------------------

    def _copy_data_extend_business_fields(self, values):
        super(AccountMoveLine, self)._copy_data_extend_business_fields(values)
        values["purchase_line_id"] = self.purchase_line_id.id


    # -------------------------------------------------------------------------
    # HELPER
    # -------------------------------------------------------------------------

    def _prepare_line_values_for_purchase(self):
        return [
            {
                "product_id": line.product_id.id,
                "product_qty": line.quantity,
                "product_uom_id": line.product_uom_id.id,
                "price_unit": line.price_unit,
                "discount": line.discount,
            }
            for line in self
        ]
