# # -*- coding: utf-8 -*-
# # Part of Odoo. See LICENSE file for full copyright and licensing details.
import datetime
import json
import sys
from unittest.mock import patch

from odoo import Command
from odoo.addons.base.tests.common import TransactionCaseWithUserDemo
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, common, tagged
from odoo.tools import mute_logger


def create_automation(self, **kwargs):
    """
    Create a transient automation with the given data and actions
    The created automation is cleaned up at the end of the calling test
    """
    vals = {'name': 'Automation'}
    vals.update(kwargs)
    actions_data = vals.pop('_actions', [])
    if not isinstance(actions_data, list):
        actions_data = [actions_data]
    automation_id = self.env['base.automation'].create(vals)
    action_ids = self.env['ir.actions.server'].create(
        [
            {
                'name': 'Action',
                'base_automation_id': automation_id.id,
                'model_id': automation_id.model_id.id,
                'usage': 'base_automation',
                **action,
            }
            for action in actions_data
        ]
    )
    action_ids.flush_recordset()
    automation_id.write({'action_server_ids': [Command.set(action_ids.ids)]})
    self.addCleanup(automation_id.unlink)
    return automation_id


@tagged('post_install', '-at_install')
class BaseAutomationTest(TransactionCaseWithUserDemo):
    def setUp(self):
        super(BaseAutomationTest, self).setUp()
        self.user_root = self.env.ref('base.user_root')
        self.user_admin = self.env.ref('base.user_admin')
        self.lead_model = self.env.ref('test_base_automation.model_base_automation_lead_test')
        self.project_model = self.env.ref('test_base_automation.model_test_base_automation_project')
        self.test_mail_template_automation = self.env['mail.template'].create(
            {
                'name': 'Template Automation',
                'model_id': self.env['ir.model']._get_id("base.automation.lead.thread.test"),
                'body_html': """&lt;div&gt;Email automation&lt;/div&gt;""",
            }
        )
        self.res_partner_1 = self.env['res.partner'].create({'name': 'My Partner'})

    def create_lead(self, **kwargs):
        vals = {
            'name': "Lead Test",
            'user_id': self.user_root.id,
        }
        vals.update(kwargs)
        lead = self.env['base.automation.lead.test'].create(vals)
        self.addCleanup(lead.unlink)
        return lead

    def create_line(self, **kwargs):
        vals = {
            'name': 'Line Test',
            'user_id': self.user_root.id,
        }
        vals.update(kwargs)
        line = self.env['base.automation.line.test'].create(vals)
        self.addCleanup(line.unlink)
        return line

    def create_project(self, **kwargs):
        vals = {'name': 'Project Test'}
        vals.update(kwargs)
        project = self.env['test_base_automation.project'].create(vals)
        self.addCleanup(project.unlink)
        return project

    def create_stage(self, **kwargs):
        vals = {'name': 'Stage Test'}
        vals.update(kwargs)
        stage = self.env['test_base_automation.stage'].create(vals)
        self.addCleanup(stage.unlink)
        return stage

    def create_tag(self, **kwargs):
        vals = {'name': 'Tag Test'}
        vals.update(kwargs)
        tag = self.env['test_base_automation.tag'].create(vals)
        self.addCleanup(tag.unlink)
        return tag

    def test_000_on_create_or_write(self):
        """
        Test case: on save, simple case
        - trigger: on_create_or_write
        """
        # --- Without the automation ---
        lead = self.create_lead()
        self.assertEqual(lead.state, 'draft')
        self.assertEqual(lead.user_id, self.user_root)

        # --- With the automation ---
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_create_or_write',
            _actions={'state': 'code', 'code': "record.write({'user_id': %s})" % (self.user_demo.id)},
        )

        # Write a lead should trigger the automation
        lead.write({'state': 'open'})
        self.assertEqual(lead.state, 'open')
        self.assertEqual(lead.user_id, self.user_demo)

        # Create a lead should trigger the automation
        lead2 = self.create_lead()
        self.assertEqual(lead2.state, 'draft')
        self.assertEqual(lead2.user_id, self.user_demo)

    def test_001_on_create_or_write(self):
        """
        Test case: on save, with filter_domain
        - trigger: on_create_or_write
        - apply when: state is 'draft'
        """
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_create_or_write',
            filter_domain="[('state', '=', 'draft')]",
            _actions={'state': 'code', 'code': "record.write({'user_id': %s})" % (self.user_demo.id)},
        )

        # Create a lead with state=open should not trigger the automation
        lead = self.create_lead(state='open')
        self.assertEqual(lead.state, 'open')
        self.assertEqual(lead.user_id, self.user_root)

        # Write a lead to state=draft should trigger the automation
        lead.write({'state': 'draft'})
        self.assertEqual(lead.state, 'draft')
        self.assertEqual(lead.user_id, self.user_demo)

        # Create a lead with state=draft should trigger the automation
        lead_2 = self.create_lead()
        self.assertEqual(lead_2.state, 'draft')
        self.assertEqual(lead_2.user_id, self.user_demo)

    def test_002_on_create_or_write(self):
        """
        Test case: on save, with filter_pre_domain and filter_domain
        - trigger: on_create_or_write
        - before update filter: state is 'open'
        - apply when: state is 'done'
        """
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_create_or_write',
            filter_pre_domain="[('state', '=', 'open')]",
            filter_domain="[('state', '=', 'done')]",
            _actions={'state': 'code', 'code': "record.write({'user_id': %s})" % (self.user_demo.id)},
        )

        # Create a lead with state=open should not trigger the automation
        lead = self.create_lead(state='open')
        self.assertEqual(lead.state, 'open')
        self.assertEqual(lead.user_id, self.user_root)

        # Write a lead to state=pending THEN to state=done should not trigger the automation
        lead.write({'state': 'pending'})
        self.assertEqual(lead.state, 'pending')
        self.assertEqual(lead.user_id, self.user_root)
        lead.write({'state': 'done'})
        self.assertEqual(lead.state, 'done')
        self.assertEqual(lead.user_id, self.user_root)

        # Write a lead from state=open to state=done should trigger the automation
        lead.write({'state': 'open'})
        self.assertEqual(lead.state, 'open')
        self.assertEqual(lead.user_id, self.user_root)
        lead.write({'state': 'done'})
        self.assertEqual(lead.state, 'done')
        self.assertEqual(lead.user_id, self.user_demo)

        # Create a lead with state=open then write it to state=done should trigger the automation
        lead_2 = self.create_lead(state='open')
        self.assertEqual(lead_2.state, 'open')
        self.assertEqual(lead_2.user_id, self.user_root)
        lead_2.write({'state': 'done'})
        self.assertEqual(lead_2.state, 'done')
        self.assertEqual(lead_2.user_id, self.user_demo)

        # Create a lead with state=done should trigger the automation,
        # as verifying the filter_pre_domain does not make sense on create
        lead_3 = self.create_lead(state='done')
        self.assertEqual(lead_3.state, 'done')
        self.assertEqual(lead_3.user_id, self.user_demo)

    def test_003_on_create_or_write(self):
        """ Check that the on_create_or_write trigger works as expected with trigger fields. """
        lead_state_field = self.env.ref('test_base_automation.field_base_automation_lead_test__state')
        automation = create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_create_or_write',
            trigger_field_ids=[Command.link(lead_state_field.id)],
            _actions={
                'state': 'code',
                'code': """
if env.context.get('old_values', None): # on write only
    record = model.browse(env.context['active_id'])
    record['name'] = record.name + 'X'""",
            },
        )

        lead = self.create_lead(name="X")
        lead.priority = True
        partner1 = self.res_partner_1
        lead.partner_id = partner1
        self.assertEqual(lead.name, 'X', "No update until now.")

        lead.state = 'open'
        self.assertEqual(lead.name, 'XX', "One update should have happened.")
        lead.state = 'done'
        self.assertEqual(lead.name, 'XXX', "One update should have happened.")
        lead.state = 'done'
        self.assertEqual(lead.name, 'XXX', "No update should have happened.")
        lead.state = 'cancel'
        self.assertEqual(lead.name, 'XXXX', "One update should have happened.")

        # change the rule to trigger on partner_id
        lead_partner_id_field = self.env.ref('test_base_automation.field_base_automation_lead_test__partner_id')
        automation.write({'trigger_field_ids': [Command.set([lead_partner_id_field.id])]})

        partner2 = self.env['res.partner'].create({'name': 'A new partner'})
        lead.name = 'X'
        lead.state = 'open'
        self.assertEqual(lead.name, 'X', "No update should have happened.")
        lead.partner_id = partner2
        self.assertEqual(lead.name, 'XX', "One update should have happened.")
        lead.partner_id = partner2
        self.assertEqual(lead.name, 'XX', "No update should have happened.")
        lead.partner_id = partner1
        self.assertEqual(lead.name, 'XXX', "One update should have happened.")
        lead.partner_id = partner1
        self.assertEqual(lead.name, 'XXX', "No update should have happened.")

    def test_010_recompute(self):
        """
        Test case: automation is applied whenever a field is recomputed
                   after a change on another model.
        - trigger: on_create_or_write
        - apply when: employee is True
        """
        partner = self.res_partner_1
        partner.write({'employee': False})

        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_create_or_write',
            filter_domain="[('employee', '=', True)]",
            _actions={'state': 'code', 'code': "record.write({'user_id': %s})" % (self.user_demo.id)},
        )

        lead = self.create_lead(partner_id=partner.id)
        self.assertEqual(lead.partner_id, partner)
        self.assertEqual(lead.employee, False)
        self.assertEqual(lead.user_id, self.user_root)

        # change partner, recompute on lead should trigger the rule
        partner.write({'employee': True})
        self.env.flush_all()  # ensures the recomputation is done
        self.assertEqual(lead.partner_id, partner)
        self.assertEqual(lead.employee, True)
        self.assertEqual(lead.user_id, self.user_demo)

    def test_011_recompute(self):
        """
        Test case: automation is applied whenever a field is recomputed.
                   The context contains the target field.
        - trigger: on_create_or_write
        """
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_create_or_write',
            _actions={
                'state': 'code',
                'code': """
if env.context.get('old_values', None):  # on write
    if 'user_id' in env.context['old_values'][record.id]:
        record.write({'is_assigned_to_admin': (record.user_id.id == 1)})""",
                },
            )

        partner = self.res_partner_1
        lead = self.create_lead(state='draft', partner_id=partner.id)
        self.assertEqual(lead.deadline, False)
        self.assertEqual(lead.is_assigned_to_admin, False)

        # change priority and user; this triggers deadline recomputation, and
        # the server action should set is_assigned_to_admin field to True
        lead.write({'priority': True, 'user_id': self.user_root.id})
        self.assertNotEqual(lead.deadline, False)
        self.assertEqual(lead.is_assigned_to_admin, True)

    def test_012_recompute(self):
        """
        Test case: automation is applied whenever a field is recomputed.
        - trigger: on_create_or_write
        - if updating fields: [deadline]
        """
        active_field = self.env.ref("test_base_automation.field_base_automation_lead_test__active")
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_create_or_write',
            trigger_field_ids=[Command.link(active_field.id)],
            _actions={
                'state': 'code',
                'code': """
if not env.context.get('old_values', None):  # on create
    record.write({'state': 'open'})
else:
    record.write({'priority': not record.priority})""",
            },
        )

        lead = self.create_lead(state='draft', priority=False)
        self.assertEqual(lead.state, 'open')  # the rule has set the state to open on create
        self.assertEqual(lead.priority, False)

        # change state; the rule should not be triggered
        lead.write({'state': 'pending'})
        self.assertEqual(lead.state, 'pending')
        self.assertEqual(lead.priority, False)

        # change active; the rule should be triggered
        lead.write({'active': False})
        self.assertEqual(lead.state, 'pending')
        self.assertEqual(lead.priority, True)

        # change active again; the rule should still be triggered
        lead.write({'active': True})
        self.assertEqual(lead.state, 'pending')
        self.assertEqual(lead.priority, False)

    def test_013_recompute(self):
        """
        Test case: automation is applied whenever a field is recomputed
        - trigger: on_create_or_write
        - if updating fields: [deadline]
        - before update filter: deadline is not set
        - apply when: deadline is set
        """
        deadline_field = self.env.ref("test_base_automation.field_base_automation_lead_test__deadline")
        create_automation(
            self,
            model_id=self.env['ir.model']._get_id('base.automation.lead.thread.test'),
            trigger='on_create_or_write',
            trigger_field_ids=[Command.link(deadline_field.id)],
            filter_pre_domain="[('deadline', '=', False)]",
            filter_domain="[('deadline', '!=', False)]",
            _actions={
                'state': 'mail_post',
                'mail_post_method': 'email',
                'template_id': self.test_mail_template_automation.id,
            },
        )

        send_mail_count = 0

        def _patched_send_mail(*args, **kwargs):
            nonlocal send_mail_count
            send_mail_count += 1

        patcher = patch('odoo.addons.mail.models.mail_template.MailTemplate.send_mail', _patched_send_mail)
        self.startPatcher(patcher)

        lead = self.env['base.automation.lead.thread.test'].create({
            'name': "Lead Test",
            'user_id': self.user_root.id,
        })
        self.addCleanup(lead.unlink)
        self.assertEqual(lead.priority, False)
        self.assertEqual(lead.deadline, False)
        self.assertEqual(send_mail_count, 0)

        lead.write({'priority': True})
        self.assertEqual(lead.priority, True)
        self.assertNotEqual(lead.deadline, False)
        self.assertEqual(send_mail_count, 1)

    def test_020_recursive(self):
        """ Check that a rule is executed recursively by a secondary change. """
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_create_or_write',
            _actions={
                'state': 'code',
                'code': """
if env.context.get('old_values', None):  # on write
    if 'partner_id' in env.context['old_values'][record.id]:
        record.write({'state': 'draft'})""",
            },
        )
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_create_or_write',
            filter_domain="[('state', '=', 'draft')]",
            _actions={'state': 'code', 'code': "record.write({'user_id': %s})" % (self.user_demo.id)},
        )

        lead = self.create_lead(state='open')
        self.assertEqual(lead.state, 'open')
        self.assertEqual(lead.user_id, self.user_root)

        # change partner; this should trigger the rule that modifies the state
        # and then the rule that modifies the user
        partner = self.res_partner_1
        lead.write({'partner_id': partner.id})
        self.assertEqual(lead.state, 'draft')
        self.assertEqual(lead.user_id, self.user_demo)

    def test_021_recursive(self):
        """ Check what it does with a recursive infinite loop """
        automations = [
            create_automation(
                self,
                model_id=self.lead_model.id,
                trigger='on_create_or_write',
                filter_domain="[('state', '=', 'draft')]",
                _actions={'state': 'code', 'code': "record.write({'state': 'pending'})"},
            ),
            create_automation(
                self,
                model_id=self.lead_model.id,
                trigger='on_create_or_write',
                filter_domain="[('state', '=', 'pending')]",
                _actions={'state': 'code', 'code': "record.write({'state': 'open'})"},
            ),
            create_automation(
                self,
                model_id=self.lead_model.id,
                trigger='on_create_or_write',
                filter_domain="[('state', '=', 'open')]",
                _actions={'state': 'code', 'code': "record.write({'state': 'done'})"},
            ),
            create_automation(
                self,
                model_id=self.lead_model.id,
                trigger='on_create_or_write',
                filter_domain="[('state', '=', 'done')]",
                _actions={'state': 'code', 'code': "record.write({'state': 'draft'})"},
            ),
        ]

        def _patch(*args, **kwargs):
            self.assertEqual(args[0], automations.pop(0))

        patcher = patch('odoo.addons.base_automation.models.base_automation.BaseAutomation._process', _patch)
        self.startPatcher(patcher)

        lead = self.create_lead(state='draft')
        self.assertEqual(lead.state, 'draft')
        self.assertEqual(len(automations), 0)  # all automations have been processed # CHECK if proper assertion ?

    def test_030_submodel(self):
        """ Check that a rule on a submodel is executed when the parent is modified. """
        # --- Without the automations ---
        line = self.create_line()
        self.assertEqual(line.user_id, self.user_root)

        lead = self.create_lead(line_ids=[(0, 0, {'name': 'Line', 'user_id': self.user_root.id})])
        self.assertEqual(lead.user_id, self.user_root)
        self.assertEqual(lead.line_ids.user_id, self.user_root)

        # --- With the automations ---
        comodel = self.env.ref('test_base_automation.model_base_automation_line_test')
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_create_or_write',
            _actions={'state': 'code', 'code': "record.write({'user_id': %s})" % (self.user_demo.id)},
        )
        create_automation(
            self,
            model_id=comodel.id,
            trigger='on_create_or_write',
            _actions={'state': 'code', 'code': "record.write({'user_id': %s})" % (self.user_demo.id)},
        )

        line = self.create_line(user_id=self.user_root.id)
        self.assertEqual(line.user_id, self.user_demo)  # rule on secondary model

        lead = self.create_lead(line_ids=[(0, 0, {'name': 'Line', 'user_id': self.user_root.id})])
        self.assertEqual(lead.user_id, self.user_demo)  # rule on primary model
        self.assertEqual(lead.line_ids.user_id, self.user_demo)  # rule on secondary model

    def test_040_modelwithoutaccess(self):
        """
        Ensure a domain on a M2O without user access doesn't fail.
        We create a base automation with a filter on a model the user haven't access to
        - create a group
        - restrict acl to this group and set only admin in it
        - create base.automation with a filter
        - create a record in the restricted model in admin
        - create a record in the non restricted model in demo
        """
        Model = self.env['base.automation.link.test']
        model_id = self.env.ref('test_base_automation.model_base_automation_link_test')
        Comodel = self.env['base.automation.linked.test']
        comodel_access = self.env.ref('test_base_automation.access_base_automation_linked_test')
        comodel_access.group_id = self.env['res.groups'].create({
            'name': "Access to base.automation.linked.test",
            "user_ids": [Command.link(self.user_admin.id)],
        })

        # sanity check: user demo has no access to the comodel of 'linked_id'
        with self.assertRaises(AccessError):
            Comodel.with_user(self.user_demo).check_access('read')

        # check base automation with filter that performs Comodel.search()
        create_automation(
            self,
            model_id=model_id.id,
            trigger='on_create_or_write',
            filter_pre_domain="[('linked_id.another_field', '=', 'something')]",
            _actions={'state': 'code', 'code': 'action = [rec.name for rec in records]'},
        )
        Comodel.create([
            {'name': 'a first record', 'another_field': 'something'},
            {'name': 'another record', 'another_field': 'something different'},
        ])
        rec1 = Model.create({'name': 'a record'})
        rec1.write({'name': 'a first record'})
        rec2 = Model.with_user(self.user_demo).create({'name': 'another record'})
        rec2.write({'name': 'another value'})

        # check base automation with filter that performs Comodel.name_search()
        create_automation(
            self,
            model_id=model_id.id,
            trigger='on_create_or_write',
            filter_pre_domain="[('linked_id', '=', 'whatever')]",
            _actions={'state': 'code', 'code': 'action = [rec.name for rec in records]'},
        )
        rec3 = Model.create({'name': 'a random record'})
        rec3.write({'name': 'a first record'})
        rec4 = Model.with_user(self.user_demo).create({'name': 'again another record'})
        rec4.write({'name': 'another value'})

    def test_050_on_create_or_write_with_create_record(self):
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_create_or_write',
            _actions={
                'state': 'object_create',
                'crud_model_id': self.project_model.id,
                'value': 'foo',
            },
        )
        lead = self.create_lead()
        search_result = self.env['test_base_automation.project'].name_search('foo')
        self.assertEqual(len(search_result), 1, 'One record on the project model should have been created')

        lead.write({'name': 'renamed lead'})
        search_result = self.env['test_base_automation.project'].name_search('foo')
        self.assertEqual(len(search_result), 2, 'Another record on the project model should have been created')

        # ----------------------------
        # The following does not work properly as it is a known
        # limitation of the implementation since at least 14.0
        # -> AssertionError: 4 != 3 : Another record on the secondary model should have been created

        # # write on a field that is a dependency of another computed field
        # lead.write({'priority': True})
        # search_result = self.env['test_base_automation.project'].name_search('foo')
        # self.assertEqual(len(search_result), 3, 'Another record on the secondary model should have been created')
        # ----------------------------

    def test_060_on_stage_set(self):
        stage_field = self.env['ir.model.fields'].search([
            ('model_id', '=', self.project_model.id),
            ('name', '=', 'stage_id'),
        ])
        stage1 = self.create_stage()
        stage2 = self.create_stage()
        create_automation(
            self,
            model_id=self.project_model.id,
            trigger='on_stage_set',
            trigger_field_ids=[stage_field.id],
            filter_domain="[('stage_id', '=', %s)]" % stage1.id,
            _actions={'state': 'code', 'code': "record.write({'name': record.name + '!'})"},
        )
        project = self.create_project()
        self.assertEqual(project.name, 'Project Test')
        project.write({'stage_id': stage1.id})
        self.assertEqual(project.name, 'Project Test!')
        project.write({'stage_id': stage1.id})
        self.assertEqual(project.name, 'Project Test!')
        project.write({'stage_id': stage2.id})
        self.assertEqual(project.name, 'Project Test!')
        project.write({'stage_id': False})
        self.assertEqual(project.name, 'Project Test!')
        project.write({'stage_id': stage1.id})
        self.assertEqual(project.name, 'Project Test!!')

    def test_070_on_user_set(self):
        user_field = self.env['ir.model.fields'].search([
            ('model_id', '=', self.lead_model.id),
            ('name', '=', 'user_id'),
        ])
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_user_set',
            trigger_field_ids=[user_field.id],
            filter_domain="[('user_id', '!=', False)]",
            _actions={'state': 'code', 'code': "record.write({'name': record.name + '!'})"},
        )

        lead = self.create_lead()
        self.assertEqual(lead.name, 'Lead Test!')
        lead.write({'user_id': self.user_demo.id})
        self.assertEqual(lead.name, 'Lead Test!!')
        lead.write({'user_id': self.user_demo.id})
        self.assertEqual(lead.name, 'Lead Test!!')
        lead.write({'user_id': self.user_admin.id})
        self.assertEqual(lead.name, 'Lead Test!!!')
        lead.write({'user_id': False})
        self.assertEqual(lead.name, 'Lead Test!!!')
        lead.write({'user_id': self.user_demo.id})
        self.assertEqual(lead.name, 'Lead Test!!!!')

    def test_071_on_user_set(self):
        # same test as above but with the user_ids many2many on a project
        user_field = self.env['ir.model.fields'].search([
            ('model_id', '=', self.project_model.id),
            ('name', '=', 'user_ids'),
        ])
        create_automation(
            self,
            model_id=self.project_model.id,
            trigger='on_user_set',
            trigger_field_ids=[user_field.id],
            filter_domain="[('user_ids', '!=', False)]",
            _actions={'state': 'code', 'code': "record.write({'name': record.name + '!'})"},
        )

        project = self.create_project()
        self.assertEqual(project.name, 'Project Test')
        project.write({'user_ids': [Command.set([self.user_demo.id])]})
        self.assertEqual(project.name, 'Project Test!')
        project.write({'user_ids': [Command.set([self.user_demo.id])]})
        self.assertEqual(project.name, 'Project Test!')
        project.write({'user_ids': [Command.link(self.user_admin.id)]})
        self.assertEqual(project.name, 'Project Test!!')
        # Unlinking a user while there are still other users does trigger the automation
        # This behavior could be changed in the future but needs a bit of investigation
        project.write({'user_ids': [Command.unlink(self.user_admin.id)]})
        self.assertEqual(project.name, 'Project Test!!!')
        project.write({'user_ids': [Command.set([])]})
        self.assertEqual(project.name, 'Project Test!!!')
        project.write({'user_ids': [Command.set([self.user_demo.id])]})
        self.assertEqual(project.name, 'Project Test!!!!')

    def test_080_on_tag_set(self):
        tag_field = self.env['ir.model.fields'].search([
            ('model_id', '=', self.project_model.id),
            ('name', '=', 'tag_ids'),
        ])
        tag1 = self.create_tag()
        create_automation(
            self,
            model_id=self.project_model.id,
            trigger='on_tag_set',
            trigger_field_ids=[tag_field.id],
            filter_pre_domain="[('tag_ids', 'not in', [%s])]" % tag1.id,
            filter_domain="[('tag_ids', 'in', [%s])]" % tag1.id,
            _actions={'state': 'code', 'code': "record.write({'name': record.name + '!'})"},
        )
        project = self.create_project()
        self.assertEqual(project.name, 'Project Test')
        project.write({'tag_ids': [Command.set([tag1.id])]})
        self.assertEqual(project.name, 'Project Test!')
        project.write({'tag_ids': [Command.set([tag1.id])]})
        self.assertEqual(project.name, 'Project Test!')

        tag2 = self.create_tag()
        project.write({'tag_ids': [Command.link(tag2.id)]})
        self.assertEqual(project.name, 'Project Test!')
        project.write({'tag_ids': [Command.clear()]})
        self.assertEqual(project.name, 'Project Test!')
        project.write({'tag_ids': [Command.set([tag2.id])]})
        self.assertEqual(project.name, 'Project Test!')
        project.write({'tag_ids': [Command.link(tag1.id)]})
        self.assertEqual(project.name, 'Project Test!!')

    def test_090_on_state_set(self):
        state_field = self.env['ir.model.fields'].search([
            ('model_id', '=', self.lead_model.id),
            ('name', '=', 'state'),
        ])

        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_state_set',
            trigger_field_ids=[state_field.id],
            filter_domain="[('state', '=', 'done')]",
            _actions={'state': 'code', 'code': "record.write({'name': record.name + '!'})"},
        )

        lead = self.create_lead()
        self.assertEqual(lead.name, 'Lead Test')
        lead.write({'state': 'open'})
        self.assertEqual(lead.name, 'Lead Test')
        lead.write({'state': 'done'})
        self.assertEqual(lead.name, 'Lead Test!')
        lead.write({'state': 'done'})
        self.assertEqual(lead.name, 'Lead Test!')
        lead.write({'state': 'open'})
        self.assertEqual(lead.name, 'Lead Test!')
        lead.write({'state': 'done'})
        self.assertEqual(lead.name, 'Lead Test!!')

    def test_100_on_priority_set(self):
        priority_field = self.env['ir.model.fields'].search([
            ('model_id', '=', self.project_model.id),
            ('name', '=', 'priority'),
        ])
        create_automation(
            self,
            model_id=self.project_model.id,
            trigger='on_priority_set',
            trigger_field_ids=[priority_field.id],
            filter_domain="[('priority', '=', '2')]",
            _actions={'state': 'code', 'code': "record.write({'name': record.name + '!'})"},
        )
        project = self.create_project()
        self.assertEqual(project.name, 'Project Test')
        self.assertEqual(project.priority, '1')
        project.write({'priority': '0'})
        self.assertEqual(project.name, 'Project Test')
        project.write({'priority': '2'})
        self.assertEqual(project.name, 'Project Test!')
        project.write({'priority': '2'})
        self.assertEqual(project.name, 'Project Test!')
        project.write({'priority': '0'})
        self.assertEqual(project.name, 'Project Test!')
        project.write({'priority': '2'})
        self.assertEqual(project.name, 'Project Test!!')

    def test_110_on_archive(self):
        active_field = self.env['ir.model.fields'].search([
            ('model_id', '=', self.lead_model.id),
            ('name', '=', 'active'),
        ])
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_archive',
            trigger_field_ids=[active_field.id],
            filter_domain="[('active', '=', False)]",
            _actions={'state': 'code', 'code': "record.write({'name': record.name + '!'})"},
        )
        lead = self.create_lead()
        self.assertEqual(lead.name, 'Lead Test')
        lead.write({'active': False})
        self.assertEqual(lead.name, 'Lead Test!')
        lead.write({'active': True})
        self.assertEqual(lead.name, 'Lead Test!')
        lead.write({'active': False})
        self.assertEqual(lead.name, 'Lead Test!!')
        lead.write({'active': False})
        self.assertEqual(lead.name, 'Lead Test!!')

    def test_110_on_unarchive(self):
        active_field = self.env['ir.model.fields'].search([
            ('model_id', '=', self.lead_model.id),
            ('name', '=', 'active'),
        ])
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_unarchive',
            trigger_field_ids=[active_field.id],
            filter_domain="[('active', '=', True)]",
            _actions={'state': 'object_write', 'evaluation_type': 'equation', 'update_path': 'name', 'value': "record.name + '!'"},
        )
        lead = self.create_lead()
        self.assertEqual(lead.name, 'Lead Test')
        lead.write({'active': False})
        self.assertEqual(lead.name, 'Lead Test')
        lead.write({'active': True})
        self.assertEqual(lead.name, 'Lead Test!')
        lead.write({'active': False})
        self.assertEqual(lead.name, 'Lead Test!')
        lead.write({'active': True})
        self.assertEqual(lead.name, 'Lead Test!!')
        lead.write({'active': True})
        self.assertEqual(lead.name, 'Lead Test!!')

    def test_120_on_change(self):
        Model = self.env.get(self.lead_model.model)
        lead_name_field = self.env['ir.model.fields'].search([
            ('model_id', '=', self.lead_model.id),
            ('name', '=', 'name'),
        ])
        self.assertEqual(lead_name_field.name in Model._onchange_methods, False)
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_change',
            on_change_field_ids=[lead_name_field.id],
            _actions={'state': 'code', 'code': ""},
        )
        self.assertEqual(lead_name_field.name in Model._onchange_methods, True)

    def test_130_on_unlink(self):
        automation = create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_unlink',
            _actions={'state': 'code', 'code': "record.write({'name': record.name + '!'})"},
        )

        called_count = 0

        def _patch(*args, **kwargs):
            nonlocal called_count
            called_count += 1
            self.assertEqual(args[0], automation)

        patcher = patch('odoo.addons.base_automation.models.base_automation.BaseAutomation._process', _patch)
        self.startPatcher(patcher)

        lead = self.create_lead()
        self.assertEqual(called_count, 0)
        lead.unlink()
        self.assertEqual(called_count, 1)

    def test_004_check_method_trigger_field(self):
        model = self.env["ir.model"]._get("base.automation.lead.test")
        TIME_TRIGGERS = [
           'on_time',
           'on_time_created',
           'on_time_updated',
        ]
        self.env["base.automation"].search([('trigger', 'in', TIME_TRIGGERS)]).active = False

        automation = self.env["base.automation"].create({
            "name": "Cron BaseAuto",
            "trigger": "on_time",
            "model_id": model.id,
        })

        # first run, check we have a field set
        # this does not happen using the UI where the trigger is forced to be set
        self.assertFalse(automation.last_run)
        with self.assertLogs('odoo.addons.base_automation', 'WARNING') as capture:
            self.env["base.automation"]._cron_process_time_based_actions(auto_commit=False)
        self.assertRegex(capture.output[0], r"Missing date trigger")
        automation.trg_date_id = model.field_id.filtered(lambda f: f.name == 'date_automation_last')

        # normal run
        self.env["base.automation"]._cron_process_time_based_actions(auto_commit=False)
        self.assertTrue(automation.last_run)

    @common.freeze_time('2020-01-01 03:00:00')
    def test_004_check_method_process(self):
        model = self.env["ir.model"]._get("base.automation.lead.test")
        TIME_TRIGGERS = [
           'on_time',
           'on_time_created',
           'on_time_updated',
        ]
        self.env["base.automation"].search([('trigger', 'in', TIME_TRIGGERS)]).active = False

        automation = self.env["base.automation"].create({
            "name": "Cron BaseAuto",
            "trigger": "on_time",
            "model_id": model.id,
            "trg_date_id": model.field_id.filtered(lambda f: f.name == 'date_automation_last').id,
            "trg_date_range": 2,
            "trg_date_range_type": "minutes",
        })

        with patch.object(automation.__class__, '_process', side_effect=automation._process) as mock:
            with patch.object(self.env.cr, '_now', now := datetime.datetime.now()):
                past_date = now - datetime.timedelta(1)
                self.env["base.automation.lead.test"].create({
                    'name': f'lead {i}',
                    # 2 without a date, 8 set in past, 5 set in future (10, 11, ... minutes after now)
                    'date_automation_last': False if i < 2 else past_date if i < 10 else now + datetime.timedelta(minutes=i),
                } for i in range(15))
            with common.freeze_time('2020-01-01 03:02:01'), patch.object(self.env.cr, '_now', datetime.datetime.now()):
                # process records
                self.env["base.automation"]._cron_process_time_based_actions(auto_commit=False)
                self.assertEqual(mock.call_count, 10)
                self.assertEqual(automation.last_run, self.env.cr.now())
            with common.freeze_time('2020-01-01 03:13:59'), patch.object(self.env.cr, '_now', datetime.datetime.now()):
                # 2 in the future (because of timing)
                # 10 previously done records because we use the date_automation_last as trigger without delay
                self.env["base.automation"]._cron_process_time_based_actions(auto_commit=False)
                self.assertEqual(mock.call_count, 22)
                self.assertEqual(automation.last_run, self.env.cr.now())
                # test triggering using a calendar
                automation.trg_date_calendar_id = self.env["resource.calendar"].search([], limit=1).ensure_one()
                automation.trg_date_range_type = 'day'
                self.env["base.automation.lead.test"].create({'name': 'calendar'})  # for the run
            with common.freeze_time('2020-02-02 03:11:00'), patch.object(self.env.cr, '_now', datetime.datetime.now()):
                self.env["base.automation"]._cron_process_time_based_actions(auto_commit=False)
                self.assertEqual(mock.call_count, 38)

    def test_005_check_model_with_different_rec_name_char(self):
        model = self.env["ir.model"]._get("base.automation.model.with.recname.char")

        create_automation(
            self,
            model_id=self.project_model.id,
            trigger='on_create_or_write',
            _actions={
                'state': 'object_create',
                'crud_model_id': model.id,
                'value': "Test _rec_name Automation",
            },
        )

        self.create_project()
        record_count = self.env[model.model].search_count([('description', '=', 'Test _rec_name Automation')])
        self.assertEqual(record_count, 1, "Only one record should have been created")

    def test_006_check_model_with_different_m2o_name_create(self):
        model = self.env["ir.model"]._get("base.automation.model.with.recname.m2o")

        create_automation(
            self,
            model_id=self.project_model.id,
            trigger='on_create_or_write',
            _actions={
                'state': 'object_create',
                'crud_model_id': model.id,
                'value': "Test _rec_name Automation",
            },
        )

        self.create_project()
        record_count = self.env[model.model].search_count([('user_id', '=', 'Test _rec_name Automation')])
        self.assertEqual(record_count, 1, "Only one record should have been created")

    def test_140_copy_should_copy_actions(self):
        """ Copying an automation should copy its actions. """
        automation = create_automation(
            self,
            model_id=self.lead_model.id,
            trigger='on_change',
            _actions={'state': 'code', 'code': "record.write({'name': record.name + '!'})"},
        )
        action_ids = automation.action_server_ids

        copy_automation = automation.copy()
        copy_action_ids = copy_automation.action_server_ids
        # Same number of actions but id should be different
        self.assertEqual(len(action_ids), 1)
        self.assertEqual(len(copy_action_ids), len(action_ids))
        self.assertNotEqual(copy_action_ids, action_ids)

    def test_add_followers_1(self):
        create_automation(self,
            model_id=self.env["ir.model"]._get("base.automation.lead.thread.test").id,
            trigger="on_create",
            _actions={
                "state": "followers",
                "followers_type": "generic",
                "followers_partner_field_name": "user_id.partner_id"
            }
        )
        user = self.env["res.users"].create({"login": "maggot_brain", "name": "Eddie Hazel"})
        thread_test = self.env["base.automation.lead.thread.test"].create({
            "name": "free your mind",
            "user_id": user.id,
        })
        self.assertEqual(thread_test.message_follower_ids.partner_id, user.partner_id)

    def test_add_followers_2(self):
        user = self.env["res.users"].create({"login": "maggot_brain", "name": "Eddie Hazel"})
        create_automation(self,
            model_id=self.env["ir.model"]._get("base.automation.lead.thread.test").id,
            trigger="on_create",
            _actions={
                "state": "followers",
                "followers_type": "specific",
                "partner_ids": [Command.link(user.partner_id.id)]
            }
        )
        thread_test = self.env["base.automation.lead.thread.test"].create({
            "name": "free your mind",
        })
        self.assertEqual(thread_test.message_follower_ids.partner_id, user.partner_id)

    def test_cannot_have_actions_with_warnings(self):
        with self.assertRaises(ValidationError) as e:
            create_automation(
                self,
                model_id=self.env['ir.model']._get('ir.actions.server').id,
                trigger='on_time',
                _actions={
                    'name': 'Send Webhook Notification',
                    'state': 'webhook',
                    'webhook_field_ids': [self.env['ir.model.fields']._get('ir.actions.server', 'code').id],
                },
            )
        self.assertEqual(e.exception.args[0], "Following child actions have warnings: Send Webhook Notification")


