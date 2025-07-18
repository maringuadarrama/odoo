# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, api, tools
from odoo.tools.misc import str2bool
from odoo.exceptions import UserError


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def web_create_users(self, emails):
        emails_normalized = [tools.mail.parse_contact_from_email(email)[1] for email in emails]

        if 'email_normalized' not in self._fields:
            raise UserError(self.env._("You have to install the Discuss application to use this feature."))

        # Reactivate already existing users if needed
        deactivated_users = self.with_context(active_test=False).search([
            ('active', '=', False),
            '|', ('login', 'in', emails + emails_normalized), ('email_normalized', 'in', emails_normalized)])
        for user in deactivated_users:
            user.active = True
        done = deactivated_users.mapped('email_normalized')

        new_emails = set(emails) - set(deactivated_users.mapped('email'))

        # Process new email addresses : create new users
        for email in new_emails:
            name, email_normalized = tools.mail.parse_contact_from_email(email)
            if email_normalized in done:
                continue
            default_values = {'login': email_normalized, 'name': name or email_normalized, 'email': email_normalized, 'active': True}
            user = self.with_context(signup_valid=True).create(default_values)

        return True

    def _default_groups(self):
        """Default groups for employees

        If base_setup.default_user_rights is set, only the "Employee" group is used
        """
        if not str2bool(self.env['ir.config_parameter'].sudo().get_param("base_setup.default_user_rights"), default=False):
            return self.env.ref("base.group_user")
        return super()._default_groups()

    def _apply_groups_to_existing_employees(self):
        """
        If base_setup.default_user_rights is set, do not apply any new groups to existing employees
        """
        if not str2bool(self.env['ir.config_parameter'].sudo().get_param("base_setup.default_user_rights"), default=False):
            return False
        return super()._apply_groups_to_existing_employees()
