# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.addons.mail.tools.discuss import Store
from odoo.tools import email_normalize, email_split, html2plaintext, plaintext2html

from markupsafe import Markup


class DiscussChannel(models.Model):
    """ Chat Session
        Reprensenting a conversation between users.
        It extends the base method for anonymous usage.
    """

    _name = 'discuss.channel'
    _inherit = ['rating.mixin', 'discuss.channel']

    anonymous_name = fields.Char('Anonymous Name')
    channel_type = fields.Selection(selection_add=[('livechat', 'Livechat Conversation')], ondelete={'livechat': 'cascade'})
    duration = fields.Float('Duration', compute='_compute_duration', help='Duration of the session in hours')
    livechat_active = fields.Boolean('Is livechat ongoing?', help='Livechat session is active until visitor or operator leaves the conversation.')
    livechat_channel_id = fields.Many2one('im_livechat.channel', 'Channel', index='btree_not_null')
    livechat_operator_id = fields.Many2one('res.partner', string='Operator', index='btree_not_null')
    chatbot_current_step_id = fields.Many2one('chatbot.script.step', string='Chatbot Current Step')
    chatbot_message_ids = fields.One2many('chatbot.message', 'discuss_channel_id', string='Chatbot Messages')
    country_id = fields.Many2one('res.country', string="Country", help="Country of the visitor of the channel")

    _livechat_operator_id = models.Constraint(
        "CHECK((channel_type = 'livechat' and livechat_operator_id is not null) or (channel_type != 'livechat'))",
        'Livechat Operator ID is required for a channel of type livechat.',
    )

    _livechat_active_idx = models.Index("(livechat_active) WHERE livechat_active IS TRUE")

    @api.depends('message_ids')
    def _compute_duration(self):
        for record in self:
            start = record.message_ids[-1].date if record.message_ids else record.create_date
            end = record.message_ids[0].date if record.message_ids else fields.Datetime.now()
            record.duration = (end - start).total_seconds() / 3600

    def _sync_field_names(self):
        return super()._sync_field_names() + ["livechat_operator_id"]

    def _field_store_repr(self, field_name):
        if field_name == "livechat_operator_id":
            return [
                # sudo - res.partner: accessing livechat operator is allowed
                Store.One(
                    "livechat_operator_id", ["avatar_128", "user_livechat_username"], sudo=True
                )
            ]
        return super()._field_store_repr(field_name)

    def _to_store_defaults(self, for_current_user=True):
        fields = [
            "anonymous_name",
            "chatbot_current_step",
            "livechat_active",
            Store.One("country_id", ["code", "name"], rename="anonymous_country"),
            "livechat_operator_id",
        ]
        if self.env.user._is_internal():
            fields.append(Store.One("livechat_channel_id", ["name"], rename="livechatChannel"))
        return super()._to_store_defaults(for_current_user=for_current_user) + fields

    def _to_store(self, store: Store, fields):
        """Extends the channel header by adding the livechat operator and the 'anonymous' profile"""
        super()._to_store(store, [f for f in fields if f != "chatbot_current_step"])
        if "chatbot_current_step" not in fields:
            return
        lang = self.env["chatbot.script"]._get_chatbot_language()
        for channel in self.filtered(lambda channel: channel.chatbot_current_step_id):
            # sudo: chatbot.script.step - returning the current script/step of the channel
            current_step_sudo = channel.chatbot_current_step_id.sudo().with_context(lang=lang)
            chatbot_script = current_step_sudo.chatbot_script_id
            step_message = self.env["chatbot.message"]
            if not current_step_sudo.is_forward_operator:
                step_message = channel.sudo().chatbot_message_ids.filtered(
                    lambda m: m.script_step_id == current_step_sudo
                    and m.mail_message_id.author_id == chatbot_script.operator_partner_id
                )[:1]
            current_step = {
                "scriptStep": current_step_sudo.id,
                "message": step_message.mail_message_id.id,
                "operatorFound": current_step_sudo.is_forward_operator
                and channel.livechat_operator_id != chatbot_script.operator_partner_id,
            }
            store.add(current_step_sudo)
            store.add(chatbot_script)
            chatbot_data = {
                "script": chatbot_script.id,
                "steps": [current_step],
                "currentStep": current_step,
            }
            store.add(channel, {"chatbot": chatbot_data})

    @api.autovacuum
    def _gc_empty_livechat_sessions(self):
        hours = 1  # never remove empty session created within the last hour
        self.env.cr.execute("""
            SELECT id as id
            FROM discuss_channel C
            WHERE NOT EXISTS (
                SELECT 1
                FROM mail_message M
                WHERE M.res_id = C.id AND m.model = 'discuss.channel'
            ) AND C.channel_type = 'livechat' AND livechat_channel_id IS NOT NULL AND
                COALESCE(write_date, create_date, (now() at time zone 'UTC'))::timestamp
                < ((now() at time zone 'UTC') - interval %s)""", ("%s hours" % hours,))
        empty_channel_ids = [item['id'] for item in self.env.cr.dictfetchall()]
        self.browse(empty_channel_ids).unlink()

    def execute_command_history(self, **kwargs):
        self._bus_send("im_livechat.history_command", {"id": self.id})

    def _get_visitor_leave_message(self, operator=False, cancel=False):
        return _('Visitor left the conversation.')

    def _close_livechat_session(self, **kwargs):
        """ Set deactivate the livechat channel and notify (the operator) the reason of closing the session."""
        self.ensure_one()
        if self.livechat_active:
            member = self.channel_member_ids.filtered(lambda m: m.is_self)
            if member:
                # sudo: discuss.channel.rtc.session - member of current user can leave call
                member.sudo()._rtc_leave_call()
            # sudo: discuss.channel - visitor left the conversation, state must be updated
            self.sudo().livechat_active = False
            self.sudo()._bus_send_store(Store(self, "livechat_active"))
            # avoid useless notification if the channel is empty
            if not self.message_ids:
                return
            # Notify that the visitor has left the conversation
            # sudo: mail.message - posting visitor leave message is allowed
            self.sudo().message_post(
                author_id=self.env.ref('base.partner_root').id,
                body=Markup('<div class="o_mail_notification o_hide_author">%s</div>')
                % self._get_visitor_leave_message(**kwargs),
                message_type='notification',
                subtype_xmlid='mail.mt_comment'
            )

    # Rating Mixin

    def _rating_get_parent_field_name(self):
        return 'livechat_channel_id'

    def _email_livechat_transcript(self, email):
        company = self.env.user.company_id
        render_context = {
            "company": company,
            "channel": self,
        }
        mail_body = self.env['ir.qweb']._render('im_livechat.livechat_email_template', render_context, minimal_qcontext=True)
        mail_body = self.env['mail.render.mixin']._replace_local_links(mail_body)
        mail = self.env['mail.mail'].sudo().create({
            'subject': _('Conversation with %s', self.livechat_operator_id.user_livechat_username or self.livechat_operator_id.name),
            'email_from': company.catchall_formatted or company.email_formatted,
            'author_id': self.env.user.partner_id.id,
            'email_to': email_split(email)[0],
            'body_html': mail_body,
        })
        mail.send()

    def _get_channel_history(self):
        """
        Converting message body back to plaintext for correct data formatting in HTML field.
        """
        self.ensure_one()
        parts = []
        # sudo: res.partner: accessing chat bot partner is acceptable to build channel history.
        chatbot_op = self.sudo().chatbot_message_ids[
            :1
        ].script_step_id.chatbot_script_id.operator_partner_id
        last_msg_from_chatbot = False
        # sudo - mail.message: getting empty messages to exclude them is allowed.
        for message in (self.message_ids - self.message_ids.sudo()._filter_empty()).sorted("id"):
            if message.author_id == chatbot_op and not last_msg_from_chatbot:
                parts.append(Markup("<br/>"))
            if message.author_id == chatbot_op:
                parts.append(Markup("<strong>%s</strong><br/>") % html2plaintext(message.body))
            else:
                parts.append(Markup("%s<br/>") % html2plaintext(message.body))
            last_msg_from_chatbot = message.author_id == chatbot_op
        return Markup("").join(parts)


    # =======================
    # Chatbot
    # =======================

    def _chatbot_find_customer_values_in_messages(self, step_type_to_field):
        """
        Look for user's input in the channel's messages based on a dictionary
        mapping the step_type to the field name of the model it will be used on.

        :param dict step_type_to_field: a dict of step types to customer fields
            to fill, like : {'question_email': 'email_from', 'question_phone': 'mobile'}
        """
        values = {}
        filtered_message_ids = self.chatbot_message_ids.filtered(
            # sudo: chatbot.script.step - getting the type of the current step
            lambda m: m.script_step_id.sudo().step_type in step_type_to_field
        )
        for message_id in filtered_message_ids:
            field_name = step_type_to_field[message_id.script_step_id.step_type]
            if not values.get(field_name):
                values[field_name] = html2plaintext(message_id.user_raw_answer or '')

        return values

    def _chatbot_post_message(self, chatbot_script, body):
        """ Small helper to post a message as the chatbot operator

        :param record chatbot_script
        :param string body: message HTML body """
        # sudo: mail.message - chat bot is allowed to post a message which
        # requires reading its partner among other things.
        return self.with_context(mail_post_autofollow_author_skip=True).sudo().message_post(
            author_id=chatbot_script.sudo().operator_partner_id.id,
            body=body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

    def _chatbot_validate_email(self, email_address, chatbot_script):
        email_address = html2plaintext(email_address)
        email_normalized = email_normalize(email_address)

        posted_message = False
        error_message = False
        if not email_normalized:
            error_message = _(
                "'%(input_email)s' does not look like a valid email. Can you please try again?",
                input_email=email_address
            )
            posted_message = self._chatbot_post_message(chatbot_script, plaintext2html(error_message))

        return {
            'success': bool(email_normalized),
            'posted_message': posted_message,
            'error_message': error_message,
        }

    def _message_post_after_hook(self, message, msg_vals):
        """
        This method is called just before _notify_thread() method which is calling the _to_store()
        method. We need a 'chatbot.message' record before it happens to correctly display the message.
        It's created only if the mail channel is linked to a chatbot step. We also need to save the
        user answer if the current step is a question selection.
        """
        if self.chatbot_current_step_id:
            selected_answer = (
                self.env["chatbot.script.answer"]
                .browse(self.env.context.get("selected_answer_id"))
                .exists()
            )
            if selected_answer in self.chatbot_current_step_id.answer_ids:
                # sudo - chatbot.message: finding the question message to update the user answer is allowed.
                question_msg = (
                    self.env["chatbot.message"]
                    .sudo()
                    .search(
                        [
                            ("discuss_channel_id", "=", self.id),
                            ("script_step_id", "=", self.chatbot_current_step_id.id),
                        ],
                        order="id DESC",
                        limit=1,
                    )
                )
                question_msg.user_script_answer_id = selected_answer
                if store := self.env.context.get("message_post_store"):
                    store.add(message, for_current_user=True).add(question_msg.mail_message_id)

            self.env["chatbot.message"].sudo().create(
                {
                    "mail_message_id": message.id,
                    "discuss_channel_id": self.id,
                    "script_step_id": self.chatbot_current_step_id.id,
                }
            )

        return super()._message_post_after_hook(message, msg_vals)

    def _chatbot_restart(self, chatbot_script):
        # sudo: discuss.channel - visitor can clear current step to restart the script
        self.sudo().chatbot_current_step_id = False
        # sudo: discuss.channel - visitor can reactivate livechat
        self.sudo().livechat_active = True
        # sudo: chatbot.message - visitor can clear chatbot messages to restart the script
        self.sudo().chatbot_message_ids.unlink()
        return self._chatbot_post_message(
            chatbot_script,
            Markup('<div class="o_mail_notification">%s</div>') % _('Restarting conversation...'),
        )

    def _types_allowing_seen_infos(self):
        return super()._types_allowing_seen_infos() + ["livechat"]

    def _types_allowing_unfollow(self):
        return super()._types_allowing_unfollow() + ["livechat"]

    def _action_unfollow(self, partner=None, guest=None, post_leave_message=True):
        super()._action_unfollow(partner, guest, post_leave_message)
        # sudo - discuss.channel: user just left but we need to close the live
        # chat if the last operator left.
        channel_sudo = self.sudo()
        if channel_sudo.livechat_active and len(channel_sudo.channel_member_ids) == 1:
            # sudo: discuss.channel - last operator left the conversation, state must be updated.
            channel_sudo.livechat_active = False
            self._bus_send_store(self, "livechat_active")
