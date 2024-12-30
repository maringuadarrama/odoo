# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockRoute(models.Model):
    _name = 'stock.route'
    _description = 'Inventory Routes'
    _order = 'sequence'
    _check_company_auto = True


    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        help='Leave this field empty if this route is shared between all companies',
    )
    name = fields.Char(string='Route', required=True, translate=True)
    active = fields.Boolean('Active', default=True,
        help='If the active field is set to False, it will allow you to hide the route without removing it.'
    )
    sequence = fields.Integer('Sequence', default=0)
    supplied_wh_id = fields.Many2one(
        'stock.warehouse',
        'Supplied Warehouse',
    )
    supplier_wh_id = fields.Many2one(
        'stock.warehouse',
        'Supplying Warehouse',
    )
    warehouse_domain_ids = fields.One2many(
        'stock.warehouse',
        compute='_compute_warehouses',
    )
    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        'stock_route_warehouse',
        'route_id',
        'warehouse_id',
        'Warehouses',
        domain=[('id', 'in', warehouse_domain_ids)],
        copy=False,
    )
    categ_ids = fields.Many2many(
        'product.category',
        'stock_route_categ',
        'route_id',
        'categ_id',
        'Product Categories',
        copy=False,
    )
    packaging_ids = fields.Many2many(
        'product.packaging',
        'stock_route_packaging',
        'route_id',
        'packaging_id',
        'Packagings',
        check_company=True,
        copy=False,
    )
    product_ids = fields.Many2many(
        'product.template',
        'stock_route_product',
        'route_id',
        'product_id',
        'Products',
        copy=False,
        check_company=True,
    )
    product_selectable = fields.Boolean(
        'Applicable on Product',
        default=True,
        help='When checked, the route will be selectable in the Inventory tab of the Product form.',
    )
    product_categ_selectable = fields.Boolean(
        'Applicable on Product Category',
        help='When checked, the route will be selectable on the Product Category.',
    )
    warehouse_selectable = fields.Boolean(
        'Applicable on Warehouse',
        help='When a warehouse is selected for this route, '
             'this route should be seen as the default route when products pass through this warehouse.',
    )
    packaging_selectable = fields.Boolean(
        'Applicable on Packaging',
        help='When checked, the route will be selectable on the Product Packaging.',
    )
    rule_ids = fields.One2many(
        'stock.rule',
        'route_id',
        'Rules',
        copy=True,
    )


    @api.constrains('company_id')
    def _check_company_consistency(self):
        for route in self:
            if not route.company_id:
                continue

            for rule in route.rule_ids:
                if route.company_id.id != rule.company_id.id:
                    raise ValidationError(_(
                        'Rule %(rule)s belongs to %(rule_company)s '
                        'while the route belongs to %(route_company)s.',
                        rule=rule.display_name,
                        rule_company=rule.company_id.display_name,
                        route_company=route.company_id.display_name,
                    ))

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default=default)
        if 'name' not in default:
            for route, vals in zip(self, vals_list):
                vals['name'] = _('%s (copy)', route.name)
        return vals_list

    def toggle_active(self):
        for route in self:
            route.with_context(active_test=False).rule_ids.filtered(
                lambda ru: ru.active == route.active
            ).toggle_active()
        super().toggle_active()

    @api.depends('company_id')
    def _compute_warehouses(self):
        for loc in self:
            domain = [('company_id', '=', loc.company_id.id)] if loc.company_id else []
            loc.warehouse_domain_ids = self.env['stock.warehouse'].search(domain)

    @api.onchange('company_id')
    def _onchange_company(self):
        if self.company_id:
            self.warehouse_ids = self.warehouse_ids.filtered(
                lambda w: w.company_id == self.company_id
            )

    @api.onchange('warehouse_selectable')
    def _onchange_warehouse_selectable(self):
        if not self.warehouse_selectable:
            self.warehouse_ids = [(5, 0, 0)]
