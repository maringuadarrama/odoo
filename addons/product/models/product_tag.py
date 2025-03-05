# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.osv import expression


class ProductTag(models.Model):
    _name = "product.tag"
    _description = "Product Tag"
    _order = "sequence, id"


    name = fields.Char(string="Name", required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Char(string="Color", default="#3C3C3C")
    product_template_ids = fields.Many2many(
        comodel_name="product.template",
        relation="product_tag_product_template_rel",
        string="Product Templates",
        default=lambda self: self._get_default_template_id(),
    )
    product_product_ids = fields.Many2many(
        comodel_name="product.product",
        relation="product_tag_product_product_rel",
        string="Product Variants",
        default=lambda self: self._get_default_variant_id(),
        domain=[("attribute_line_ids", "!=", False), ("product_tmpl_id", "not in", product_template_ids)],
    )
    product_ids = fields.Many2many(
        comodel_name="product.product",
        string="All Product Variants using this Tag",
        compute="_compute_product_ids",
        search="_search_product_ids"
    )


    # ------------------------------------------------------------
    # CONSTRAINT METHODS
    # ------------------------------------------------------------

    _name_uniq = models.Constraint(
        "unique (name)",
        "Tag name already exists!",
    )


    # ------------------------------------------------------------
    # CRUD METHODS
    # ------------------------------------------------------------

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [dict(vals, name=self.env._("%s (copy)", tag.name)) for tag, vals in zip(self, vals_list)]


    # ------------------------------------------------------------
    # COMPUTE METHODS
    # ------------------------------------------------------------

    @api.depends("product_template_ids", "product_product_ids")
    def _compute_product_ids(self):
        for tag in self:
            tag.product_ids = tag.product_template_ids.product_variant_ids | tag.product_product_ids


    # ------------------------------------------------------------
    # SEARCH METHODS
    # ------------------------------------------------------------

    def _search_product_ids(self, operator, operand):
        if operator in expression.NEGATIVE_TERM_OPERATORS:
            return [
                ("product_template_ids.product_variant_ids", operator, operand),
                ("product_product_ids", operator, operand)
            ]

        return [
            "|",
            ("product_template_ids.product_variant_ids", operator, operand),
            ("product_product_ids", operator, operand)
        ]


    # ------------------------------------------------------------
    # METHODS
    # ------------------------------------------------------------

    def _get_default_template_id(self):
        return self.env["product.template"].browse(self.env.context.get("product_template_id"))

    def _get_default_variant_id(self):
        return self.env["product.product"].browse(self.env.context.get("product_variant_id"))
