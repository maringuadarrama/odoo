# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import requests
from odoo.addons.microsoft_calendar.models.microsoft_sync import microsoft_calendar_token
from datetime import datetime, timedelta

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError
from odoo.loglevels import exception_to_unicode
from odoo.addons.microsoft_account.models import microsoft_service
from odoo.addons.microsoft_calendar.utils.microsoft_calendar import InvalidSyncToken
from odoo.tools import str2bool

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    microsoft_calendar_sync_token = fields.Char(related='res_users_settings_id.microsoft_calendar_sync_token', groups='base.group_system')
    microsoft_synchronization_stopped = fields.Boolean(related='res_users_settings_id.microsoft_synchronization_stopped', readonly=False, groups='base.group_system')
    microsoft_last_sync_date = fields.Datetime(related='res_users_settings_id.microsoft_last_sync_date', readonly=False, groups='base.group_system')

    def _microsoft_calendar_authenticated(self):
        return bool(self.sudo().microsoft_calendar_rtoken)

    def _get_microsoft_calendar_token(self):
        if not self:
            return None

        self.ensure_one()
        if self.sudo().microsoft_calendar_rtoken and not self._is_microsoft_calendar_valid():
            self._refresh_microsoft_calendar_token()
        return self.sudo().microsoft_calendar_token

    def _is_microsoft_calendar_valid(self):
        return self.sudo().microsoft_calendar_token_validity and self.sudo().microsoft_calendar_token_validity >= (fields.Datetime.now() + timedelta(minutes=1))

    def _refresh_microsoft_calendar_token(self, service='calendar'):
        self.ensure_one()
        try:
            access_token, ttl = self.env['microsoft.service']._refresh_microsoft_token('calendar', self.sudo().microsoft_calendar_rtoken)
            self.sudo().write({
                'microsoft_calendar_token': access_token,
                'microsoft_calendar_token_validity': fields.Datetime.now() + timedelta(seconds=ttl),
            })
        except requests.HTTPError as error:
            if error.response.status_code in (400, 401):  # invalid grant or invalid client
                # Delete refresh token and make sure it's commited
                self.env.cr.rollback()
                self.sudo().write({
                    'microsoft_calendar_rtoken': False,
                    'microsoft_calendar_token': False,
                    'microsoft_calendar_token_validity': False,
                })
                self.res_users_settings_id.sudo().write({
                    'microsoft_calendar_sync_token': False
                })
                self.env.cr.commit()
            error_key = error.response.json().get("error", "nc")
            error_msg = _(
                "An error occurred while generating the token. Your authorization code may be invalid or has already expired [%s]. "
                "You should check your Client ID and secret on the Microsoft Azure portal or try to stop and restart your calendar synchronisation.",
                error_key)
            raise UserError(error_msg)

    def _get_microsoft_sync_status(self):
        """ Returns the calendar synchronization status (active, paused or stopped). """
        status = "sync_active"
        if str2bool(self.env['ir.config_parameter'].sudo().get_param("microsoft_calendar_sync_paused"), default=False):
            status = "sync_paused"
        elif self.sudo().microsoft_calendar_token and not self.sudo().microsoft_synchronization_stopped:
            status = "sync_active"
        elif self.sudo().microsoft_synchronization_stopped:
            status = "sync_stopped"
        return status

    def _sync_microsoft_calendar(self):
        self.ensure_one()
        self.sudo().microsoft_last_sync_date = datetime.now()
        if self._get_microsoft_sync_status() != "sync_active":
            return False

        # Set the first synchronization date as an ICP parameter before writing the variable
        # 'microsoft_calendar_sync_token' below, so we identify the first synchronization.
        self._set_ICP_first_synchronization_date(fields.Datetime.now())

        calendar_service = self.env["calendar.event"]._get_microsoft_service()
        full_sync = not bool(self.sudo().microsoft_calendar_sync_token)
        with microsoft_calendar_token(self) as token:
            try:
                events, next_sync_token = calendar_service.get_events(self.sudo().microsoft_calendar_sync_token, token=token)
            except InvalidSyncToken:
                events, next_sync_token = calendar_service.get_events(token=token)
                full_sync = True
        self.res_users_settings_id.sudo().microsoft_calendar_sync_token = next_sync_token

        # Microsoft -> Odoo
        synced_events, synced_recurrences = self.env['calendar.event']._sync_microsoft2odoo(events) if events else (self.env['calendar.event'], self.env['calendar.recurrence'])

        # Odoo -> Microsoft
        recurrences = self.env['calendar.recurrence']._get_microsoft_records_to_sync(full_sync=full_sync)
        recurrences -= synced_recurrences
        recurrences._sync_odoo2microsoft()
        synced_events |= recurrences.calendar_event_ids

        events = self.env['calendar.event']._get_microsoft_records_to_sync(full_sync=full_sync)
        (events - synced_events)._sync_odoo2microsoft()
        self.sudo().microsoft_last_sync_date = datetime.now()

        return bool(events | synced_events) or bool(recurrences | synced_recurrences)

    @api.model
    def _sync_all_microsoft_calendar(self):
        """ Cron job """
        users = self.env['res.users'].sudo().search([('microsoft_calendar_rtoken', '!=', False), ('microsoft_synchronization_stopped', '=', False)])
        for user in users:
            _logger.info("Calendar Synchro - Starting synchronization for %s", user)
            try:
                user.with_user(user).sudo()._sync_microsoft_calendar()
                self.env.cr.commit()
            except Exception as e:
                _logger.exception("[%s] Calendar Synchro - Exception : %s!", user, exception_to_unicode(e))
                self.env.cr.rollback()

    def stop_microsoft_synchronization(self):
        self.ensure_one()
        self.sudo().microsoft_synchronization_stopped = True
        self.sudo().microsoft_last_sync_date = None

    def restart_microsoft_synchronization(self):
        self.ensure_one()
        self.sudo().microsoft_last_sync_date = datetime.now()
        self.sudo().microsoft_synchronization_stopped = False
        self.env['calendar.recurrence']._restart_microsoft_sync()
        self.env['calendar.event']._restart_microsoft_sync()

    def unpause_microsoft_synchronization(self):
        self.env['ir.config_parameter'].sudo().set_param("microsoft_calendar_sync_paused", False)

    def pause_microsoft_synchronization(self):
        self.env['ir.config_parameter'].sudo().set_param("microsoft_calendar_sync_paused", True)

    @api.model
    def _has_setup_microsoft_credentials(self):
        """ Checks if both Client ID and Client Secret are defined in the database. """
        ICP_sudo = self.env['ir.config_parameter'].sudo()
        client_id = self.env['microsoft.service']._get_microsoft_client_id('calendar')
        client_secret = microsoft_service._get_microsoft_client_secret(ICP_sudo, 'calendar')
        return bool(client_id and client_secret)

    @api.model
    def check_calendar_credentials(self):
        res = super().check_calendar_credentials()
        res['microsoft_calendar'] = self._has_setup_microsoft_credentials()
        return res

    def check_synchronization_status(self):
        res = super().check_synchronization_status()
        credentials_status = self.check_calendar_credentials()
        sync_status = 'missing_credentials'
        if credentials_status.get('microsoft_calendar'):
            sync_status = self._get_microsoft_sync_status()
            if sync_status == 'sync_active' and not self.sudo().microsoft_calendar_token:
                sync_status = 'sync_stopped'
        res['microsoft_calendar'] = sync_status
        return res

    def _has_any_active_synchronization(self):
        """
        Check if synchronization is active for Microsoft Calendar.
        This function retrieves the synchronization status from the user's environment
        and checks if the Microsoft Calendar synchronization is active.

        :return: Action to delete the event
        """
        sync_status = self.check_synchronization_status()
        res = super()._has_any_active_synchronization()
        if sync_status.get('microsoft_calendar') == 'sync_active':
            return True
        return res

    def _set_ICP_first_synchronization_date(self, now):
        """
        Set the first synchronization date as an ICP parameter when applicable (param not defined yet
        and calendar never synchronized before). This parameter is used for not synchronizing previously
        created Odoo events and thus avoid spamming invitations for those events.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        first_synchronization_date = ICP.get_param('microsoft_calendar.sync.first_synchronization_date')

        if not first_synchronization_date:
            # Check if any calendar has synchronized before by checking the user's tokens.
            any_calendar_synchronized = self.env['res.users'].sudo().search_count(
                domain=[('microsoft_calendar_sync_token', '!=', False)],
                limit=1
            )

            # Check if any user synchronized its calendar before by saving the date token.
            # Add one minute of time diff for avoiding write time delay conflicts with the next sync methods.
            if not any_calendar_synchronized:
                ICP.set_param('microsoft_calendar.sync.first_synchronization_date', now - timedelta(minutes=1))
