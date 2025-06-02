from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import SQL
from odoo.tools.translate import _


class PurchaseBillLineMatch(models.Model):
    _name = "purchase.bill.line.match"
    _description = "Purchase Line and Vendor Bill line matching view"
    _auto = False
    _order = "product_id, aml_id, pol_id"

    # ------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------

    company_id = fields.Many2one(comodel_name="res.company")
    currency_id = fields.Many2one(comodel_name="res.currency")
    partner_id = fields.Many2one(comodel_name="res.partner")
    purchase_order_id = fields.Many2one(comodel_name="purchase.order")
    pol_id = fields.Many2one(comodel_name="purchase.order.line")
    account_move_id = fields.Many2one(comodel_name="account.move")
    aml_id = fields.Many2one(comodel_name="account.move.line")
    state = fields.Char()
    product_id = fields.Many2one(comodel_name="product.product")
    product_uom_id = fields.Many2one(related="product_id.uom_id")
    line_uom_id = fields.Many2one(comodel_name="uom.uom")
    line_qty = fields.Float()
    product_uom_qty = fields.Float(
        compute="_compute_product_uom_qty",
        inverse="_inverse_product_uom_qty",
        readonly=False,
    )
    qty_to_invoice = fields.Float("Qty to invoice")
    qty_invoiced = fields.Float()
    product_uom_price = fields.Float(
        compute="_compute_product_uom_price",
        inverse="_inverse_product_uom_price",
        readonly=False,
    )
    line_amount_untaxed = fields.Monetary()
    amount_billed_untaxed = fields.Monetary(
        compute="_compute_amount_untaxed_fields",
        currency_field="currency_id",
    )
    amount_purchased_untaxed = fields.Monetary(
        compute="_compute_amount_untaxed_fields",
        currency_field="currency_id",
    )
    reference = fields.Char(compute="_compute_reference")

    # ------------------------------------------------------------
    # COMPUTE METHODS
    # ------------------------------------------------------------

    def _compute_amount_untaxed_fields(self):
        for line in self:
            line.amount_billed_untaxed = (
                line.line_amount_untaxed if line.account_move_id else False
            )
            line.amount_purchased_untaxed = (
                line.line_amount_untaxed if line.purchase_order_id else False
            )

    def _compute_display_name(self):
        for line in self:
            line.display_name = (
                line.product_id.display_name or line.aml_id.name or line.pol_id.name
            )

    def _compute_product_uom_qty(self):
        for line in self:
            line.product_uom_qty = line.line_uom_id._compute_quantity(
                line.line_qty, line.product_uom_id
            )

    def _compute_reference(self):
        for line in self:
            line.reference = (
                line.purchase_order_id.display_name or line.account_move_id.display_name
            )

    @api.depends("aml_id.price_unit", "pol_id.price_unit")
    def _compute_product_uom_price(self):
        for line in self:
            line.product_uom_price = (
                line.aml_id.price_unit if line.aml_id else line.pol_id.price_unit
            )

    # ------------------------------------------------------------
    # INVERSE METHODS
    # ------------------------------------------------------------

    @api.onchange("product_uom_price")
    def _inverse_product_uom_price(self):
        for line in self:
            if line.aml_id:
                line.aml_id.price_unit = line.product_uom_price
            else:
                line.pol_id.price_unit = line.product_uom_price

    @api.onchange("product_uom_qty")
    def _inverse_product_uom_qty(self):
        for line in self:
            if line.aml_id:
                line.aml_id.quantity = line.product_uom_qty
            else:
                # ON POL, setting product_qty will recompute price_unit to have the old value
                # this prevents the price to revert by saving the previous price and re-setting them again
                previous_price_unit = line.pol_id.price_unit
                line.pol_id.product_qty = line.product_uom_qty
                line.pol_id.price_unit = previous_price_unit

    # ------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------

    def action_open_line(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move" if self.account_move_id else "purchase.order",
            "view_mode": "form",
            "res_id": (
                self.account_move_id.id
                if self.account_move_id
                else self.purchase_order_id.id
            ),
        }

    def action_add_to_po(self):
        if not self or not self.aml_id:
            raise UserError(_("Select Vendor Bill lines to add to a Purchase Order"))

        context = {
            "default_partner_id": self.partner_id.id,
            "dialog_size": "medium",
            "has_products": bool(self.aml_id.product_id),
        }
        if len(self.purchase_order_id) > 1:
            raise UserError(
                _("Vendor Bill lines can only be added to one Purchase Order.")
            )

        elif self.purchase_order_id:
            context["default_purchase_order_id"] = self.purchase_order_id.id
        return {
            "name": _("Add to Purchase Order"),
            "type": "ir.actions.act_window",
            "res_model": "bill.to.po.wizard",
            "views": [(self.env.ref("purchase.bill_to_po_wizard_form").id, "form")],
            "target": "new",
            "context": context,
        }

    @api.model
    def _action_create_bill_from_po_lines(self, partner, po_lines):
        """Create a new vendor bill with the selected PO lines and returns an action to open it"""
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": partner.id,
            }
        )
        bill._add_purchase_order_lines(po_lines)
        return bill._get_records_action()

    def action_match_lines(self):
        if not self.pol_id:  # we need POL(s) to either match or create bill
            raise UserError(
                _(
                    "You must select at least one Purchase Order line to match or create bill."
                )
            )

        if (
            not self.aml_id
        ):  # select POL(s) without AML -> create a draft bill with the POL(s)
            return self._action_create_bill_from_po_lines(self.partner_id, self.pol_id)

        if (
            len(self.aml_id.move_id) > 1
        ):  # for purchase matching, disallow matching multiple bills at the same time
            raise UserError(
                _(
                    "You can't select lines from multiple Vendor Bill to do the matching."
                )
            )

        pol_by_product = self.pol_id.grouped("product_id")
        aml_by_product = self.aml_id.grouped("product_id")
        residual_purchase_order_lines = self.pol_id
        residual_account_move_lines = self.aml_id
        residual_bill = self.aml_id.move_id
        # Match all matchable POL-AML lines and remove them from the residual group
        for product, po_line in pol_by_product.items():
            po_line = po_line[
                0
            ]  # in case of multiple POL with same product, only match the first one
            matching_bill_lines = aml_by_product.get(product)
            if matching_bill_lines:
                matching_bill_lines.purchase_line_ids = [Command.set(po_line.ids)]
                residual_purchase_order_lines -= po_line
                residual_account_move_lines -= matching_bill_lines

        # Delete all unmatched selected AML
        if residual_account_move_lines:
            residual_account_move_lines.unlink()

        # Add all remaining POL to the residual bill
        if residual_purchase_order_lines:
            residual_bill._add_purchase_order_lines(residual_purchase_order_lines)

    # ------------------------------------------------------------
    # SQL
    # ------------------------------------------------------------

    @property
    def _table_query(self) -> SQL:
        return self._query()

    def _query(self) -> SQL:
        return SQL(
            "SELECT %s FROM %s WHERE %s UNION ALL SELECT %s FROM %s WHERE %s",
            self._select_pol(),
            self._from_pol(),
            self._where_pol(),
            self._select_aml(),
            self._from_aml(),
            self._where_aml(),
        )

    def _select_pol(self) -> SQL:
        return SQL(
            """
            pol.id,
            pol.id AS pol_id,
            NULL AS aml_id,
            pol.company_id AS company_id,
            pol.partner_id AS partner_id,
            po.id AS purchase_order_id,
            NULL AS account_move_id,
            pol.product_id AS product_id,
            pol.product_uom_id AS line_uom_id,
            pol.product_qty AS line_qty,
            pol.qty_invoiced AS qty_invoiced,
            pol.qty_to_invoice AS qty_to_invoice,
            pol.price_subtotal AS line_amount_untaxed,
            po.currency_id AS currency_id,
            po.state AS state
            """
        )

    def _from_pol(self) -> SQL:
        return SQL(
            """
            purchase_order_line pol
            LEFT JOIN purchase_order po ON pol.order_id = po.id
            """,
        )

    def _where_pol(self) -> SQL:
        return SQL(
            """
            po.state = 'purchase'
            AND (
                pol.product_qty > pol.qty_invoiced
                OR pol.qty_to_invoice != 0
            )
            OR (
                (pol.display_type = '' OR pol.display_type IS NULL)
                AND pol.is_downpayment
                AND pol.qty_invoiced > 0
            )
            """,
        )

    def _select_aml(self) -> SQL:
        return SQL(
            """
            -aml.id,
            NULL AS pol_id,
            aml.id AS aml_id,
            aml.company_id AS company_id,
            aml.partner_id AS partner_id,
            NULL AS purchase_order_id,
            am.id AS account_move_id,
            aml.product_id AS product_id,
            aml.product_uom_id AS line_uom_id,
            aml.quantity AS line_qty,
            NULL AS qty_invoiced,
            NULL AS qty_to_invoice,
            aml.amount_currency AS line_amount_untaxed,
            aml.currency_id AS currency_id,
            aml.parent_state AS state
            """
        )

    def _from_aml(self) -> SQL:
        return SQL(
            """
            account_move_line aml
            LEFT JOIN account_move am ON aml.move_id = am.id
            LEFT JOIN account_move_line_purchase_order_line_rel rel ON aml.id = rel.move_line_id
            """
        )

    def _where_aml(self) -> SQL:
        return SQL(
            """
            aml.display_type = 'product'
            AND am.move_type IN ('in_invoice', 'in_refund')
            AND aml.parent_state IN ('draft', 'posted')
            AND rel IS NULL
            """
        )
