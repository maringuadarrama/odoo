# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict
from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.addons.stock.models.procurement_exception import ProcurementException
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class StockRule(models.Model):
    ''' A rule describe what a procurement should do; produce, buy, move, ... '''
    _name = 'stock.rule'
    _description = 'Stock Rule'
    _order = 'sequence, id'
    _check_company_auto = True


    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'company_id' in fields_list and not res['company_id']:
            res['company_id'] = self.env.company.id
        return res


    route_id = fields.Many2one(
        comodel_name='stock.route',
        string='Route',
        required=True,
        ondelete='cascade',
        index=True,
    )
    route_company_id = fields.Many2one(
        related='route_id.company_id', string='Route Company'
    )
    route_sequence = fields.Integer(
        related='route_id.sequence', string='Route Sequence', store=True, compute_sudo=True
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        domain=[('id', '=?', route_company_id)]
    )
    group_id = fields.Many2one(
        comodel_name='procurement.group',
        string='Fixed Procurement Group',
    )
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
        check_company=True,
        index=True,
    )
    propagate_warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse to Propagate',
        help='The warehouse to propagate on the created move/procurement, which can be different '
             'of the warehouse this rule is for (e.g for resupplying rules from another warehouse)'
    )
    partner_address_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner Address',
        check_company=True,
        help='Address where goods should be delivered. Optional.',
    )
    picking_type_code_domain = fields.Char(compute='_compute_picking_type_code_domain')
    picking_type_id = fields.Many2one(
        comodel_name='stock.picking.type',
        string='Operation Type',
        required=True,
        check_company=True,
        domain=[('code', '=?', picking_type_code_domain)]
    )
    location_dest_id = fields.Many2one(
        comodel_name='stock.location',
        string='Destination Location',
        required=True,
        check_company=True,
        index=True,
    )
    location_src_id = fields.Many2one(
        comodel_name='stock.location',
        string='Source Location',
        check_company=True,
        index=True,
    )
    name = fields.Char(
        string='Name',
        required=True,
        translate=True,
        help='This field will fill the packing origin and the name of its moves',
    )
    sequence = fields.Integer('Sequence', default=20)
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, it will allow you to hide the rule without removing it.',
    )
    procure_method = fields.Selection(
        [
            ('make_to_stock', 'Take From Stock'),
            ('make_to_order', 'Trigger Another Rule'),
            ('mts_else_mto', 'Take From Stock, if unavailable, Trigger Another Rule')
        ],
        string='Supply Method',
        required=True,
        default='make_to_stock',
        help='Take From Stock: the products will be taken from the available stock of '
             'the source location.\n'
             'Trigger Another Rule: the system will try to find a stock rule to bring the products '
             'in the source location. The available stock will be ignored.\n'
             'Take From Stock, if Unavailable, Trigger Another Rule: the products will be taken '
             'from the available stock of the source location.'
             'If there is no stock available, the system will try to find a  rule to bring '
             'the products in the source location.'
    )
    action = fields.Selection(
        selection=[
            ('pull', 'Pull From'),
            ('push', 'Push To'),
            ('pull_push', 'Pull & Push')
        ],
        string='Action',
        required=True,
        default='pull',
        index=True,
    )
    auto = fields.Selection(
        [
            ('manual', 'Manual Operation'),
            ('transparent', 'Automatic No Step Added')
        ],
        string='Automatic Move',
        required=True,
        default='manual',
        help='The \'Manual Operation\' value will create a stock move after the current one. '
             'With \'Automatic No Step Added\', the location is replaced in the original move.'
    )
    group_propagation_option = fields.Selection(
        [
            ('none', 'Leave Empty'),
            ('propagate', 'Propagate'),
            ('fixed', 'Fixed')
        ],
        string='Propagation of Procurement Group',
        default='propagate',
    )
    delay = fields.Integer(
        string='Lead Time',
        default=0,
        help='The expected date of the created transfer will be computed based on this lead time.'
    )
    location_dest_from_rule = fields.Boolean(
        string='Destination location origin from rule',
        default=False,
        help='When set to True the destination location of the stock.move will be the rule.'
             'Otherwise, it takes it from the picking type.'
    )
    propagate_cancel = fields.Boolean(
        string='Cancel Next Move',
        default=False,
        help='When ticked, if the move created by this rule is cancelled, the next move will be cancelled too.'
    )
    propagate_carrier = fields.Boolean(
        string='Propagation of carrier',
        default=False,
        help='When ticked, carrier of shipment will be propagated.'
    )
    rule_message = fields.Html(compute='_compute_action_message')
    push_domain = fields.Char('Push Applicability')


    @api.constrains('company_id')
    def _check_company_consistency(self):
        for rule in self:
            route = rule.route_id
            if route.company_id and rule.company_id.id != route.company_id.id:
                raise ValidationError(_(
                    'Rule %(rule)s belongs to %(rule_company)s '
                    'while the route belongs to %(route_company)s.',
                    rule=rule.display_name,
                    rule_company=rule.company_id.display_name,
                    route_company=route.company_id.display_name,
                ))

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default=default)
        if 'name' not in default:
            for rule, vals in zip(self, vals_list):
                vals['name'] = _('%s (copy)', rule.name)
        return vals_list

    @api.depends(
        'picking_type_id', 'location_dest_id', 'location_src_id',
        'action', 'procure_method', 'location_dest_from_rule'
    )
    def _compute_action_message(self):
        '''
        Generate dynamicaly a message that describe the rule purpose to the
        end user.
        '''
        action_rules = self.filtered(lambda rule: rule.action)
        for rule in action_rules:
            message_dict = rule._get_message_dict()
            message = message_dict.get(rule.action) and message_dict[rule.action] or ''
            if rule.action == 'pull_push':
                message = message_dict['pull'] + '<br/><br/>' + message_dict['push']
            rule.rule_message = message
        (self - action_rules).rule_message = None

    @api.depends('action')
    def _compute_picking_type_code_domain(self):
        self.picking_type_code_domain = False

    @api.onchange('picking_type_id')
    def _onchange_picking_type(self):
        '''
        Modify locations to the default picking type's locations source and
        destination.
        Enable the delay alert if the picking type is a delivery
        '''
        self.location_src_id = self.picking_type_id.default_location_src_id.id
        self.location_dest_id = self.picking_type_id.default_location_dest_id.id

    @api.onchange('route_id', 'company_id')
    def _onchange_route(self):
        '''
        Ensure that the rule's company is the same than the route's company.
        '''
        if self.route_id.company_id:
            self.company_id = self.route_id.company_id
        if self.picking_type_id.warehouse_id.company_id != self.route_id.company_id:
            self.picking_type_id = False

    def _get_message_values(self):
        '''
        Return the source, destination and picking_type applied on a stock
        rule. The purpose of this function is to avoid code duplication in
        _get_message_dict functions since it often requires those data.
        '''
        source = self.location_src_id and self.location_src_id.display_name or _('Source Location')
        destination = self.location_dest_id and self.location_dest_id.display_name or _('Destination Location')
        direct_destination = (
            self.picking_type_id
            and self.picking_type_id.default_location_dest_id != self.location_dest_id
            and self.picking_type_id.default_location_dest_id.display_name
        )
        operation = self.picking_type_id and self.picking_type_id.name or _('Operation Type')
        return source, destination, direct_destination, operation

    def _get_message_dict(self):
        '''
        Return a dict with the different possible message used for the
        rule message. It should return one message for each stock.rule action
        (except push and pull). This function is override in mrp and
        purchase_stock in order to complete the dictionary.
        '''
        message_dict = {}
        source, destination, direct_destination, operation = self._get_message_values()
        if self.action in ('push', 'pull', 'pull_push'):
            suffix = ''
            if (
                self.action in ('pull', 'pull_push')
                and direct_destination
                and not self.location_dest_from_rule
            ):
                suffix = _(
                    "<br>The products will be moved towards <b>%(destination)s</b>, "
                    "<br/> as specified from <b>%(operation)s</b> destination.",
                    destination=direct_destination, operation=operation
                )
            if self.procure_method == 'make_to_order' and self.location_src_id:
                suffix += _(
                    "<br>A need is created in <b>%s</b> and a rule will be triggered to fulfill it.",
                    source
                )
            if self.procure_method == 'mts_else_mto' and self.location_src_id:
                suffix += _(
                    "<br>If the products are not available in <b>%s</b>, a rule will be triggered "
                    "to bring the missing quantity in this location.",
                    source
                )
            message_dict = {
                'pull': _(
                    'When products are needed in <b>%(destination)s</b>, <br> <b>%(operation)s</b> '
                    'are created from <b>%(source_location)s</b> to fulfill the need.',
                    destination=destination,
                    operation=operation,
                    source_location=source,
                    suffix=suffix,
                ),
                'push': _(
                    'When products arrive in <b>%(source_location)s</b>, <br> <b>%(operation)s</b> '
                    'are created to send them to <b>%(destination)s</b>.',
                    source_location=source,
                    operation=operation,
                    destination=destination,
                ),
            }
        return message_dict

    def _run_push(self, move):
        '''
        Apply a push rule on a move.
        If the rule is 'no step added' it will modify the destination location
        on the move.
        If the rule is 'manual operation' it will generate a new move in order
        to complete the section define by the rule.
        Care this function is not call by method run. It is called explicitely
        in stock_move.py inside the method _push_apply
        '''
        self.ensure_one()
        new_date = fields.Datetime.to_string(move.date + relativedelta(days=self.delay))
        if self.auto == 'transparent':
            old_dest_location = move.location_dest_id
            move.write({'date': new_date, 'location_dest_id': self.location_dest_id.id})
            # make sure the location_dest_id is consistent with the move line location dest
            if move.move_line_ids:
                move.move_line_ids.location_dest_id = move.location_dest_id._get_putaway_strategy(move.product_id) or move.location_dest_id

            # avoid looping if a push rule is not well configured; otherwise call again push_apply to see if a next step is defined
            if self.location_dest_id != old_dest_location:
                # TDE FIXME: should probably be done in the move model IMO
                return move._push_apply()[:1]
        else:
            new_move_vals = self._push_prepare_move_copy_values(move, new_date)
            new_move = move.sudo().copy(new_move_vals)
            if new_move._should_bypass_reservation():
                new_move.write({'procure_method': 'make_to_stock'})
            if not new_move.location_id.should_bypass_reservation():
                move.write({'move_dest_ids': [(4, new_move.id)]})
            return new_move

    def _push_prepare_move_copy_values(self, move_to_copy, new_date):
        company_id = self.company_id.id
        copied_quantity = move_to_copy.quantity
        if float_compare(move_to_copy.product_uom_qty, 0, precision_rounding=move_to_copy.product_uom.rounding) < 0:
            copied_quantity = move_to_copy.product_uom_qty
        if not company_id:
            company_id = self.sudo().warehouse_id and self.sudo().warehouse_id.company_id.id or self.sudo().picking_type_id.warehouse_id.company_id.id
        new_move_vals = {
            'product_uom_qty': copied_quantity,
            'origin': move_to_copy.origin or move_to_copy.picking_id.name or '/',
            'location_id': move_to_copy.location_dest_id.id,
            'location_dest_id': self.location_dest_id.id,
            'location_final_id': move_to_copy.location_final_id.id,
            'rule_id': self.id,
            'date': new_date,
            'date_deadline': move_to_copy.date_deadline,
            'company_id': company_id,
            'picking_id': False,
            'picking_type_id': self.picking_type_id.id,
            'propagate_cancel': self.propagate_cancel,
            'warehouse_id': self.warehouse_id.id,
            'procure_method': 'make_to_order',
        }
        return new_move_vals

    @api.model
    def _run_pull(self, procurements):
        moves_values_by_company = defaultdict(list)

        # To handle the `mts_else_mto` procure method, we do a preliminary loop to
        # isolate the products we would need to read the forecasted quantity,
        # in order to to batch the read. We also make a sanitary check on the
        # `location_src_id` field.
        for procurement, rule in procurements:
            if not rule.location_src_id:
                msg = _('No source location defined on stock rule: %s!', rule.name)
                raise ProcurementException([(procurement, msg)])

        # Prepare the move values, adapt the `procure_method` if needed.
        procurements = sorted(procurements, key=lambda proc: float_compare(proc[0].product_qty, 0.0, precision_rounding=proc[0].product_uom.rounding) > 0)
        for procurement, rule in procurements:
            procure_method = rule.procure_method
            if rule.procure_method == 'mts_else_mto':
                procure_method = 'make_to_stock'

            move_values = rule._get_stock_move_values(*procurement)
            move_values['procure_method'] = procure_method
            moves_values_by_company[procurement.company_id.id].append(move_values)

        for company_id, moves_values in moves_values_by_company.items():
            # create the move as SUPERUSER because the current user may not have the rights to do it (mto product launched by a sale for example)
            moves = self.env['stock.move'].with_user(SUPERUSER_ID).sudo().with_company(company_id).create(moves_values)
            # Since action_confirm launch following procurement_group we should activate it.
            moves._action_confirm()
        return True

    def _get_custom_move_fields(self):
        '''
        The purpose of this method is to be override in order to easily add
        fields from procurement 'values' argument to move data.
        '''
        return []

    def _get_stock_move_values(self, product_id, product_qty, product_uom, location_dest_id, name, origin, company_id, values):
        ''' Returns a dictionary of values that will be used to create a stock move from a procurement.
        This function assumes that the given procurement has a rule (action == 'pull' or 'pull_push') set on it.

        :param procurement: browse record
        :rtype: dictionary
        '''
        group_id = False
        if self.group_propagation_option == 'propagate':
            group_id = values.get('group_id', False) and values['group_id'].id
        elif self.group_propagation_option == 'fixed':
            group_id = self.group_id.id

        date_scheduled = fields.Datetime.to_string(
            fields.Datetime.from_string(values['date_planned']) - relativedelta(days=self.delay or 0)
        )
        date_deadline = values.get('date_deadline') and (fields.Datetime.to_datetime(values['date_deadline']) - relativedelta(days=self.delay or 0)) or False
        partner = self.partner_address_id or (values.get('group_id', False) and values['group_id'].partner_id)
        if partner:
            product_id = product_id.with_context(lang=partner.lang or self.env.user.lang)
        picking_description = product_id._get_description(self.picking_type_id)
        if values.get('product_description_variants'):
            picking_description += values['product_description_variants']
        # it is possible that we've already got some move done, so check for the done qty and create
        # a new move with the correct qty
        qty_left = product_qty

        move_dest_ids = []
        if not self.location_dest_id.should_bypass_reservation():
            move_dest_ids = values.get('move_dest_ids', False) and [(4, x.id) for x in values['move_dest_ids']] or []

        # when create chained moves for inter-warehouse transfers, set the warehouses as partners
        if not partner and move_dest_ids:
            move_dest = values['move_dest_ids']
            if location_dest_id == company_id.internal_transit_location_id:
                partners = move_dest.location_dest_id.warehouse_id.partner_id
                if len(partners) == 1:
                    partner = partners
                move_dest.partner_id = self.location_src_id.warehouse_id.partner_id or self.company_id.partner_id

        # If the quantity is negative the move should be considered as a refund
        if float_compare(product_qty, 0.0, precision_rounding=product_uom.rounding) < 0:
            values['to_refund'] = True

        move_values = {
            'name': name[:2000],
            'company_id': self.company_id.id or self.location_src_id.company_id.id or self.location_dest_id.company_id.id or company_id.id,
            'product_id': product_id.id,
            'product_uom': product_uom.id,
            'product_uom_qty': qty_left,
            'partner_id': partner.id if partner else False,
            'location_id': self.location_src_id.id,
            'location_final_id': location_dest_id.id,
            'move_dest_ids': move_dest_ids,
            'rule_id': self.id,
            'procure_method': self.procure_method,
            'origin': origin,
            'picking_type_id': self.picking_type_id.id,
            'group_id': group_id,
            'route_ids': [(4, route.id) for route in values.get('route_ids', [])],
            'never_product_template_attribute_value_ids': values.get('never_product_template_attribute_value_ids'),
            'warehouse_id': self.warehouse_id.id,
            'date': date_scheduled,
            'date_deadline': False if self.group_propagation_option == 'fixed' else date_deadline,
            'propagate_cancel': self.propagate_cancel,
            'description_picking': picking_description,
            'priority': values.get('priority', '0'),
            'orderpoint_id': values.get('orderpoint_id') and values['orderpoint_id'].id,
            'product_packaging_id': values.get('product_packaging_id') and values['product_packaging_id'].id,
        }
        if self.location_dest_from_rule:
            move_values['location_dest_id'] = self.location_dest_id.id
        for field in self._get_custom_move_fields():
            if field in values:
                move_values[field] = values.get(field)
        return move_values

    def _get_lead_days(self, product, **values):
        '''
        Returns the cumulative delay and its description encountered by a
        procurement going through the rules in `self`.

        :param product: the product of the procurement
        :type product: :class:`~odoo.addons.product.models.product.ProductProduct`
        :return: the cumulative delay and cumulative delay's description
        :rtype: tuple[defaultdict(float), list[str, str]]
        '''
        _ = self.env._
        delays = defaultdict(float)
        delay = sum(self.filtered(lambda r: r.action in ['pull', 'pull_push']).mapped('delay'))
        delays['total_delay'] += delay
        global_visibility_days = self.env.context.get('global_visibility_days', 0)
        if global_visibility_days:
            delays['total_delay'] += int(global_visibility_days)
        if self.env.context.get('bypass_delay_description'):
            delay_description = []
        else:
            delay_description = [
                (_('Delay on %s', rule.name), _('+ %d day(s)', rule.delay))
                for rule in self
                if rule.action in ['pull', 'pull_push'] and rule.delay
            ]
        if global_visibility_days:
            delay_description.append((_('Time Horizon'), _('+ %d day(s)', int(global_visibility_days))))
        return delays, delay_description
