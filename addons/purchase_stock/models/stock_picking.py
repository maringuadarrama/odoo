from odoo import api, fields, models


class StockPicking(models.Model):
    "Inherit StockPicking"

    _inherit = "stock.picking"

    purchase_id = fields.Many2one(
        related="move_ids.purchase_line_id.order_id",
        string="Purchase Orders",
        readonly=True,
    )
    days_to_arrive = fields.Datetime(
        compute="_compute_date_effective",
        search="_search_days_to_arrive",
        copy=False,
    )
    delay_pass = fields.Datetime(
        compute="_compute_date_order",
        search="_search_delay_pass",
        copy=False,
        index=True,
    )

    def _compute_date_order(self):
        for picking in self:
            picking.delay_pass = (
                picking.purchase_id.date_order
                if picking.purchase_id
                else fields.Datetime.now()
            )

    @api.depends("state", "location_dest_id.usage", "date_done")
    def _compute_date_effective(self):
        for picking in self:
            if (
                picking.state == "done"
                and picking.location_dest_id.usage != "supplier"
                and picking.date_done
            ):
                picking.days_to_arrive = picking.date_done
            else:
                picking.days_to_arrive = False

    @api.model
    def _search_days_to_arrive(self, operator, value):
        date_value = fields.Datetime.from_string(value)
        return [("date_done", operator, date_value)]

    @api.model
    def _search_delay_pass(self, operator, value):
        date_value = fields.Datetime.from_string(value)
        return [("purchase_id.date_order", operator, date_value)]
