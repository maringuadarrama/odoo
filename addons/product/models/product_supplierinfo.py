# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class SupplierInfo(models.Model):
    _name = 'product.supplierinfo'
    _description = 'Supplier Pricelist'
    _order = 'sequence, min_qty DESC, price, id'
    _rec_name = 'partner_id'


    def _default_product_id(self):
        product_id = self.env.get('default_product_id')
        if not product_id:
            model, active_id = [self.env.context.get(k) for k in ['model', 'active_id']]
            if model == 'product.product' and active_id:
                product_id = self.env[model].browse(active_id).exists()
        return product_id


    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company.id,
        index=1,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Vendor',
        required=True,
        check_company=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product Variant',
        default=_default_product_id,
        check_company=True,
        domain="[('product_tmpl_id', '=', product_tmpl_id)] if product_tmpl_id else []",
        help='If not set, the vendor price will apply to all variants of this product.',
    )
    product_tmpl_id = fields.Many2one(
        comodel_name='product.template',
        string='Product Template',
        check_company=True,
        index=True,
        ondelete='cascade',
    )
    product_uom = fields.Many2one(
        related='product_tmpl_id.uom_po_id',
        string='Unit of Measure',
    )
    product_variant_count = fields.Integer(
        related='product_tmpl_id.product_variant_count',
        string='Variant Count',
    )
    sequence = fields.Integer(
        string='Sequence',
        default=1,
        help='Assigns the priority to the list of product vendor.',
    )
    product_name = fields.Char(
        string='Vendor Product Name',
        help='This vendor\'s product name will be used when printing a request for quotation.'
             'Keep empty to use the internal one.'
    )
    product_code = fields.Char(
        string='Vendor Product Code',
        help='This vendor\'s product code will be used when printing a request for quotation.'
             'Keep empty to use the internal one.'
    )
    price = fields.Float(
        string='Price',
        digits='Product Price',
        required=True,
        default=0.0,
        help='The price to purchase a product',
    )
    discount = fields.Float(
        string='Discount (%)',
        digits='Discount',
        readonly=False,
    )
    price_discounted = fields.Float(
        string='Discounted Price',
        compute='_compute_price_discounted',
    )
    date_start = fields.Date(
        string='Start Date',
        help='Start date for this vendor price',
    )
    date_end = fields.Date(
        string='End Date',
        help='End date for this vendor price',
    )
    delay = fields.Integer(
        string='Delivery Lead Time',
        required=True,
        default=1,
        help='Lead time in days between the confirmation of the purchase order and the receipt of '
             'the products in your warehouse. Used by the scheduler for automatic computation of '
             'the purchase order planning.'
    )
    min_qty = fields.Float(
        string='Quantity',
        digits='Product Unit of Measure',
        required=True,
        default=0.0,
        help='The quantity to purchase from this vendor to benefit from the price, expressed in '
             'the vendor Product Unit of Measure if not any, in the default unit of measure of the '
             'product otherwise.',
    )


    def _sanitize_vals(self, vals):
        '''Sanitize vals to sync product variant & template on read/write.'''
        # add product's product_tmpl_id if none present in vals
        if  vals.get('product_id') and not vals.get('product_tmpl_id'):
            product = self.env['product.product'].browse(vals['product_id'])
            vals['product_tmpl_id'] = product.product_tmpl_id.id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sanitize_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._sanitize_vals(vals)
        return super().write(vals)

    @api.depends('discount', 'price')
    def _compute_price_discounted(self):
        for rec in self:
            rec.price_discounted = rec.price * (1 - rec.discount / 100)

    @api.onchange('product_tmpl_id')
    def _onchange_product_tmpl_id(self):
        '''Clear product variant if it no longer matches the product template.'''
        if self.product_id and self.product_id not in self.product_tmpl_id.product_variant_ids:
            self.product_id = False

    @api.model
    def get_import_templates(self):
        return [{
            'label': _('Import Template for Vendor Pricelists'),
            'template': '/product/static/xls/product_supplierinfo.xls'
        }]
