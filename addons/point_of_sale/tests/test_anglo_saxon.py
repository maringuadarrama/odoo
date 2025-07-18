# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class TestAngloSaxonCommon(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.PosMakePayment = cls.env['pos.make.payment']
        cls.PosOrder = cls.env['pos.order']
        cls.Statement = cls.env['account.bank.statement']
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.partner = cls.env['res.partner'].create({'name': 'Partner 1'})
        cls.category = cls.env.ref('product.product_category_services')
        cls.category = cls.category.copy({'name': 'New category','property_valuation': 'real_time'})
        cls.account = cls.env['account.account'].create({'name': 'Receivable', 'code': 'RCV00', 'account_type': 'asset_receivable', 'reconcile': True})
        account_expense = cls.env['account.account'].create({'name': 'Expense', 'code': 'EXP00', 'account_type': 'expense', 'reconcile': True})
        account_income = cls.env['account.account'].create({'name': 'Income', 'code': 'INC00', 'account_type': 'income', 'reconcile': True})
        account_output = cls.env['account.account'].create({'name': 'Output', 'code': 'OUT00', 'account_type': 'expense', 'reconcile': True})
        account_valuation = cls.env['account.account'].create({'name': 'Valuation', 'code': 'STV00', 'account_type': 'expense', 'reconcile': True})
        cls.partner.property_account_receivable_id = cls.account
        cls.category.property_account_income_categ_id = account_income
        cls.category.property_account_expense_categ_id = account_expense
        cls.category.property_stock_account_input_categ_id = cls.account
        cls.category.property_stock_account_output_categ_id = account_output
        cls.category.property_stock_valuation_account_id = account_valuation
        cls.category.property_stock_journal = cls.env['account.journal'].create({'name': 'Stock journal', 'type': 'sale', 'code': 'STK00'})
        cls.cash_journal = cls.env['account.journal'].create(
            {'name': 'CASH journal', 'type': 'cash', 'code': 'CSH02'})
        cls.cash_payment_method = cls.env['pos.payment.method'].create({
            'name': 'Cash Test',
            'journal_id': cls.cash_journal.id,
        })
        cls.pos_config = cls.env['pos.config'].create({
            'name': 'New POS config',
            'payment_method_ids': cls.cash_payment_method,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'New product',
            'standard_price': 100,
            'available_in_pos': True,
            'is_storable': True,
        })
        cls.company.anglo_saxon_accounting = True
        cls.company.point_of_sale_update_stock_quantities = 'real'
        cls.product.categ_id = cls.category
        cls.product.property_account_expense_id = account_expense
        cls.product.property_account_income_id = account_income
        sale_journal = cls.env['account.journal'].create({'name': 'POS journal', 'type': 'sale', 'code': 'POS00'})
        cls.pos_config.journal_id = sale_journal
        cls.cash_journal = cls.env['account.journal'].create({'name': 'CASH journal', 'type': 'cash', 'code': 'CSH00'})
        cls.sale_journal = cls.env['account.journal'].create({'name': 'SALE journal', 'type': 'sale', 'code': 'INV00'})
        cls.pos_config.invoice_journal_id = cls.sale_journal
        cls.cash_payment_method = cls.env['pos.payment.method'].create({
            'name': 'Cash Test',
            'journal_id': cls.cash_journal.id,
            'receivable_account_id': cls.account.id,
        })
        cls.pos_config.write({'payment_method_ids': [(6, 0, cls.cash_payment_method.ids)]})