@common.tagged('post_install', '-at_install')
class TestCompute(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref('base.user_admin').write({
            'email': 'mitchell.admin@example.com',
        })

    def test_automation_form_view(self):
        automation_form = Form(self.env['base.automation'], view='base_automation.view_base_automation_form')

        # Initialize some fields
        automation_form.name = "Test Automation"
        automation_form.model_id = self.env.ref('test_base_automation.model_test_base_automation_project')
        automation_form.trigger = 'on_create_or_write'
        self.assertEqual(automation_form.trigger_field_ids.ids, [])
        self.assertEqual(automation_form.filter_domain, False)
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        # Changing the model must reset the trigger
        automation_form.model_id = self.env.ref('test_base_automation.model_base_automation_lead_test')
        self.assertEqual(automation_form.trigger, False)
        self.assertEqual(automation_form.trigger_field_ids.ids, [])
        self.assertEqual(automation_form.filter_domain, False)

        # Some triggers must preset a filter_domain and trigger_field_ids
        ## State is set to...
        automation_form.trigger = 'on_state_set'
        state_field_id = self.env.ref('test_base_automation.field_base_automation_lead_test__state').id
        self.assertEqual(automation_form.trigger_field_ids.ids, [state_field_id])
        self.assertEqual(automation_form.filter_domain, False)
        automation_form.trg_selection_field_id = self.env['ir.model.fields.selection'].search([
            ('field_id', '=', state_field_id),
            ('value', '=', 'pending'),
        ])
        self.assertEqual(automation_form.trigger_field_ids.ids, [state_field_id])
        self.assertEqual(automation_form.filter_domain, repr([('state', '=', 'pending')]))
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        ## Priority is set to...
        automation_form.model_id = self.env.ref('test_base_automation.model_test_base_automation_project')
        automation_form.trigger = 'on_priority_set'
        priority_field_id = self.env.ref('test_base_automation.field_test_base_automation_project__priority').id
        self.assertEqual(automation_form.trigger_field_ids.ids, [priority_field_id])
        self.assertEqual(automation_form.filter_domain, False)
        automation_form.trg_selection_field_id = self.env['ir.model.fields.selection'].search([
            ('field_id', '=', priority_field_id),
            ('value', '=', '2'),
        ])
        self.assertEqual(automation_form.trigger_field_ids.ids, [priority_field_id])
        self.assertEqual(automation_form.filter_domain, repr([('priority', '=', '2')]))
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        ## Stage is set to...
        automation_form.model_id = self.env.ref('test_base_automation.model_base_automation_lead_test')
        automation_form.trigger = 'on_stage_set'
        stage_field_id = self.env.ref('test_base_automation.field_base_automation_lead_test__stage_id').id
        self.assertEqual(automation_form.trigger_field_ids.ids, [stage_field_id])
        self.assertEqual(automation_form.filter_domain, False)
        new_lead_stage = self.env['test_base_automation.stage'].create({'name': 'New'})
        automation_form.trg_field_ref = new_lead_stage.id
        self.assertEqual(automation_form.filter_domain, repr([('stage_id', '=', new_lead_stage.id)]))
        self.assertEqual(automation_form.trigger_field_ids.ids, [stage_field_id])
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        ## User is set
        automation_form.trigger = 'on_user_set'
        self.assertEqual(automation_form.trigger_field_ids.ids, [
            self.env.ref('test_base_automation.field_base_automation_lead_test__user_id').id
        ])
        self.assertEqual(automation_form.filter_domain, repr([('user_id', '!=', False)]))
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        ## On archive
        automation_form.trigger = 'on_archive'
        self.assertEqual(automation_form.trigger_field_ids.ids, [
            self.env.ref('test_base_automation.field_base_automation_lead_test__active').id
        ])
        self.assertEqual(automation_form.filter_domain, repr([('active', '=', False)]))
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        ## On unarchive
        automation_form.trigger = 'on_unarchive'
        self.assertEqual(automation_form.trigger_field_ids.ids, [
            self.env.ref('test_base_automation.field_base_automation_lead_test__active').id
        ])
        self.assertEqual(automation_form.filter_domain, repr([('active', '=', True)]))
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        ## Tag is set to...
        automation_form.trigger = 'on_tag_set'
        a_lead_tag = self.env['test_base_automation.tag'].create({'name': '*AWESOME*'})
        automation_form.trg_field_ref = a_lead_tag.id
        self.assertEqual(automation_form.filter_domain, repr([('tag_ids', 'in', [a_lead_tag.id])]))
        self.assertEqual(automation_form.trigger_field_ids.ids, [
            self.env.ref('test_base_automation.field_base_automation_lead_test__tag_ids').id
        ])
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, repr([('tag_ids', 'not in', [a_lead_tag.id])]))

    def test_automation_form_view_on_change_filter_domain(self):
        a_lead_tag = self.env['test_base_automation.tag'].create({'name': '*AWESOME*'})
        automation = self.env['base.automation'].create({
            'name': 'Test Automation',
            'model_id': self.env.ref('test_base_automation.model_base_automation_lead_test').id,
            'trigger': 'on_tag_set',
            'trg_field_ref': a_lead_tag.id,
        })
        self.assertEqual(automation.filter_pre_domain, repr([('tag_ids', 'not in', [a_lead_tag.id])]))
        self.assertEqual(automation.filter_domain, repr([('tag_ids', 'in', [a_lead_tag.id])]))
        self.assertEqual(automation.trigger_field_ids.ids, [
            self.env.ref('test_base_automation.field_base_automation_lead_test__tag_ids').id
        ])
        self.assertEqual(automation.on_change_field_ids.ids, [])

        # Change the trigger to "On save" will erase the domains and the trigger fields
        automation_form = Form(automation, view='base_automation.view_base_automation_form')
        automation_form.trigger = 'on_create_or_write'
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)
        self.assertEqual(automation.filter_domain, False)
        self.assertEqual(automation.trigger_field_ids.ids, [])
        self.assertEqual(automation.on_change_field_ids.ids, [])

        # Change the domain will append each used field to the trigger fields
        automation_form.filter_domain = repr([('priority', '=', True), ('employee', '=', False)])
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)
        self.assertEqual(automation.filter_domain, repr([('priority', '=', True), ('employee', '=', False)]))
        self.assertSetEqual(set(automation.trigger_field_ids.ids), {
            self.env.ref('test_base_automation.field_base_automation_lead_test__priority').id,
            self.env.ref('test_base_automation.field_base_automation_lead_test__employee').id,
        })
        self.assertEqual(automation.on_change_field_ids.ids, [])

        # Change the trigger fields will not change the domain
        automation_form.trigger_field_ids.set(
            self.env.ref('test_base_automation.field_base_automation_lead_test__tag_ids')
        )
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)
        self.assertEqual(automation.filter_domain, repr([('priority', '=', True), ('employee', '=', False)]))
        self.assertEqual(automation.trigger_field_ids.ids, [
            self.env.ref('test_base_automation.field_base_automation_lead_test__tag_ids').id
        ])
        self.assertEqual(automation.on_change_field_ids.ids, [])

        # Erase the domain will not change the trigger fields
        automation_form.filter_domain = False
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)
        self.assertEqual(automation.filter_domain, False)
        self.assertEqual(automation.trigger_field_ids.ids, [
            self.env.ref('test_base_automation.field_base_automation_lead_test__tag_ids').id
        ])
        self.assertEqual(automation.on_change_field_ids.ids, [])

    def test_automation_form_view_time_triggers(self):
        # Starting from a "On save" automation
        on_save_automation = self.env['base.automation'].create({
            'name': 'Test Automation',
            'model_id': self.env.ref('test_base_automation.model_base_automation_lead_test').id,
            'trigger': 'on_create_or_write',
            'filter_domain': repr([('employee', '=', False)]),
            'trigger_field_ids': self.env.ref('test_base_automation.field_base_automation_lead_test__employee')
        })

        automation = on_save_automation.copy()
        self.assertEqual(automation.filter_pre_domain, False)
        self.assertEqual(automation.filter_domain, repr([('employee', '=', False)]))
        self.assertEqual(automation.trg_date_id.id, False)
        self.assertEqual(automation.trigger_field_ids.ids, [
            self.env.ref('test_base_automation.field_base_automation_lead_test__employee').id
        ])

        # Changing to a time trigger must erase domains and trigger fields
        ## Change the trigger to "On time created"
        automation_form = Form(automation, view='base_automation.view_base_automation_form')
        automation_form.trigger = 'on_time_created'
        self.assertEqual(automation_form.filter_domain, False)
        self.assertEqual(automation_form.trg_date_id, self.env.ref('test_base_automation.field_base_automation_lead_test__create_date'))
        self.assertEqual(automation_form.trigger_field_ids.ids, [])
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        ## Change the trigger to "On time updated"
        automation = on_save_automation.copy()
        automation_form = Form(automation, view='base_automation.view_base_automation_form')
        automation_form.trigger = 'on_time_updated'
        self.assertEqual(automation_form.filter_domain, False)
        self.assertEqual(automation_form.trg_date_id, self.env.ref('test_base_automation.field_base_automation_lead_test__write_date'))
        self.assertEqual(automation_form.trigger_field_ids.ids, [])
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        ## Change the trigger to "On time"
        automation = on_save_automation.copy()
        automation_form = Form(automation, view='base_automation.view_base_automation_form')
        automation_form.trigger = 'on_time'
        automation_form.trg_date_id = self.env.ref('test_base_automation.field_base_automation_lead_test__create_date')
        self.assertEqual(automation_form.filter_domain, False)
        self.assertEqual(automation_form.trg_date_id, self.env.ref('test_base_automation.field_base_automation_lead_test__create_date'))
        self.assertEqual(automation_form.trigger_field_ids.ids, [])
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

    def test_automation_form_view_with_default_values_in_context(self):
        # Use case where default model, trigger and filter_domain in context
        context = {
            'default_name': 'Test Automation',
            'default_model_id': self.env.ref('test_base_automation.model_base_automation_lead_test').id,
            'default_trigger': 'on_create_or_write',
            'default_filter_domain': repr([('state', '=', 'draft')]),
        }
        # Create form should be pre-filled with the default values
        automation = self.env['base.automation'].with_context(context)
        default_trigger_field_ids = [self.env.ref('test_base_automation.field_base_automation_lead_test__state').id]
        automation_form = Form(automation, view='base_automation.view_base_automation_form')
        self.assertEqual(automation_form.name, context.get('default_name'))
        self.assertEqual(automation_form.model_id.id, context.get('default_model_id'))
        self.assertEqual(automation_form.trigger, context.get('default_trigger'))
        self.assertEqual(automation_form.trigger_field_ids.ids, default_trigger_field_ids,
            'trigger_field_ids should match the fields in the default filter domain.')

        automation_form.trigger = 'on_stage_set'
        self.assertNotEqual(automation_form.trigger_field_ids.ids, default_trigger_field_ids,
            'When user changes trigger, the trigger_field_ids field should be updated')

    def test_inversion(self):
        """ If a stored field B depends on A, an update to the trigger for A
        should trigger the recomputaton of A, then B.

        However if a search() is performed during the computation of A
        ??? and _order is affected ??? a flush will be triggered, forcing the
        computation of B, based on the previous A.

        This happens if a rule has a non-empty filter_pre_domain, even if
        it's an empty list (``'[]'`` as opposed to ``False``).
        """
        company1 = self.env['res.partner'].create({
            'name': "Gorofy",
            'is_company': True,
        })
        company2 = self.env['res.partner'].create({
            'name': "Awiclo",
            'is_company': True
        })
        r = self.env['res.partner'].create({
            'name': 'Bob',
            'is_company': False,
            'parent_id': company1.id
        })
        self.assertEqual(r.display_name, 'Gorofy, Bob')
        r.parent_id = company2
        self.assertEqual(r.display_name, 'Awiclo, Bob')

        create_automation(
            self,
            model_id=self.env.ref('base.model_res_partner').id,
            filter_pre_domain=False,
            trigger='on_create_or_write',
            _actions={'state': 'code'},  # no-op action
        )
        r.parent_id = company1
        self.assertEqual(r.display_name, 'Gorofy, Bob')

        create_automation(
            self,
            model_id=self.env.ref('base.model_res_partner').id,
            filter_pre_domain='[]',
            trigger='on_create_or_write',
            _actions={'state': 'code'},  # no-op action
        )
        r.parent_id = company2
        self.assertEqual(r.display_name, 'Awiclo, Bob')

    def test_recursion(self):
        project = self.env['test_base_automation.project'].create({})

        # this action is executed every time a task is assigned to project
        create_automation(
            self,
            model_id=self.env.ref('test_base_automation.model_test_base_automation_task').id,
            trigger='on_create_or_write',
            filter_domain=repr([('project_id', '=', project.id)]),
            _actions={'state': 'code'},  # no-op action
        )

        # create one task in project with 10 subtasks; all the subtasks are
        # automatically assigned to project, too
        task = self.env['test_base_automation.task'].create({'project_id': project.id})
        subtasks = task.create([{'parent_id': task.id} for _ in range(10)])
        subtasks.flush_model()

        # This test checks what happens when a stored recursive computed field
        # is marked to compute on many records, and automation rules are
        # triggered depending on that field.  In this case, we trigger the
        # recomputation of 'project_id' on 'subtasks' by deleting their parent
        # task.
        #
        # An issue occurs when the domain of automation rules is evaluated by
        # method search(), because the latter flushes the fields to search on,
        # which are also the ones being recomputed.  Combined with the fact
        # that recursive fields are not computed in batch, this leads to a huge
        # amount of recursive calls between the automation rule and flush().
        #
        # The execution of task.unlink() looks like this:
        # - mark 'project_id' to compute on subtasks
        # - delete task
        # - flush()
        #   - recompute 'project_id' on subtask1
        #     - call compute on subtask1
        #     - in action, search([('id', 'in', subtask1.ids), ('project_id', '=', pid)])
        #       - flush(['id', 'project_id'])
        #         - recompute 'project_id' on subtask2
        #           - call compute on subtask2
        #           - in action search([('id', 'in', subtask2.ids), ('project_id', '=', pid)])
        #             - flush(['id', 'project_id'])
        #               - recompute 'project_id' on subtask3
        #                 - call compute on subtask3
        #                 - in action, search([('id', 'in', subtask3.ids), ('project_id', '=', pid)])
        #                   - flush(['id', 'project_id'])
        #                     - recompute 'project_id' on subtask4
        #                       ...
        limit = sys.getrecursionlimit()
        try:
            sys.setrecursionlimit(100)
            task.unlink()
        finally:
            sys.setrecursionlimit(limit)

    def test_mail_triggers(self):
        lead_model = self.env["ir.model"]._get("base.automation.lead.test")
        with self.assertRaises(ValidationError):
            create_automation(self, trigger="on_message_sent", model_id=lead_model.id)

        lead_thread_model = self.env["ir.model"]._get("base.automation.lead.thread.test")
        automation = create_automation(self, trigger="on_message_sent", model_id=lead_thread_model.id, _actions={
            "state": "object_write",
            "update_path": "active",
            "update_boolean_value": "false"
        })

        ext_partner = self.env["res.partner"].create({"name": "ext", "email": "email@server.com"})
        internal_partner = self.env["res.users"].browse(2).partner_id

        obj = self.env["base.automation.lead.thread.test"].create({"name": "test"})
        obj.message_subscribe([ext_partner.id, internal_partner.id])

        obj.message_post(author_id=internal_partner.id, message_type="comment", subtype_xmlid="mail.mt_comment")
        self.assertFalse(obj.active)

        obj.active = True
        obj.message_post(author_id=internal_partner.id, subtype_xmlid="mail.mt_comment")
        self.assertTrue(obj.active)

        obj.message_post(author_id=ext_partner.id, message_type="comment")
        self.assertTrue(obj.active)

        obj.message_post(author_id=internal_partner.id, message_type="comment")
        self.assertTrue(obj.active)
        obj.message_post(author_id=internal_partner.id, subtype_xmlid="mail.mt_comment", message_type="comment")
        self.assertFalse(obj.active)

        obj.active = True
        # message doesn't have author_id, so it should be considered as external the automation should't be triggered
        obj.message_post(author_id=False, email_from="test_abla@test.test", message_type="email", subtype_xmlid="mail.mt_comment")
        self.assertTrue(obj.active)

        automation.trigger = "on_message_received"
        obj.active = True
        obj.message_post(author_id=internal_partner.id, subtype_xmlid="mail.mt_comment", message_type="comment")
        self.assertTrue(obj.active)

        obj.message_post(author_id=ext_partner.id, message_type="comment")
        self.assertTrue(obj.active)

        obj.message_post(author_id=ext_partner.id, subtype_xmlid="mail.mt_comment", message_type="comment")
        self.assertFalse(obj.active)

        obj.active = True
        obj.message_post(author_id=ext_partner.id, subtype_xmlid="mail.mt_comment")
        self.assertTrue(obj.active)

        obj.message_post(author_id=False, email_from="test_abla@test.test", message_type="email", subtype_xmlid="mail.mt_comment")
        self.assertFalse(obj.active)

    def test_multiple_mail_triggers(self):
        lead_model = self.env["ir.model"]._get("base.automation.lead.test")
        with self.assertRaises(ValidationError):
            create_automation(self, trigger="on_message_sent", model_id=lead_model.id)

        lead_thread_model = self.env["ir.model"]._get("base.automation.lead.thread.test")

        create_automation(self, trigger="on_message_sent", model_id=lead_thread_model.id, _actions={
            "state": "object_write",
            "update_path": "active",
            "update_boolean_value": "false"
        })
        create_automation(self, trigger="on_message_sent", model_id=lead_thread_model.id, _actions={
            "state": "object_write",
            "evaluation_type": "equation",
            "update_path": "name",
            "value": "record.name + '!'"
        })

        ext_partner = self.env["res.partner"].create({"name": "ext", "email": "email@server.com"})
        internal_partner = self.env["res.users"].browse(2).partner_id

        obj = self.env["base.automation.lead.thread.test"].create({"name": "test"})
        obj.message_subscribe([ext_partner.id, internal_partner.id])

        obj.message_post(author_id=internal_partner.id, message_type="comment", subtype_xmlid="mail.mt_comment")
        self.assertFalse(obj.active)
        self.assertEqual(obj.name, "test!")

    def test_compute_on_create(self):
        lead_model = self.env['ir.model']._get('base.automation.lead.test')
        stage_field = self.env['ir.model.fields']._get('base.automation.lead.test', 'stage_id')
        new_stage = self.env['test_base_automation.stage'].create({'name': 'New'})

        create_automation(
            self,
            model_id=lead_model.id,
            trigger='on_stage_set',
            trigger_field_ids=[stage_field.id],
            _actions={
                'state': 'object_create',
                'crud_model_id': self.env['ir.model']._get('res.partner').id,
                'value': "Test Partner Automation",
            },
            filter_domain=repr([('stage_id', '=', new_stage.id)]),
        )

        # Tricky case: the record is created with 'stage_id' being false, and
        # the field is marked for recomputation.  The field is then recomputed
        # while evaluating 'filter_domain', which causes the execution of the
        # automation.  And as the domain is satisfied, the automation is
        # processed again, but it must detect that it has just been run!
        self.env['base.automation.lead.test'].create({
            'name': 'Test Lead',
        })

        # check that the automation has been run once
        partner_count = self.env['res.partner'].search_count([('name', '=', 'Test Partner Automation')])
        self.assertEqual(partner_count, 1, "Only one partner should have been created")

    def test_00_form_save_update_related_model_id(self):
        with Form(self.env['ir.actions.server'], view="base.view_server_action_form") as f:
            f.name = "Test Action"
            f.model_id = self.env["ir.model"]._get("res.partner")
            f.state = "object_write"
            f.update_path = "user_id"
            f.evaluation_type = "value"
            f.resource_ref = "res.users,2"

        res_users_model = self.env["ir.model"]._get("res.users")
        self.assertEqual(f.update_related_model_id, res_users_model)

    def test_01_form_object_write_o2m_field(self):
        aks_partner = self.env["res.partner"].create({"name": "A Kind Shepherd"})
        bs_partner = self.env["res.partner"].create({"name": "Black Sheep"})

        # test the 'object_write' type shows a resource_ref field for o2many
        f = Form(self.env['ir.actions.server'], view="base.view_server_action_form")
        f.name = "Adopt The Black Sheep"
        f.model_id = self.env["ir.model"]._get("res.partner")
        f.state = "object_write"
        f.evaluation_type = "value"
        f.update_path = "child_ids"
        self.assertEqual(f.update_m2m_operation, "add")
        self.assertEqual(f.value_field_to_show, "resource_ref")
        f.resource_ref = f"res.partner,{bs_partner.id}"
        action = f.save()

        # test the action runs correctly
        action.with_context(
            active_model="res.partner",
            active_id=aks_partner.id,
        ).run()
        self.assertEqual(aks_partner.child_ids, bs_partner)
        self.assertEqual(bs_partner.parent_id, aks_partner)

        # also check with 'remove' operation
        f.update_m2m_operation = "remove"
        action = f.save()
        action.with_context(
            active_model="res.partner",
            active_id=aks_partner.id,
        ).run()
        self.assertEqual(aks_partner.child_ids.ids, [])
        self.assertEqual(bs_partner.parent_id.id, False)

