# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Please note that these reports are not multi-currency !!!


from odoo import fields, models
from odoo.tools.query import Query
from odoo.tools.sql import SQL


class PurchaseReport(models.Model):
    _name = "purchase.report"
    _description = "Purchase Report"
    _auto = False
    _order = "date_order desc, price_total desc"


    company_id = fields.Many2one("res.company", "Company", readonly=True)
    currency_id = fields.Many2one("res.currency", "Currency", readonly=True)
    date_order = fields.Datetime("Order Date", readonly=True)
    state = fields.Selection(
        [
            ("draft", "Draft RFQ"),
            ("sent", "RFQ Sent"),
            ("to approve", "To Approve"),
            ("purchase", "Purchase Order"),
            ("done", "Done"),
            ("cancel", "Cancelled")
        ],
        string="Status",
        readonly=True,
    )
    partner_id = fields.Many2one("res.partner", "Vendor", readonly=True)
    user_id = fields.Many2one("res.users", "Buyer", readonly=True)
    product_id = fields.Many2one("product.product", "Product", readonly=True)
    product_uom_id = fields.Many2one("uom.uom", "Reference Unit of Measure", readonly=True)
    date_approve = fields.Datetime("Confirmation Date", readonly=True)
    delay = fields.Float("Days to Confirm", digits=(16, 2), readonly=True, aggregator="avg",
        help="Amount of time between purchase approval and order by date.",
    )
    delay_pass = fields.Float("Days to Receive", digits=(16, 2), readonly=True, aggregator="avg",
        help="Amount of time between date planned and order by date for each purchase order line.",
    )
    price_total = fields.Monetary("Total", readonly=True)
    price_average = fields.Monetary("Average Cost", readonly=True, aggregator="avg")
    nbr_lines = fields.Integer("# of Lines", readonly=True)
    category_id = fields.Many2one("product.category", "Product Category", readonly=True)
    product_tmpl_id = fields.Many2one("product.template", "Product Template", readonly=True)
    country_id = fields.Many2one("res.country", "Partner Country", readonly=True)
    fiscal_position_id = fields.Many2one("account.fiscal.position", string="Fiscal Position", readonly=True)
    commercial_partner_id = fields.Many2one("res.partner", "Commercial Entity", readonly=True)
    weight = fields.Float("Gross Weight", readonly=True)
    volume = fields.Float("Volume", readonly=True)
    order_id = fields.Many2one("purchase.order", "Order", readonly=True)
    untaxed_total = fields.Monetary("Untaxed Total", readonly=True)
    qty_ordered = fields.Float("Qty Ordered", readonly=True)
    qty_received = fields.Float("Qty Received", readonly=True)
    qty_billed = fields.Float("Qty Billed", readonly=True)
    qty_to_be_billed = fields.Float("Qty to be Billed", readonly=True)


    @property
    def _table_query(self) -> SQL:
        """Report needs to be dynamic to take into account 
        multi-company selected + multi-currency rates"""
        return SQL("%s %s %s %s", self._select(), self._from(), self._where(), self._group_by())

    def _select(self) -> SQL:
        return SQL(
            """
            SELECT
                po.id AS order_id,
                min(l.id) AS id,
                po.date_order AS date_order,
                po.state,
                po.date_approve,
                po.dest_address_id,
                po.partner_id AS partner_id,
                po.user_id AS user_id,
                po.company_id AS company_id,
                po.fiscal_position_id AS fiscal_position_id,
                l.product_id,
                p.product_tmpl_id,
                t.categ_id AS category_id,
                c.currency_id,
                t.uom_id AS product_uom_id,
                extract(epoch from age(po.date_approve,po.date_order))/(24*60*60)::decimal(16,2) AS delay,
                extract(epoch from age(l.date_planned,po.date_order))/(24*60*60)::decimal(16,2) AS delay_pass,
                count(*) AS nbr_lines,
                SUM(l.price_total / COALESCE(po.currency_rate, 1.0))::decimal(16,2) * account_currency_table.rate AS price_total,
                (SUM(l.product_qty * l.price_unit / COALESCE(po.currency_rate, 1.0))/NULLIF(SUM(l.product_qty/line_uom.factor*product_uom.factor),0.0))::decimal(16,2) * account_currency_table.rate AS price_average,
                partner.country_id AS country_id,
                partner.commercial_partner_id AS commercial_partner_id,
                SUM(p.weight * l.product_qty/line_uom.factor*product_uom.factor) AS weight,
                SUM(p.volume * l.product_qty/line_uom.factor*product_uom.factor) AS volume,
                SUM(l.price_subtotal / COALESCE(po.currency_rate, 1.0))::decimal(16,2) * account_currency_table.rate AS untaxed_total,
                SUM(l.product_qty * line_uom.factor / product_uom.factor) AS qty_ordered,
                SUM(l.qty_received * line_uom.factor / product_uom.factor) AS qty_received,
                SUM(l.qty_invoiced * line_uom.factor / product_uom.factor) AS qty_billed,
                CASE WHEN t.purchase_method = 'purchase'
                    THEN SUM(l.product_qty / line_uom.factor * product_uom.factor) - SUM(l.qty_invoiced / line_uom.factor * product_uom.factor)
                    ELSE SUM(l.qty_received / line_uom.factor * product_uom.factor) - SUM(l.qty_invoiced / line_uom.factor * product_uom.factor)
                END AS qty_to_be_billed
            """,
        )

    def _from(self) -> SQL:
        return SQL(
            """
            FROM
                purchase_order_line l
            JOIN purchase_order po ON (l.order_id=po.id)
            JOIN res_partner partner ON po.partner_id = partner.id
                LEFT JOIN product_product p ON (l.product_id=p.id)
                    LEFT JOIN product_template t ON (p.product_tmpl_id=t.id)
            LEFT JOIN res_company C ON C.id = po.company_id
            LEFT JOIN uom_uom line_uom ON (line_uom.id=l.product_uom_id)
            LEFT JOIN uom_uom product_uom ON (product_uom.id=t.uom_id)
            LEFT JOIN %(currency_table)s ON account_currency_table.company_id = po.company_id
            """,
            currency_table=self.env["res.currency"]._get_simple_currency_table(self.env.companies),
        )

    def _where(self) -> SQL:
        return SQL(
            """
            WHERE
                l.display_type IS NULL
            """,
        )

    def _group_by(self) -> SQL:
        return SQL(
            """
            GROUP BY
                po.company_id,
                po.user_id,
                po.partner_id,
                line_uom.factor,
                c.currency_id,
                l.price_unit,
                po.date_approve,
                l.date_planned,
                l.product_uom_id,
                po.dest_address_id,
                po.fiscal_position_id,
                l.product_id,
                p.product_tmpl_id,
                t.categ_id,
                po.date_order,
                po.state,
                t.uom_id,
                t.purchase_method,
                line_uom.id,
                product_uom.factor,
                partner.country_id,
                partner.commercial_partner_id,
                po.id,
                account_currency_table.rate
            """,
        )

    def _read_group_select(self, aggregate_spec: str, query: Query) -> SQL:
        """This override allows us to correctly calculate 
        the average price of products."""
        if aggregate_spec != "price_average:avg":
            return super()._read_group_select(aggregate_spec, query)
        return SQL(
            "SUM(%(f_price)s * %(f_qty)s) / SUM(%(f_qty)s)",
            f_qty=self._field_to_sql(self._table, "qty_ordered", query),
            f_price=self._field_to_sql(self._table, "price_average", query),
        )
