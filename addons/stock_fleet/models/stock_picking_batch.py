# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"


    vehicle_id = fields.Many2one(
        comodel_name="fleet.vehicle",
        string="Vehicle"
    )
    vehicle_category_id = fields.Many2one(
        comodel_name="fleet.vehicle.model.category",
        string="Vehicle Category",
        compute="_compute_vehicle_category_id", store=True,
        readonly=False,
    )
    driver_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Driver",
        compute="_compute_driver_id", store=True,
        readonly=False,
    )
    dock_id = fields.Many2one(
        comodel_name="stock.location",
        string="Dock Location",
        compute="_compute_dock_id", store=True,
        readonly=False,
        domain="[('warehouse_id', '=', warehouse_id), ('is_a_dock', '=', True)]",
    )
    vehicle_weight_capacity = fields.Float(
        related="vehicle_category_id.weight_capacity",
        string="Vehcilce Payload Capacity",
    )
    weight_uom_name = fields.Char(
        string="Weight unit of measure label",
        compute="_compute_weight_uom_name",
    )
    vehicle_volume_capacity = fields.Float(
        related="vehicle_category_id.volume_capacity",
        string="Max Volume (m³)",
    )
    volume_uom_name = fields.Char(
        string="Volume unit of measure label",
        compute="_compute_volume_uom_name",
    )
    used_weight_percentage = fields.Float(
        string="Weight %",
        compute="_compute_capacity_percentage",
    )
    used_volume_percentage = fields.Float(
        string="Volume %",
        compute="_compute_capacity_percentage",
    )
    end_date = fields.Datetime(
        string="End Date",
        default=fields.Datetime.now,
    )


    # ------------------------------------------------------------
    # CRUD METHODS
    # ------------------------------------------------------------

    def create(self, vals_list):
        batches = super().create(vals_list)
        batches.order_on_zip()
        batches.filtered(lambda b: b.dock_id)._set_moves_destination_to_dock()
        return batches

    def write(self, vals):
        res = super().write(vals)
        if "dock_id" in vals:
            self._set_moves_destination_to_dock()
        return res


    # ------------------------------------------------------------
    # COMPUTE METHODS
    # ------------------------------------------------------------

    @api.depends("vehicle_id")
    def _compute_vehicle_category_id(self):
        for batch in self:
            batch.vehicle_category_id = batch.vehicle_id.category_id

    @api.depends("vehicle_id")
    def _compute_driver_id(self):
        for batch in self:
            batch.driver_id = batch.vehicle_id.driver_id

    @api.depends("vehicle_id")
    def _compute_odometer_uom_id(self):
        for batch in self:
            batch.odometer_uom_id = batch.vehicle_id.odometer_uom_id

    @api.depends("vehicle_id")
    def _compute_odometer(self):
        for batch in self:
            batch.odometer = batch.vehicle_id.odometer

    @api.depends(
        "picking_ids", "picking_ids.location_id", "picking_ids.location_dest_id"
    )
    def _compute_dock_id(self):
        for batch in self:
            if batch.picking_ids:
                if (
                    len(batch.picking_ids.location_id) == 1
                    and batch.picking_ids.location_id.is_a_dock
                ):
                    batch.dock_id = batch.picking_ids.location_id

    def _compute_weight_uom_name(self):
        self.weight_uom_name = self.env[
            "product.template"
        ]._get_weight_uom_name_from_ir_config_parameter()

    def _compute_volume_uom_name(self):
        self.volume_uom_name = self.env[
            "product.template"
        ]._get_volume_uom_name_from_ir_config_parameter()

    @api.depends(
        "estimated_shipping_weight",
        "vehicle_category_id.weight_capacity",
        "estimated_shipping_volume",
        "vehicle_category_id.volume_capacity",
    )
    def _compute_capacity_percentage(self):
        self.used_weight_percentage = False
        self.used_volume_percentage = False
        for batch in self:
            if batch.vehicle_weight_capacity:
                batch.used_weight_percentage = 100 * (
                    batch.estimated_shipping_weight / batch.vehicle_weight_capacity
                )
            if batch.vehicle_volume_capacity:
                batch.used_volume_percentage = 100 * (
                    batch.estimated_shipping_volume / batch.vehicle_volume_capacity
                )

    # Public actions
    def order_on_zip(self):
        sorted_pickings = self.picking_ids.sorted(lambda p: p.zip or "")
        for idx, picking in enumerate(sorted_pickings):
            picking.batch_sequence = idx

    # Private buisness logic
    def _set_moves_destination_to_dock(self):
        for batch in self:
            if not batch.dock_id:
                batch.picking_ids._reset_location()
            elif batch.picking_type_id.code in ["internal", "incoming"]:
                batch.picking_ids.move_ids.write({"location_dest_id": batch.dock_id.id})
            else:
                batch.picking_ids.move_ids.write({"location_id": batch.dock_id.id})
