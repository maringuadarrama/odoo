from odoo import api, models


class ProductSupplierinfo(models.Model):
    """Inherit ProductSupplierinfo"""

    _inherit = "product.supplierinfo"

    # -------------------------------------------------------------------------
    # ONCHANGE METHODS
    # -------------------------------------------------------------------------

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        self.currency_id = (
            self.partner_id.property_purchase_currency_id.id
            or self.env.company.currency_id.id
        )

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    def _get_filtered_supplier(self, company_id, product_id, params):
        if params and "order_id" in params and params["order_id"].company_id:
            company_id = params["order_id"].company_id
        return super()._get_filtered_supplier(company_id, product_id, params)
