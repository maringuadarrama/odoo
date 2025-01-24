# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from collections import defaultdict, namedtuple, OrderedDict

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.addons.stock.models.procurement_exception import ProcurementException
from odoo.exceptions import UserError
from odoo.modules.registry import Registry
from odoo.osv import expression
from odoo.sql_db import BaseCursor
from odoo.tools import float_is_zero
from odoo.tools.misc import split_every

_logger = logging.getLogger(__name__)

class ProcurementGroup(models.Model):
    '''
    The procurement group class is used to group products together
    when computing procurements. (tasks, physical products, ...)

    The goal is that when you have one sales order of several products
    and the products are pulled from the same or several location(s), to keep
    having the moves grouped into pickings that represent the sales order.

    Used in: sales order (to group delivery order lines like the so), pull/push
    rules (to pack like the delivery order), on orderpoints (e.g. for wave picking
    all the similar products together).

    Grouping is made only if the source and the destination is the same.
    Suppose you have 4 lines on a picking from Output where 2 lines will need
    to come from Input (crossdock) and 2 lines coming from Stock -> Output As
    the four will have the same group ids from the SO, the move from input will
    have a stock.picking with 2 grouped lines and the move from stock will have
    2 grouped lines also.

    The name is usually the name of the original document (sales order) or a
    sequence computed if created manually.
    '''
    _name = 'procurement.group'
    _description = 'Procurement Group'
    _order = 'id desc'

    Procurement = namedtuple(
        'Procurement',
        [
            'product_id', 'product_qty', 'product_uom',
            'location_id', 'name', 'origin', 'company_id', 'values'
        ]
    )


    partner_id = fields.Many2one(
        'res.partner',
        'Partner',
    )
    name = fields.Char(
        'Reference',
        default=lambda self: self.env['ir.sequence'].next_by_code('procurement.group') or '',
        required=True,
    )
    move_type = fields.Selection(
        [('direct', 'Partial'), ('one', 'All at once')],
        string='Delivery Type'
    )
    stock_move_ids = fields.One2many(
        'stock.move',
        'group_id',
        string='Related Stock Moves',
    )


    @api.model
    def _skip_procurement(self, procurement):
        return procurement.product_id.type != 'consu' or float_is_zero(
            procurement.product_qty, precision_rounding=procurement.product_uom.rounding
        )

    @api.model
    def run(self, procurements, raise_user_error=True):
        '''Fulfil `procurements` with the help of stock rules.

        Procurements are needs of products at a certain location. To fulfil
        these needs, we need to create some sort of documents (`stock.move`
        by default, but extensions of `_run_` methods allow to create every
        type of documents).

        :param procurements: the description of the procurement
        :type list: list of `~odoo.addons.stock.models.stock_rule.ProcurementGroup.Procurement`
        :param raise_user_error: will raise either an UserError or a ProcurementException
        :type raise_user_error: boolan, optional
        :raises UserError: if `raise_user_error` is True and a procurement isn't fulfillable
        :raises ProcurementException: if `raise_user_error` is False and a procurement isn't fulfillable
        '''

        def raise_exception(procurement_errors):
            if raise_user_error:
                dummy, errors = zip(*procurement_errors)
                raise UserError('\n'.join(errors))
            else:
                raise ProcurementException(procurement_errors)
        actions_to_run = defaultdict(list)
        procurement_errors = []
        for procurement in procurements:
            procurement.values.setdefault('company_id', procurement.location_id.company_id)
            procurement.values.setdefault('priority', '0')
            procurement.values.setdefault('date_planned', procurement.values.get('date_planned', False) or fields.Datetime.now())
            if self._skip_procurement(procurement):
                continue
            rule = self._get_rule(procurement.product_id, procurement.location_id, procurement.values)
            if not rule:
                error = _('No rule has been found to replenish \'%(product)s\' in \'%(location)s\'.\nVerify the routes configuration on the product.',
                    product=procurement.product_id.display_name, location=procurement.location_id.display_name)
                procurement_errors.append((procurement, error))
            else:
                action = 'pull' if rule.action == 'pull_push' else rule.action
                actions_to_run[action].append((procurement, rule))

        if procurement_errors:
            raise_exception(procurement_errors)

        for action, procurements in actions_to_run.items():
            if hasattr(self.env['stock.rule'], '_run_%s' % action):
                try:
                    getattr(self.env['stock.rule'], '_run_%s' % action)(procurements)
                except ProcurementException as e:
                    procurement_errors += e.procurement_exceptions
            else:
                _logger.error('The method _run_%s doesn\'t exist on the procurement rules' % action)

        if procurement_errors:
            raise_exception(procurement_errors)
        return True

    @api.model
    def _search_rule_for_warehouses(self, route_ids, packaging_id, product_id, warehouse_ids, domain):
        if warehouse_ids:
            domain = expression.AND([['|', ('warehouse_id', 'in', warehouse_ids.ids), ('warehouse_id', '=', False)], domain])
        valid_route_ids = set()
        if route_ids:
            valid_route_ids |= set(route_ids.ids)
        if packaging_id:
            packaging_routes = packaging_id.route_ids
            valid_route_ids |= set(packaging_routes.ids)
        valid_route_ids |= set((product_id.route_ids | product_id.categ_id.total_route_ids).ids)
        if warehouse_ids:
            valid_route_ids |= set(warehouse_ids.route_ids.ids)
        if valid_route_ids:
            domain = expression.AND([[('route_id', 'in', list(valid_route_ids))], domain])
        res = self.env['stock.rule']._read_group(
            domain,
            groupby=['location_dest_id', 'warehouse_id', 'route_id'],
            aggregates=['id:recordset'],
            order='route_sequence:min, sequence:min',
        )
        rule_dict = defaultdict(OrderedDict)
        for group in res:
            rule_dict[group[0].id, group[2].id][group[1].id] = group[3].sorted(lambda rule: (rule.route_sequence, rule.sequence))[0]
        return rule_dict

    def _search_rule(self, route_ids, packaging_id, product_id, warehouse_id, domain):
        '''
        First find a rule among the ones defined on the procurement
        group, then try on the routes defined for the product, finally fallback
        on the default behavior
        '''
        if warehouse_id:
            domain = expression.AND([['|', ('warehouse_id', '=', warehouse_id.id), ('warehouse_id', '=', False)], domain])
        Rule = self.env['stock.rule']
        res = self.env['stock.rule']
        if route_ids:
            res = Rule.search(expression.AND([[('route_id', 'in', route_ids.ids)], domain]), order='route_sequence, sequence', limit=1)
        if not res and packaging_id:
            packaging_routes = packaging_id.route_ids
            if packaging_routes:
                res = Rule.search(expression.AND([[('route_id', 'in', packaging_routes.ids)], domain]), order='route_sequence, sequence', limit=1)
        if not res:
            product_routes = product_id.route_ids | product_id.categ_id.total_route_ids
            if product_routes:
                res = Rule.search(expression.AND([[('route_id', 'in', product_routes.ids)], domain]), order='route_sequence, sequence', limit=1)
        if not res and warehouse_id:
            warehouse_routes = warehouse_id.route_ids
            if warehouse_routes:
                res = Rule.search(expression.AND([[('route_id', 'in', warehouse_routes.ids)], domain]), order='route_sequence, sequence', limit=1)
        return res

    @api.model
    def _get_rule(self, product_id, location_id, values):
        '''
        Find a pull rule for the location_id, fallback on the parent
        locations if it could not be found.
        '''
        result = self.env['stock.rule']
        if not location_id:
            return result
        locations = location_id
        # Get the location hierarchy, starting from location_id up to its root location.
        while locations[-1].location_id:
            locations |= locations[-1].location_id
        domain = self._get_rule_domain(locations, values)
        # Get a mapping (location_id, route_id) -> warehouse_id -> rule_id
        rule_dict = self._search_rule_for_warehouses(
            values.get('route_ids', False),
            values.get('product_packaging_id', False),
            product_id,
            values.get('warehouse_id', locations.warehouse_id),
            domain,
        )

        def extract_rule(rule_dict, route_ids, warehouse_id, location_dest_id):
            rule = self.env['stock.rule']
            for route_id in route_ids:
                sub_dict = rule_dict.get((location_dest_id.id, route_id.id))
                if not sub_dict:
                    continue
                if not warehouse_id:
                    rule = sub_dict[next(iter(sub_dict))]
                else:
                    rule = sub_dict.get(warehouse_id.id)
                    rule = rule or sub_dict[False]
                if rule:
                    break
            return rule

        def get_rule_for_routes(rule_dict, route_ids, packaging_id, product_id, warehouse_id, location_dest_id):
            res = self.env['stock.rule']
            if route_ids:
                res = extract_rule(rule_dict, route_ids, warehouse_id, location_dest_id)
            if not res and packaging_id:
                res = extract_rule(rule_dict, packaging_id.route_ids, warehouse_id, location_dest_id)
            if not res:
                res = extract_rule(rule_dict, product_id.route_ids | product_id.categ_id.total_route_ids, warehouse_id, location_dest_id)
            if not res and warehouse_id:
                res = extract_rule(rule_dict, warehouse_id.route_ids, warehouse_id, location_dest_id)
            return res

        location = location_id
        # Go through the location hierarchy again, this time breaking at the first valid stock.rule found
        # in rules_by_location.
        inter_comp_location_checked = False
        while (not result) and location:
            candidate_locations = location
            if not inter_comp_location_checked and self._check_intercomp_location(location):
                # Add the intercomp location to candidate_locations as the intercomp domain was added
                # above in the call to _get_rule_domain.
                inter_comp_location = self.env.ref('stock.stock_location_customers', raise_if_not_found=False)
                candidate_locations |= inter_comp_location
                inter_comp_location_checked = True
            for candidate_location in candidate_locations:
                result = get_rule_for_routes(
                    rule_dict,
                    values.get('route_ids', self.env['stock.route']),
                    values.get('product_packaging_id', self.env['product.packaging']),
                    product_id,
                    values.get('warehouse_id', candidate_location.warehouse_id),
                    candidate_location,
                )
                if result:
                    break
            else:
                location = location.location_id
        return result

    @api.model
    def _check_intercomp_location(self, locations):
        if self.env.user.has_group('base.group_multi_company') and locations.filtered(lambda location: location.usage == 'transit'):
            inter_comp_location = self.env.ref('stock.stock_location_inter_company', raise_if_not_found=False)
            return inter_comp_location and inter_comp_location.id in locations.ids

    @api.model
    def _get_rule_domain(self, locations, values):
        location_ids = locations.ids
        # If the method is called to find rules towards the Inter-company location, also add the 'Customer' location in the domain.
        # This is to avoid having to duplicate every rules that deliver to Customer to have the Inter-company part.
        if self._check_intercomp_location(locations):
            location_ids.append(self.env.ref('stock.stock_location_customers', raise_if_not_found=False).id)
        domain = ['&', ('location_dest_id', 'in', location_ids), ('action', '!=', 'push')]
        # In case the method is called by the superuser, we need to restrict the rules to the
        # ones of the company. This is not useful as a regular user since there is a record
        # rule to filter out the rules based on the company.
        if self.env.su and values.get('company_id'):
            company_ids = set(values.get('company_id').ids)
            if values.get('route_ids'):
                company_ids |= set(values['route_ids'].company_id.ids)
            domain_company = ['|', ('company_id', '=', False), ('company_id', 'child_of', list(company_ids))]
            domain = expression.AND([domain, domain_company])
        return domain

    @api.model
    def _get_push_rule(self, product_id, location_dest_id, values):
        '''
        Find a push rule for the location_dest_id, with a fallback to the parent locations if none could be found.
        '''
        found_rule = self.env['stock.rule']
        location = location_dest_id
        while (not found_rule) and location:
            domain = [('location_src_id', '=', location.id), ('action', 'in', ('push', 'pull_push'))]
            if values.get('domain'):
                domain = expression.AND([domain, values['domain']])
            found_rule = self._search_rule(values.get('route_ids'), values.get('product_packaging_id'), product_id, values.get('warehouse_id'), domain)
            location = location.location_id
        return found_rule

    @api.model
    def _get_moves_to_assign_domain(self, company_id):
        moves_domain = [
            ('state', 'in', ['confirmed', 'partially_available']),
            ('product_uom_qty', '!=', 0.0),
            '|',
                ('reservation_date', '<=', fields.Date.today()),
                ('picking_type_id.reservation_method', '=', 'at_confirm'),
        ]
        if company_id:
            moves_domain = expression.AND([[('company_id', '=', company_id)], moves_domain])
        return moves_domain

    @api.model
    def _run_scheduler_tasks(self, use_new_cursor=False, company_id=False):
        task_done = 0

        # Minimum stock rules
        domain = self._get_orderpoint_domain(company_id=company_id)
        orderpoints = self.env['stock.warehouse.orderpoint'].search(domain)
        orderpoints.sudo()._procure_orderpoint_confirm(use_new_cursor=use_new_cursor, company_id=company_id, raise_user_error=False)
        task_done += 1

        if use_new_cursor:
            self.env['ir.cron']._notify_progress(done=task_done, remaining=self._get_scheduler_tasks_to_do() - task_done)
            self._cr.commit()

        # Search all confirmed stock_moves and try to assign them
        domain = self._get_moves_to_assign_domain(company_id)
        moves_to_assign = self.env['stock.move'].search(domain, limit=None,
            order='reservation_date, priority desc, date asc, id asc')
        for moves_chunk in split_every(1000, moves_to_assign.ids):
            self.env['stock.move'].browse(moves_chunk).sudo()._action_assign()
            if use_new_cursor:
                self._cr.commit()
                _logger.info('A batch of %d moves are assigned and committed', len(moves_chunk))
        task_done += 1

        if use_new_cursor:
            self.env['ir.cron']._notify_progress(
                done=task_done,
                remaining=self._get_scheduler_tasks_to_do() - task_done
            )
            self._cr.commit()

        # Merge duplicated quants
        self.env['stock.quant']._quant_tasks()

        task_done += 1
        if use_new_cursor:
            self.env['ir.cron']._notify_progress(
                done=task_done,
                remaining=self._get_scheduler_tasks_to_do() - task_done
            )
            self._cr.commit()
        self._context.get('scheduler_task_done', {})['task_done'] = task_done

    @api.model
    def _get_scheduler_tasks_to_do(self):
        '''
        Number of task to be executed by the stock scheduler. This number will be given in log
        message to know how many tasks succeeded.
        '''
        return 3

    @api.model
    def run_scheduler(self, use_new_cursor=False, company_id=False):
        '''
        Call the scheduler in order to check the running procurements (super method), to check the minimum stock rules
        and the availability of moves. This function is intended to be run for all the companies at the same time, so
        we run functions as SUPERUSER to avoid intercompanies and access rights issues.
        '''
        try:
            self._run_scheduler_tasks(use_new_cursor=use_new_cursor, company_id=company_id)
        except Exception:
            _logger.error('Error during stock scheduler', exc_info=True)
            raise
        return {}

    @api.model
    def _get_orderpoint_domain(self, company_id=False):
        domain = [('trigger', '=', 'auto'), ('product_id.active', '=', True)]
        if company_id:
            domain += [('company_id', '=', company_id)]
        return domain
