from odoo import fields, models


class ProductCategory(models.Model):
    """Extends the 'product.category' model to include a downpayment account configuration.

    This module adds a Many2one field to specify an account for downpayment invoices at the product category level,
    ensuring proper accounting treatment for downpayment transactions.
    """
    _inherit = "product.category"

    # ------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------

    # Many2one
    property_account_downpayment_categ_id = fields.Many2one(
        comodel_name='account.account',
        company_dependent=True,
        string="Downpayment Account",
        domain=[
            ('deprecated', '=', False),
            ('account_type', 'not in', ('asset_receivable', 'liability_payable', 'asset_cash', 'liability_credit_card', 'off_balance'))
        ],
        help="This account will be used on Downpayment invoices.",
        tracking=True,
    )