from odoo import models, fields


class ProductCategory(models.Model):
    _inherit = 'product.category'


    property_account_downpayment_categ_id = fields.Many2one(
        'account.account',
        'Downpayment Account',
        company_dependent=True,
        domain=[
            ('deprecated', '=', False),
            ('account_type', 'not in',
                (
                    'asset_receivable',
                    'liability_payable',
                    'asset_cash',
                    'liability_credit_card',
                    'off_balance'
                )
            )
        ],
        tracking=True,
        help='This account will be used on Downpayment invoices.',
    )
