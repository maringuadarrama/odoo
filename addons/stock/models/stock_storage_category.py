# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class StorageCategory(models.Model):
    _name = 'stock.storage.category'
    _description = 'Storage Category'
    _order = 'name'


    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
    )
    name = fields.Char('Storage Category', required=True)
    allow_new_product = fields.Selection(
        [
            ('empty', 'If the location is empty'),
            ('same', 'If all products are same'),
            ('mixed', 'Allow mixed products'),
        ],
        required=True,
        default='mixed',
    )
    max_weight = fields.Float(
        string='Max Weight',
        digits='Stock Weight',
    )
    weight_uom_name = fields.Char(
        string='Weight unit',
        compute='_compute_weight_uom_name',
    )
    location_ids = fields.One2many(
        comodel_name='stock.location',
        inverse_name='storage_category_id',
    )
    product_capacity_ids = fields.One2many(
        comodel_name='stock.storage.category.capacity',
        inverse='_set_storage_capacity_ids',
        compute='_compute_storage_capacity_ids',
    )
    package_capacity_ids = fields.One2many(
        comodel_name='stock.storage.category.capacity',
        inverse='_set_storage_capacity_ids',
        compute='_compute_storage_capacity_ids',
    )
    capacity_ids = fields.One2many(
        comodel_name='stock.storage.category.capacity',
        inverse_name='storage_category_id',
        copy=True,
    )


    _sql_constraints = [
        ('positive_max_weight', 'CHECK(max_weight >= 0)', 'Max weight should be a positive number.'),
    ]


    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [dict(vals, name=self.env._('%s (copy)', category.name)) for category, vals in zip(self, vals_list)]

    @api.depends('capacity_ids')
    def _compute_storage_capacity_ids(self):
        for storage_category in self:
            storage_category.product_capacity_ids = storage_category.capacity_ids.filtered(lambda c: c.product_id)
            storage_category.package_capacity_ids = storage_category.capacity_ids.filtered(lambda c: c.package_type_id)

    def _compute_weight_uom_name(self):
        self.weight_uom_name = self.env['product.template']._get_weight_uom_name_from_ir_config_parameter()

    def _set_storage_capacity_ids(self):
        for storage_category in self:
            storage_category.capacity_ids = storage_category.product_capacity_ids | storage_category.package_capacity_ids


class StorageCategoryProductCapacity(models.Model):
    _name = 'stock.storage.category.capacity'
    _description = 'Storage Category Capacity'
    _check_company_auto = True
    _order = 'storage_category_id'


    storage_category_id = fields.Many2one(
        comodel_name='stock.storage.category',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        related='storage_category_id.company_id', string='Company',
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        check_company=True,
        domain=("[('product_tmpl_id', '=', context.get('active_id', False))] if context.get('active_model') == 'product.template' else"
            " [('id', '=', context.get('default_product_id', False))] if context.get('default_product_id') else"
            " [('is_storable', '=', True)]"
        ),
        ondelete='cascade',
    )
    product_uom_id = fields.Many2one(related='product_id.uom_id')
    package_type_id = fields.Many2one(
        comodel_name='stock.package.type',
        string='Package Type',
        check_company=True,
        ondelete='cascade',
    )
    quantity = fields.Float('Quantity', required=True)


    _sql_constraints = [
        ('positive_quantity', 'CHECK(quantity > 0)', 'Quantity should be a positive number.'),
        ('unique_product', 'UNIQUE(product_id, storage_category_id)', 'Multiple capacity rules for one product.'),
        ('unique_package_type', 'UNIQUE(package_type_id, storage_category_id)', 'Multiple capacity rules for one package type.'),
    ]
