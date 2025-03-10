from odoo import fields, models


class AccountAnalyticLine(models.Model):
    """Extends the 'account.analytic.line' model to link analytic lines to sale order lines.

    This module adds a Many2one field to associate analytic lines with specific sale order items,
    enabling better tracking of delivered quantities and analytic data related to sales.
    """

    _inherit = "account.analytic.line"

    # ------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------

    so_line = fields.Many2one(
        comodel_name="sale.order.line",
        string="Sales Order Item",
        domain=[("qty_delivered_method", "=", "analytic")],
        index="btree_not_null",
    )