@common.tagged("post_install", "-at_install")
class TestHttp(common.HttpCase):
    def test_webhook_trigger(self):
        model = self.env["ir.model"]._get("base.automation.linked.test")
        record_getter = "model.search([('name', '=', payload['name'])]) if payload.get('name') else None"
        automation = create_automation(self, trigger="on_webhook", model_id=model.id, record_getter=record_getter, _actions={
            "state": "object_write",
            "update_path": "another_field",
            "value": "written"
        })

        obj = self.env[model.model].create({"name": "some name"})
        response = self.url_open(automation.url, data=json.dumps({"name": "some name"}))
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(obj.another_field, "written")

        obj.another_field = False
        with mute_logger("odoo.addons.base_automation.models.base_automation"):
            response = self.url_open(automation.url, data=json.dumps({}))
        self.assertEqual(response.json(), {"status": "error"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(obj.another_field, False)

        response = self.url_open("/web/hook/0123456789", data=json.dumps({"name": "some name"}))
        self.assertEqual(response.json(), {"status": "error"})
        self.assertEqual(response.status_code, 404)

    def test_payload_in_action_server(self):
        model = self.env["ir.model"]._get("base.automation.linked.test")
        record_getter = "model.search([('name', '=', payload['name'])]) if payload.get('name') else None"
        automation = create_automation(self, trigger="on_webhook", model_id=model.id, record_getter=record_getter, _actions={
            "state": "code",
            "code": "record.write({'another_field': json.dumps(payload)})"
        })

        obj = self.env[model.model].create({"name": "some name"})
        self.url_open(automation.url, data=json.dumps({"name": "some name", "test_key": "test_value"}), headers={"Content-Type": "application/json"})
        self.assertEqual(json.loads(obj.another_field), {
            "name": "some name",
            "test_key": "test_value",
        })

        obj.another_field = ""
        self.url_open(automation.url + "?test_param=test_value&name=some%20name")
        self.assertEqual(json.loads(obj.another_field), {
            "name": "some name",
            "test_param": "test_value",
        })

    def test_webhook_send_and_receive(self):
        model = self.env["ir.model"]._get("base.automation.linked.test")
        obj = self.env[model.model].create({"name": "some name"})

        automation_receiver = create_automation(self, trigger="on_webhook", model_id=model.id, _actions={
            "state": "code",
            "code": "record.write({'another_field': json.dumps(payload)})"
        })
        name_field_id = self.env.ref("test_base_automation.field_base_automation_linked_test__name")
        automation_sender = create_automation(self, trigger="on_write", model_id=model.id, trigger_field_ids=[(6, 0, [name_field_id.id])], _actions={
            "name": "Send Webhook Notification",
            "state": "webhook",
            "webhook_url": automation_receiver.url,
        })

        obj.name = "new_name"
        self.cr.flush()
        self.cr.clear()
        self._wait_remaining_requests()  # just in case the request timeouts
        self.assertEqual(json.loads(obj.another_field), {
            '_action': f'Send Webhook Notification(#{automation_sender.action_server_ids[0].id})',
            "_id": obj.id,
            "_model": obj._name,
        })

    def test_on_change_get_views_cache(self):
        model_name = "base.automation.lead.test"
        my_view = self.env["ir.ui.view"].create({
            "name": "My View",
            "model": model_name,
            "type": "form",
            "arch": "<form><field name='active'/></form>",
        })
        self.assertEqual(
            self.env[model_name].get_view(my_view.id)["arch"],
            '<form><field name="active"/></form>'
        )
        model = self.env["ir.model"]._get(model_name)
        active_field = self.env["ir.model.fields"]._get(model_name, "active")
        create_automation(self, trigger="on_change", model_id=model.id, on_change_field_ids=[Command.set([active_field.id])], _actions={
            "state": "code",
            "code": "",
        })
        self.assertEqual(
            self.env[model_name].get_view(my_view.id)["arch"],
            '<form><field name="active" on_change="1"/></form>'
        )
