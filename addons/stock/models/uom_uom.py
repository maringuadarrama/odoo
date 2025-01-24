# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, models
from odoo.exceptions import UserError


class UoM(models.Model):
    _inherit = 'uom.uom'


    def write(self, values):
        # Users can not update the factor if open stock moves are based on it
        if 'factor' in values or 'factor_inv' in values or 'category_id' in values:
            changed = self.filtered(
                lambda u:
                    any(
                        u[f] != values[f] if f in values else False
                        for f in {'factor', 'factor_inv'}
                    )
            ) + self.filtered(
                lambda u:
                    any(
                        u[f].id != int(values[f]) if f in values else False
                        for f in {'category_id'}
                    )
            )
            if changed:
                error_msg = _(
                    'You cannot change the ratio of this unit of measure'
                    ' as some products with this UoM have already been moved'
                    ' or are currently reserved.'
                )
                if self.env['stock.move'].sudo().search_count([
                    ('product_uom', 'in', changed.ids),
                    ('state', 'not in', ('cancel', 'done'))
                ]):
                    raise UserError(error_msg)

                if self.env['stock.move.line'].sudo().search_count([
                    ('product_uom_id', 'in', changed.ids),
                    ('state', 'not in', ('cancel', 'done')),
                ]):
                    raise UserError(error_msg)

                if self.env['stock.quant'].sudo().search_count([
                    ('product_id.product_tmpl_id.uom_id', 'in', changed.ids),
                    ('quantity', '!=', 0),
                ]):
                    raise UserError(error_msg)

        return super(UoM, self).write(values)

    def _adjust_uom_quantities(self, qty, quant_uom):
        '''
        This method adjust the quantities of a procurement if its UoM isn't the same
        as the one of the quant and the parameter 'propagate_uom' is not set.
        '''
        procurement_uom = self
        computed_qty = qty
        get_param = self.env['ir.config_parameter'].sudo().get_param
        if get_param('stock.propagate_uom') != '1':
            computed_qty = self._compute_quantity(qty, quant_uom, rounding_method='HALF-UP')
            procurement_uom = quant_uom
        else:
            computed_qty = self._compute_quantity(qty, procurement_uom, rounding_method='HALF-UP')
        return (computed_qty, procurement_uom)
