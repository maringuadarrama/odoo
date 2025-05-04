from odoo import fields, models


class ResCompany(models.Model):
    """Inherit ResCompany"""

    _inherit = "res.company"

    # ------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------

    po_lock = fields.Selection(
        selection=[
            ("edit", "Allow to edit purchase orders"),
            ("lock", "Confirmed purchase orders are not editable"),
        ],
        string="Purchase Order Modification",
        default="edit",
        help="Purchase Order Modification used when you want to purchase order editable after confirm",
    )
    po_double_validation = fields.Selection(
        selection=[
            ("one_step", "Confirm purchase orders in one step"),
            ("two_step", "Get 2 levels of approvals to confirm a purchase order"),
        ],
        string="Levels of Approvals",
        default="one_step",
        help="Provide a double validation mechanism for purchases",
    )
    po_double_validation_amount = fields.Monetary(
        string="Double validation amount",
        default=5000,
        help="Minimum amount for which a double validation is required",
    )
    po_lead = fields.Float(
        string="Purchase Lead Time",
        default=0.0,
        required=True,
        help="Margin of error for vendor lead times. When the system "
        "generates Purchase Orders for procuring products, "
        "they will be scheduled that many days earlier "
        "to cope with unexpected vendor delays.",
    )
