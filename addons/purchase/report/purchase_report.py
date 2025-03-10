from odoo import fields, models
from odoo.tools.query import Query
from odoo.tools.sql import SQL


class PurchaseReport(models.Model):
    _name = "purchase.report"
    _description = "Purchase Analysis Report"
    _auto = False
    _order = "date_order desc, price_total desc"

    # ------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------

    company_id = fields.Many2one("res.company", "Company", readonly=True)
    currency_id = fields.Many2one("res.currency", "Currency", readonly=True)
    order_id = fields.Many2one("purchase.order", "Order", readonly=True)
    partner_id = fields.Many2one("res.partner", "Vendor", readonly=True)
    commercial_partner_id = fields.Many2one(
        "res.partner", "Commercial Entity", readonly=True
    )
    country_id = fields.Many2one("res.country", "Partner Country", readonly=True)
    fiscal_position_id = fields.Many2one(
        "account.fiscal.position", string="Fiscal Position", readonly=True
    )
    user_id = fields.Many2one("res.users", "Buyer", readonly=True)
    date_order = fields.Datetime("Order Date", readonly=True)
    date_approve = fields.Datetime("Confirmation Date", readonly=True)
    delay = fields.Float(
        string="Days to Confirm",
        digits=(16, 2),
        readonly=True,
        aggregator="avg",
        help="Amount of time between purchase approval and order by date.",
    )
    delay_pass = fields.Float(
        string="Days to Receive",
        digits=(16, 2),
        readonly=True,
        aggregator="avg",
        help="Amount of time between date planned and order by date for each purchase order line.",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft RFQ"),
            ("to approve", "To Approve"),
            ("purchase", "Purchase Order"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        readonly=True,
    )
    product_id = fields.Many2one("product.product", "Product", readonly=True)
    product_tmpl_id = fields.Many2one(
        "product.template", "Product Template", readonly=True
    )
    category_id = fields.Many2one("product.category", "Product Category", readonly=True)
    product_uom_id = fields.Many2one(
        "uom.uom", "Reference Unit of Measure", readonly=True
    )
    nbr_lines = fields.Integer("# of Lines", readonly=True)
    price_average = fields.Monetary("Average Cost", readonly=True, aggregator="avg")
    untaxed_total = fields.Monetary("Untaxed Total", readonly=True)
    price_total = fields.Monetary("Total", readonly=True)
    qty_ordered = fields.Float("Qty Ordered", readonly=True)
    qty_transfered = fields.Float("Qty Received", readonly=True)
    qty_to_be_billed = fields.Float("Qty to be Billed", readonly=True)
    qty_billed = fields.Float("Qty Billed", readonly=True)
    weight = fields.Float("Gross Weight", readonly=True)
    volume = fields.Float("Volume", readonly=True)

    @property
    def _table_query(self) -> SQL:
        return SQL(
            "SELECT %s FROM %s WHERE %s GROUP BY %s",
            self._select(),
            self._from(),
            self._where(),
            self._group_by(),
        )

    def _select(self) -> SQL:
        return SQL(
            """
            o.company_id AS company_id,
            c.currency_id,
            o.id AS order_id,
            MIN(l.id) AS id,
            o.partner_id AS partner_id,
            partner.commercial_partner_id AS commercial_partner_id,
            partner.country_id AS country_id,
            o.fiscal_position_id AS fiscal_position_id,
            o.dest_address_id,
            o.user_id AS user_id,
            o.date_order AS date_order,
            o.date_approve,
            (
                EXTRACT(epoch from age(o.date_approve,o.date_order))
                / (24*60*60)::decimal(16,2)
            ) AS delay,
            (
                EXTRACT(epoch from age(l.date_planned,o.date_order))
                / (24*60*60)::decimal(16,2)
            ) AS delay_pass,
            o.state,
            l.product_id,
            p.product_tmpl_id,
            t.categ_id AS category_id,
            t.uom_id AS product_uom_id,
            SUM(
                l.product_qty * line_uom.factor / product_uom.factor
            ) AS qty_ordered,
            COUNT(*) AS nbr_lines,
            (
                SUM(l.product_qty * l.price_unit / COALESCE(o.currency_rate, 1.0))
                / NULLIF(SUM(l.product_qty / line_uom.factor * product_uom.factor), 0.0)
            )::decimal(16,2) * account_currency_table.rate AS price_average,
            (
                SUM(l.price_subtotal / COALESCE(o.currency_rate, 1.0))::decimal(16,2)
                * account_currency_table.rate
            ) AS untaxed_total,
            (
                SUM(l.price_total / COALESCE(o.currency_rate, 1.0))::decimal(16,2)
                * account_currency_table.rate
            ) AS price_total,
            SUM(
                l.qty_transfered * line_uom.factor / product_uom.factor
            ) AS qty_transfered,
            CASE WHEN t.bill_policy = 'purchase'
                THEN
                    SUM(l.product_qty / line_uom.factor * product_uom.factor)
                    - SUM(l.qty_invoiced / line_uom.factor * product_uom.factor)
                ELSE
                    SUM(l.qty_transfered / line_uom.factor * product_uom.factor)
                    - SUM(l.qty_invoiced / line_uom.factor * product_uom.factor)
            END AS qty_to_be_billed,
            SUM(
                l.qty_invoiced * line_uom.factor / product_uom.factor
            ) AS qty_billed,
            SUM(
                p.weight * l.product_qty / line_uom.factor * product_uom.factor
            ) AS weight,
            SUM(
                p.volume * l.product_qty / line_uom.factor * product_uom.factor
            ) AS volume
            """,
        )

    def _from(self) -> SQL:
        return SQL(
            """
            purchase_order_line l
            LEFT JOIN purchase_order o
                ON o.id=l.order_id
            LEFT JOIN res_partner partner
                ON o.partner_id = partner.id
            LEFT JOIN product_product p
                ON l.product_id=p.id
            LEFT JOIN product_template t
                ON p.product_tmpl_id=t.id
            LEFT JOIN uom_uom product_uom
                ON product_uom.id=t.uom_id
            LEFT JOIN res_company c
                ON c.id = o.company_id
            LEFT JOIN uom_uom line_uom
                ON line_uom.id=l.product_uom_id
            LEFT JOIN %(currency_table)s
                ON account_currency_table.company_id = o.company_id
            """,
            currency_table=self.env["res.currency"]._get_simple_currency_table(
                self.env.companies
            ),
        )

    def _where(self) -> SQL:
        return SQL(
            """
                l.display_type IS NULL
            """,
        )

    def _group_by(self) -> SQL:
        return SQL(
            """
            o.company_id,
            o.user_id,
            o.partner_id,
            line_uom.factor,
            c.currency_id,
            l.price_unit,
            o.date_approve,
            l.date_planned,
            l.product_uom_id,
            o.dest_address_id,
            o.fiscal_position_id,
            l.product_id,
            p.product_tmpl_id,
            t.categ_id,
            o.date_order,
            o.state,
            t.uom_id,
            t.bill_policy,
            line_uom.id,
            product_uom.factor,
            partner.country_id,
            partner.commercial_partner_id,
            o.id,
            account_currency_table.rate
            """,
        )

    def _read_group_select(self, aggregate_spec: str, query: Query) -> SQL:
        """This override allows us to correctly calculate
        the average price of products."""
        if aggregate_spec != "price_average:avg":
            return super()._read_group_select(aggregate_spec, query)

        return SQL(
            "SUM(%(f_price)s * %(f_qty)s) / NULLIF(SUM(%(f_qty)s), 0.0)",
            f_qty=self._field_to_sql(self._table, "qty_ordered", query),
            f_price=self._field_to_sql(self._table, "price_average", query),
        )