@tagged('post_install', '-at_install')
class TestAngloSaxonFlow(TestAngloSaxonCommon):

    def test_create_account_move_line(self):
        # This test will check that the correct journal entries are created when a product in real time valuation
        # is sold in a company using anglo-saxon
        self.pos_config.open_ui()
        current_session = self.pos_config.current_session_id
        self.cash_journal.loss_account_id = self.account
        current_session.set_opening_control(0, None)

        # I create a PoS order with 1 unit of New product at 450 EUR
        self.pos_order_pos0 = self.PosOrder.create({
            'company_id': self.company.id,
            'partner_id': self.partner.id,
            'pricelist_id': self.company.partner_id.property_product_pricelist.id,
            'session_id': self.pos_config.current_session_id.id,
            'lines': [(0, 0, {
                'name': "OL/0001",
                'product_id': self.product.id,
                'price_unit': 450,
                'discount': 0.0,
                'qty': 1.0,
                'price_subtotal': 450,
                'price_subtotal_incl': 450,
            })],
            'amount_total': 450,
            'amount_tax': 0,
            'amount_paid': 0,
            'amount_return': 0,
            'last_order_preparation_change': '{}'
        })

        # I make a payment to fully pay the order
        context_make_payment = {"active_ids": [self.pos_order_pos0.id], "active_id": self.pos_order_pos0.id}
        self.pos_make_payment_0 = self.PosMakePayment.with_context(context_make_payment).create({
            'amount': 450.0,
            'payment_method_id': self.cash_payment_method.id,
        })

        # I click on the validate button to register the payment.
        context_payment = {'active_id': self.pos_order_pos0.id}
        self.pos_make_payment_0.with_context(context_payment).check()

        # I check that the order is marked as paid
        self.assertEqual(self.pos_order_pos0.state, 'paid', 'Order should be in paid state.')
        self.assertEqual(self.pos_order_pos0.amount_paid, 450, 'Amount paid for the order should be updated.')

        # I close the current session to generate the journal entries
        current_session_id = self.pos_config.current_session_id
        current_session_id.post_closing_cash_details(450.0)
        current_session_id.close_session_from_ui()
        self.assertEqual(current_session_id.state, 'closed', 'Check that session is closed')

        # Check if there is account_move in the order.
        # There shouldn't be because the order is not invoiced.
        self.assertFalse(self.pos_order_pos0.account_move, 'There should be no invoice in the order.')

        # I test that the generated journal entries are correct.
        account_output = self.category.property_stock_account_output_categ_id
        expense_account = self.category.property_account_expense_categ_id
        aml = current_session.move_id.line_ids
        aml_output = aml.filtered(lambda l: l.account_id.id == account_output.id)
        aml_expense = aml.filtered(lambda l: l.account_id.id == expense_account.id)
        self.assertEqual(aml_output.credit, self.product.standard_price, "Cost of Good Sold entry missing or mismatching")
        self.assertEqual(aml_expense.debit, self.product.standard_price, "Cost of Good Sold entry missing or mismatching")

    def _prepare_pos_order(self):
        """ Set the cost method of `self.product` as FIFO. Receive 5@5 and 5@1 and
        create a `pos.order` record selling 7 units @ 450.
        """
        # check fifo Costing Method of product.category
        self.product.categ_id.property_cost_method = 'fifo'
        self.product.standard_price = 5.0
        self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': self.product.id,
            'inventory_quantity': 5.0,
            'location_id': self.warehouse.lot_stock_id.id,
        }).action_apply_inventory()
        self.product.standard_price = 1.0
        self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': self.product.id,
            'inventory_quantity': 10.0,
            'location_id': self.warehouse.lot_stock_id.id,
        }).action_apply_inventory()
        self.assertEqual(self.product.value_svl, 30, "Value should be (5*5 + 5*1) = 30")
        self.assertEqual(self.product.quantity_svl, 10)


        self.pos_config.open_ui()
        pos_session = self.pos_config.current_session_id
        pos_session.set_opening_control(0, None)

        pos_order_values = {
            'company_id': self.company.id,
            'partner_id': self.partner.id,
            'pricelist_id': self.company.partner_id.property_product_pricelist.id,
            'session_id': self.pos_config.current_session_id.id,
            'lines': [(0, 0, {
                'name': "OL/0001",
                'product_id': self.product.id,
                'price_unit': 450,
                'discount': 0.0,
                'qty': 7.0,
                'price_subtotal': 7 * 450,
                'price_subtotal_incl': 7 * 450,
            })],
            'amount_total': 7 * 450,
            'amount_tax': 0,
            'amount_paid': 0,
            'amount_return': 0,
            'last_order_preparation_change': '{}'
        }

        return self.PosOrder.create(pos_order_values)

    def test_fifo_valuation_no_invoice(self):
        """Register a payment and validate a session after selling a fifo
        product without making an invoice for the customer"""
        pos_order_pos0 = self._prepare_pos_order()
        context_make_payment = {"active_ids": [pos_order_pos0.id], "active_id": pos_order_pos0.id}
        self.pos_make_payment_0 = self.PosMakePayment.with_context(context_make_payment).create({
            'amount': 7 * 450.0,
            'payment_method_id': self.cash_payment_method.id,
        })

        # register the payment
        context_payment = {'active_id': pos_order_pos0.id}
        self.pos_make_payment_0.with_context(context_payment).check()

        # validate the session
        current_session_id = self.pos_config.current_session_id
        current_session_id.post_closing_cash_details(7 * 450.0)
        current_session_id.close_session_from_ui()

        # check the anglo saxon move lines
        # with uninvoiced orders, the account_move field of pos.order is empty.
        # the accounting lines are in move_id of pos.session.
        session_move = pos_order_pos0.session_id.move_id
        line = session_move.line_ids.filtered(lambda l: l.debit and l.account_id == self.category.property_account_expense_categ_id)
        self.assertEqual(session_move.journal_id, self.pos_config.journal_id)
        self.assertEqual(line.debit, 27, 'As it is a fifo product, the move\'s value should be 5*5 + 2*1')

    def test_fifo_valuation_with_invoice(self):
        """Register a payment and validate a session after selling a fifo
        product and make an invoice for the customer"""
        pos_order_pos0 = self._prepare_pos_order()
        context_make_payment = {"active_ids": [pos_order_pos0.id], "active_id": pos_order_pos0.id}
        self.pos_make_payment_0 = self.PosMakePayment.with_context(context_make_payment).create({
            'amount': 7 * 450.0,
            'payment_method_id': self.cash_payment_method.id,
        })

        # register the payment
        context_payment = {'active_id': pos_order_pos0.id}
        self.pos_make_payment_0.with_context(context_payment).check()

        # Create the customer invoice
        pos_order_pos0.action_pos_order_invoice()

        # check the anglo saxon move lines
        line = pos_order_pos0.account_move.line_ids.filtered(lambda l: l.debit and l.account_id == self.category.property_account_expense_categ_id)
        self.assertEqual(pos_order_pos0.account_move.journal_id, self.pos_config.invoice_journal_id)
        self.assertEqual(line.debit, 27, 'As it is a fifo product, the move\'s value should be 5*5 + 2*1')

    def test_cogs_with_ship_later_no_invoicing(self):
        # This test will check that the correct journal entries are created when a product in real time valuation
        # is sold using the ship later option and no invoice is created in a company using anglo-saxon
        self.pos_config.open_ui()
        current_session = self.pos_config.current_session_id
        self.cash_journal.loss_account_id = self.account
        current_session.set_opening_control(0, None)

        # 2 step delivery method
        self.warehouse.delivery_steps = 'pick_ship'

        # I create a PoS order with 1 unit of New product at 450 EUR
        self.pos_order_pos0 = self.PosOrder.create({
            'company_id': self.company.id,
            'partner_id': self.partner.id,
            'pricelist_id': self.company.partner_id.property_product_pricelist.id,
            'session_id': self.pos_config.current_session_id.id,
            'to_invoice': False,
            'shipping_date': '2023-01-01',
            'lines': [(0, 0, {
                'name': "OL/0001",
                'product_id': self.product.id,
                'price_unit': 450,
                'discount': 0.0,
                'qty': 1.0,
                'price_subtotal': 450,
                'price_subtotal_incl': 450,
            })],
            'amount_total': 450,
            'amount_tax': 0,
            'amount_paid': 0,
            'amount_return': 0,
            'last_order_preparation_change': '{}'
        })

        # I make a payment to fully pay the order
        context_make_payment = {"active_ids": [self.pos_order_pos0.id], "active_id": self.pos_order_pos0.id}
        self.pos_make_payment_0 = self.PosMakePayment.with_context(context_make_payment).create({
            'amount': 450.0,
            'payment_method_id': self.cash_payment_method.id,
        })

        # I click on the validate button to register the payment.
        context_payment = {'active_id': self.pos_order_pos0.id}
        self.pos_make_payment_0.with_context(context_payment).check()

        # I close the current session to generate the journal entries
        current_session_id = self.pos_config.current_session_id
        current_session_id.post_closing_cash_details(450.0)
        current_session_id.close_session_from_ui()
        self.assertEqual(current_session_id.state, 'closed', 'Check that session is closed')

        self.assertEqual(len(current_session.picking_ids), 1, "There should be 2 pickings")
        current_session.picking_ids.move_ids_without_package.write({'quantity': 1, 'picked': True})
        current_session.picking_ids.button_validate()
        self.assertEqual(len(current_session.picking_ids), 2, "There should be 2 pickings")
        current_session.picking_ids.button_validate()

        # I test that the generated journal entries are correct.
        account_output = self.category.property_stock_account_output_categ_id
        expense_account = self.category.property_account_expense_categ_id
        aml = current_session._get_related_account_moves().line_ids
        aml_output = aml.filtered(lambda l: l.account_id.id == account_output.id)
        aml_expense = aml.filtered(lambda l: l.account_id.id == expense_account.id)

        self.assertEqual(len(aml_output), 2, "There should be 2 output account move lines")
        # 2 moves in POS journal (Pos order + manual entry at delivery)
        self.assertEqual(len(aml_output.move_id.filtered(lambda l: l.journal_id == self.pos_config.journal_id)), 1)
        # 1 move in stock journal (delivery from stock layers)
        self.assertEqual(len(aml_output.move_id.filtered(lambda l: l.journal_id == self.category.property_stock_journal)), 1)
        #Check the lines created after the picking validation
        self.assertEqual(aml_output[1].credit, self.product.standard_price, "Cost of Good Sold entry missing or mismatching")
        self.assertEqual(aml_output[1].debit, 0.0, "Cost of Good Sold entry missing or mismatching")
        self.assertEqual(aml_expense[0].debit, self.product.standard_price, "Cost of Good Sold entry missing or mismatching")
        self.assertEqual(aml_expense[0].credit, 0.0, "Cost of Good Sold entry missing or mismatching")
        #Check the lines created by the PoS session
        self.assertEqual(aml_output[0].debit, 100.0, "Cost of Good Sold entry missing or mismatching")
        self.assertEqual(aml_output[0].credit, 0.0, "Cost of Good Sold entry missing or mismatching")

    def test_action_pos_order_invoice(self):
        self.company.point_of_sale_update_stock_quantities = 'closing'

        # Setup a running session, with a paid pos order that is not invoiced
        self.pos_config.open_ui()
        current_session = self.pos_config.current_session_id
        self.pos_order_pos0 = self.PosOrder.create({
            'company_id': self.company.id,
            'partner_id': self.partner.id,
            'session_id': self.pos_config.current_session_id.id,
            'lines': [(0, 0, {
                'product_id': self.product.id,
                'price_unit': 450,
                'qty': 1.0,
                'price_subtotal': 450,
                'price_subtotal_incl': 450,
            })],
            'amount_total': 450,
            'amount_tax': 0,
            'amount_paid': 0,
            'amount_return': 0,
        })
        context_make_payment = {"active_ids": [self.pos_order_pos0.id], "active_id": self.pos_order_pos0.id}
        self.pos_make_payment_0 = self.PosMakePayment.with_context(context_make_payment).create({
            'amount': 450.0,
            'payment_method_id': self.cash_payment_method.id,
        })
        context_payment = {'active_id': self.pos_order_pos0.id}
        self.pos_make_payment_0.with_context(context_payment).check()

        # Invoice the pos order afterward (session still running)
        self.pos_order_pos0.action_pos_order_invoice()

        # Check that the stock output journal item from the invoice is reconciled (with its counterpart from the valuation entry)
        stock_output_account = self.category.property_stock_account_output_categ_id
        related_amls = current_session._get_related_account_moves().line_ids
        stock_output_amls = related_amls.filtered_domain([('account_id', '=', stock_output_account.id)])

        self.assertTrue(all(stock_output_amls.mapped('reconciled')))

    def test_action_pos_order_invoice_with_discount(self):
        """This test make sure that the line containing 'Discoun from' is correctly added to the invoice"""

        # Setup a running session, with a paid pos order that is not invoiced
        self.pos_config.open_ui()
        pricelist = self.env['product.pricelist'].create({
            'name': 'Test Pricelist',
            'item_ids': [
                Command.create({
                    'compute_price': 'percentage',
                    'percent_price': '5.0',
                    'min_quantity': 0,
                    'applied_on': '3_global',
                })
            ],
        })
        self.product.lst_price = 100
        self.pos_order_pos0 = self.PosOrder.create({
            'company_id': self.company.id,
            'partner_id': self.partner.id,
            'session_id': self.pos_config.current_session_id.id,
            'pricelist_id': pricelist.id,
            'lines': [(0, 0, {
                'product_id': self.product.id,
                'price_unit': 95,
                'qty': 1.0,
                'tax_ids': [(6, 0, self.tax_purchase_a.ids)],
                'price_subtotal': 90.25,
                'price_subtotal_incl': 103.79,
                'discount': 5,
            })],
            'amount_total': 103.79,
            'amount_tax': 13.51,
            'amount_paid': 0,
            'amount_return': 0,
            'to_invoice': True,
        })
        context_make_payment = {"active_ids": [self.pos_order_pos0.id], "active_id": self.pos_order_pos0.id}
        self.pos_make_payment_0 = self.PosMakePayment.with_context(context_make_payment).create({
            'amount': 450.0,
            'payment_method_id': self.cash_payment_method.id,
        })
        context_payment = {'active_id': self.pos_order_pos0.id}
        self.pos_make_payment_0.with_context(context_payment).check()

        res = self.pos_order_pos0.action_pos_order_invoice()
        invoice = self.env['account.move'].browse(res['res_id'])
        self.assertTrue('Price discount from 100.00 to 95.00' in invoice.invoice_line_ids.filtered(lambda l: l.display_type == "line_note").display_name)
        product_line = invoice.invoice_line_ids.filtered(lambda l: l.display_type == "product")
        self.assertEqual(product_line.price_unit, 95)  # Only pricelist applies
        self.assertEqual(product_line.discount, 5)  # Disount is reflected
        self.assertEqual(product_line.price_subtotal, 90.25)  # Discount applies on price_unit
        self.assertEqual(product_line.price_total, 103.79)  # Taxes applied with price_total

    def test_cogs_with_ship_later_with_backorder(self):
        # This test will check that the correct journal entries are created when 2 products are sold
        # using the ship later option and one of them is processed in a backorder
        self.pos_config.open_ui()
        current_session = self.pos_config.current_session_id
        self.cash_journal.loss_account_id = self.account
        current_session.set_opening_control(0, None)

        # Create 2 product one with no cost and one with a cost of 20 EUR
        self.product_2 = self.env['product.product'].create({
            'name': 'New product 2',
            'standard_price': 20,
            'available_in_pos': True,
            'is_storable': True,
            'categ_id': self.category.id,
        })

        self.product_1 = self.env['product.product'].create({
            'name': 'New product 1',
            'standard_price': 0,
            'available_in_pos': True,
            'is_storable': True,
            'categ_id': self.category.id,
        })

        # I create a PoS order with 1 unit of New product at 450 EUR
        self.pos_order_pos0 = self.PosOrder.create({
            'company_id': self.company.id,
            'partner_id': self.partner.id,
            'pricelist_id': self.company.partner_id.property_product_pricelist.id,
            'session_id': self.pos_config.current_session_id.id,
            'to_invoice': False,
            'shipping_date': '2023-01-01',
            'lines': [(0, 0, {
                'name': "OL/0001",
                'product_id': self.product_1.id,
                'price_unit': 100,
                'discount': 0.0,
                'qty': 1.0,
                'price_subtotal': 100,
                'price_subtotal_incl': 100,
            }), (0, 0, {
                'name': "OL/0002",
                'product_id': self.product_2.id,
                'price_unit': 200,
                'discount': 0.0,
                'qty': 1.0,
                'price_subtotal': 200,
                'price_subtotal_incl': 200,
            })],
            'amount_total': 300,
            'amount_tax': 0,
            'amount_paid': 0,
            'amount_return': 0,
            'last_order_preparation_change': '{}'
        })

        # I make a payment to fully pay the order
        context_make_payment = {"active_ids": [self.pos_order_pos0.id], "active_id": self.pos_order_pos0.id}
        self.pos_make_payment_0 = self.PosMakePayment.with_context(context_make_payment).create({
            'amount': 300.0,
            'payment_method_id': self.cash_payment_method.id,
        })

        # I click on the validate button to register the payment.
        context_payment = {'active_id': self.pos_order_pos0.id}
        self.pos_make_payment_0.with_context(context_payment).check()

        # I close the current session to generate the journal entries
        current_session_id = self.pos_config.current_session_id
        current_session_id.post_closing_cash_details(300.0)
        current_session_id.close_session_from_ui()
        self.assertEqual(current_session_id.state, 'closed', 'Check that session is closed')

        current_session.picking_ids.move_ids_without_package.filtered(lambda m: m.product_id == self.product_2).write({'quantity': 1, 'picked': True})
        res_dict = current_session.picking_ids.button_validate()
        self.env['stock.backorder.confirmation'].with_context(res_dict['context']).process()

        # I test that the generated journal entries are correct.
        out = self.product_1.categ_id.property_stock_account_output_categ_id
        exp = self.product_1._get_product_accounts()['expense']
        aml = current_session._get_related_account_moves().line_ids
        aml_output = aml.filtered(lambda l: l.account_id.id == out.id and l.journal_id == self.pos_config.journal_id)
        aml_expense = aml.filtered(lambda l: l.account_id.id == exp.id and l.journal_id == self.pos_config.journal_id)

        self.assertEqual(len(aml_expense), 1, "There should be 1 output account move lines")
        self.assertEqual(aml_expense.debit, 20)
        self.assertEqual(aml_expense.credit, 0)

        self.assertEqual(len(aml_output), 1, "There should be 1 output account move lines")
        self.assertEqual(aml_output.debit, 0)
        self.assertEqual(aml_output.credit, 20)

        backorder_picking = current_session.picking_ids.filtered(lambda p: p.state == 'confirmed')
        backorder_picking.move_ids_without_package.write({'quantity': 1, 'picked': True})
        backorder_picking.button_validate()

        # As the second item has no cost, the account move line should be the same as before
        aml = current_session._get_related_account_moves().line_ids
        aml_output = aml.filtered(lambda l: l.account_id.id == out.id and l.journal_id == self.pos_config.journal_id)
        aml_expense = aml.filtered(lambda l: l.account_id.id == exp.id and l.journal_id == self.pos_config.journal_id)

        self.assertEqual(len(aml_expense), 1, "There should be 1 output account move lines")
        self.assertEqual(aml_expense.debit, 20)
        self.assertEqual(aml_expense.credit, 0)

        self.assertEqual(len(aml_output), 1, "There should be 1 output account move lines")
        self.assertEqual(aml_output.debit, 0)
        self.assertEqual(aml_output.credit, 20)
