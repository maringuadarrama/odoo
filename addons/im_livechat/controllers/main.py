# Part of Odoo. See LICENSE file for full copyright and licensing details.

from markupsafe import Markup
from werkzeug.exceptions import NotFound
from urllib.parse import urlsplit

from odoo import http, _
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import replace_exceptions
from odoo.addons.base.models.ir_qweb_fields import nl2br
from odoo.addons.mail.tools.discuss import add_guest_to_context, Store


class LivechatController(http.Controller):

    # Note: the `cors` attribute on many routes is meant to allow the livechat
    # to be embedded in an external website.

    @http.route('/im_livechat/external_lib.<any(css,js):ext>', type='http', auth='public', cors='*')
    def external_lib(self, ext, **kwargs):
        """ Preserve compatibility with legacy livechat imports. Only
        serves javascript since the css will be fetched by the shadow
        DOM of the livechat to avoid conflicts.
        """
        if ext == 'css':
            raise request.not_found()
        return self.assets_embed(ext, **kwargs)

    def _is_cors_request(self):
        headers = request.httprequest.headers
        origin_url = urlsplit(headers.get("referer"))
        return (
            origin_url.netloc != headers.get("host")
            or origin_url.scheme != request.httprequest.scheme
        )

    @http.route('/im_livechat/assets_embed.<any(css, js):ext>', type='http', auth='public', cors='*')
    def assets_embed(self, ext, **kwargs):
        # If the request comes from a different origin, we must provide the CORS
        # assets to enable the redirection of routes to the CORS controller.
        bundle = "im_livechat.assets_embed_cors" if self._is_cors_request() else "im_livechat.assets_embed_external"
        asset = request.env["ir.qweb"]._get_asset_bundle(bundle)
        if ext not in ('css', 'js'):
            raise request.not_found()
        stream = request.env['ir.binary']._get_stream_from(getattr(asset, ext)())
        return stream.get_response()

    @http.route('/im_livechat/font-awesome', type='http', auth='none', cors="*")
    def fontawesome(self, **kwargs):
        return http.Stream.from_path('web/static/src/libs/fontawesome/fonts/fontawesome-webfont.woff2').get_response()

    @http.route('/im_livechat/odoo_ui_icons', type='http', auth='none', cors="*")
    def odoo_ui_icons(self, **kwargs):
        return http.Stream.from_path('web/static/lib/odoo_ui_icons/fonts/odoo_ui_icons.woff2').get_response()

    @http.route('/im_livechat/emoji_bundle', type='http', auth='public', cors='*')
    def get_emoji_bundle(self):
        bundle = 'web.assets_emoji'
        asset = request.env["ir.qweb"]._get_asset_bundle(bundle)
        stream = request.env['ir.binary']._get_stream_from(asset.js())
        return stream.get_response()

    @http.route('/im_livechat/support/<int:channel_id>', type='http', auth='public')
    def support_page(self, channel_id, **kwargs):
        channel = request.env['im_livechat.channel'].sudo().browse(channel_id)
        return request.render('im_livechat.support_page', {'channel': channel})

    @http.route('/im_livechat/loader/<int:channel_id>', type='http', auth='public')
    def loader(self, channel_id, **kwargs):
        username = kwargs.get("username", _("Visitor"))
        channel = request.env['im_livechat.channel'].sudo().browse(channel_id)
        info = channel.get_livechat_info(username=username)
        return request.render('im_livechat.loader', {'info': info}, headers=[('Content-Type', 'application/javascript')])

    @http.route('/im_livechat/init', type='jsonrpc', auth="public")
    @add_guest_to_context
    def livechat_init(self, channel_id):
        operator_available = len(request.env['im_livechat.channel'].sudo().browse(channel_id).available_operator_ids)
        rule = {}
        store = Store()
        # find the country from the request
        country_id = False
        if request.geoip.country_code:
            country_id = request.env['res.country'].sudo().search([('code', '=', request.geoip.country_code)], limit=1).id
        # extract url
        url = request.httprequest.headers.get('Referer')
        # find the first matching rule for the given country and url
        if matching_rule := request.env['im_livechat.channel.rule'].sudo().match_rule(channel_id, url, country_id):
            matching_rule = matching_rule.with_context(lang=request.env['chatbot.script']._get_chatbot_language())
            rule = {
                "action": matching_rule.action,
                "auto_popup_timer": matching_rule.auto_popup_timer,
                "regex_url": matching_rule.regex_url,
            }
            if chatbot_script := matching_rule.chatbot_script_id:
                rule.update({"chatbotScript": chatbot_script.id})
                store.add(chatbot_script)
        store = Store()
        request.env["res.users"]._init_store_data(store)
        return {
            'available_for_me': bool((rule and rule.get('chatbotScript'))
                                or operator_available and (not rule or rule['action'] != 'hide_button')),
            'rule': rule,
            'storeData': store.get_result(),
        }

    def _get_guest_name(self):
        return _("Visitor")

    @http.route('/im_livechat/get_session', methods=["POST"], type="jsonrpc", auth='public')
    @add_guest_to_context
    def get_session(self, channel_id, anonymous_name, previous_operator_id=None, chatbot_script_id=None, persisted=True):
        store = Store()
        user_id = None
        country_id = None
        channel = request.env["discuss.channel"]
        guest = request.env["mail.guest"]
        # if the user is identifiy (eg: portal user on the frontend), don't use the anonymous name. The user will be added to session.
        if request.session.uid:
            user_id = request.env.user.id
            country_id = request.env.user.country_id.id
        else:
            # if geoip, add the country name to the anonymous name
            if request.geoip.country_code:
                # get the country of the anonymous person, if any
                country = request.env['res.country'].sudo().search([('code', '=', request.geoip.country_code)], limit=1)
                if country:
                    country_id = country.id

        if previous_operator_id:
            previous_operator_id = int(previous_operator_id)

        chatbot_script = request.env["chatbot.script"]
        if chatbot_script_id:
            chatbot_script = request.env['chatbot.script'].sudo().with_context(
                lang=request.env["chatbot.script"]._get_chatbot_language()
            ).browse(chatbot_script_id)
        channel_vals = request.env["im_livechat.channel"].with_context(lang=False).sudo().browse(channel_id)._get_livechat_discuss_channel_vals(
            anonymous_name,
            previous_operator_id=previous_operator_id,
            chatbot_script=chatbot_script,
            user_id=user_id,
            country_id=country_id,
            lang=request.cookies.get('frontend_lang')
        )
        if not channel_vals:
            return False
        if not persisted:
            chatbot_data = None
            if chatbot_script:
                welcome_steps = chatbot_script._get_welcome_steps()
                chatbot_data = {
                    "script": chatbot_script.id,
                    "steps": welcome_steps.mapped(lambda s: {"scriptStep": s.id}),
                }
                store.add(chatbot_script)
                store.add(welcome_steps)
            operator = request.env["res.partner"].sudo().browse(channel_vals["livechat_operator_id"])
            channel_info = {
                "fetchChannelInfoState": "fetched",
                "id": -1,  # only one temporary thread at a time, id does not matter.
                "isLoaded": True,
                "livechat_operator_id": Store.One(
                    operator, ["avatar_128", "user_livechat_username"]
                ),
                "name": channel_vals["name"],
                "scrollUnread": False,
                "livechat_active": True,
                "channel_type": "livechat",
                "chatbot": chatbot_data,
            }
            store.add_model_values("discuss.channel", channel_info)
        else:
            channel = request.env['discuss.channel'].with_context(
                mail_create_nosubscribe=False,
                lang=request.env['chatbot.script']._get_chatbot_language()
            ).sudo().create(channel_vals)
            if chatbot_script:
                chatbot_script._post_welcome_steps(channel)
            with replace_exceptions(UserError, by=NotFound()):
                # sudo: mail.guest - creating a guest and their member in a dedicated channel created from livechat
                __, guest = channel.sudo()._find_or_create_persona_for_channel(
                    guest_name=self._get_guest_name(),
                    country_code=request.geoip.country_code,
                    timezone=request.env['mail.guest']._get_timezone_from_request(request),
                    post_joined_message=False
                )
            channel = channel.with_context(guest=guest)  # a new guest was possibly created
            if not chatbot_script or chatbot_script.operator_partner_id != channel.livechat_operator_id:
                channel._broadcast([channel.livechat_operator_id.id])
            if guest:
                store.add_global_values(guest_token=guest._format_auth_cookie())
        request.env["res.users"].with_context(guest=guest)._init_store_data(store)
        guest._bus_send_store(store)
        # Make sure not to send the channel on the guest bus, otherwise
        # "isLoaded" value could be overwritten.
        if channel:
            store.add(
                channel,
                extra_fields={
                    "isLoaded": not chatbot_script,
                    "scrollUnread": False,
                },
            )
        return store.get_result()

    def _post_feedback_message(self, channel, rating, reason):
        body = Markup(
            """<div class="o_mail_notification o_hide_author">"""
            """%(rating)s: <img class="o_livechat_emoji_rating" src="%(rating_url)s" alt="rating"/>%(reason)s"""
            """</div>"""
        ) % {
            "rating": _("Rating"),
            "rating_url": rating.rating_image_url,
            "reason": nl2br("\n" + reason) if reason else "",
        }
        # sudo: discuss.channel - not necessary for posting, but necessary to update related rating
        channel.sudo().message_post(
            body=body,
            message_type="notification",
            rating_id=rating.id,
            subtype_xmlid="mail.mt_comment",
        )

    @http.route("/im_livechat/feedback", type="jsonrpc", auth="public")
    @add_guest_to_context
    def feedback(self, channel_id, rate, reason=None, **kwargs):
        if channel := request.env["discuss.channel"].search([("id", "=", channel_id)]):
            # limit the creation : only ONE rating per session
            values = {
                'rating': rate,
                'consumed': True,
                'feedback': reason,
                'is_internal': False,
            }
            # sudo: rating.rating - visitor can access rating to check if
            # feedback was already given
            if not channel.sudo().rating_ids:
                values.update({
                    'res_id': channel.id,
                    'res_model_id': request.env['ir.model']._get_id('discuss.channel'),
                })
                # sudo: res.partner - visitor must find the operator to rate
                if channel.sudo().channel_partner_ids:
                    values['rated_partner_id'] = channel.channel_partner_ids[0].id
                # if logged in user, set its partner on rating
                values['partner_id'] = request.env.user.partner_id.id if request.session.uid else False
                # create the rating
                rating = request.env['rating.rating'].sudo().create(values)
            else:
                rating = channel.rating_ids[0]
                # sudo: rating.rating - guest or portal user can update their livechat rating
                rating.sudo().write(values)
            self._post_feedback_message(channel, rating, reason)
            return rating.id
        return False

    @http.route("/im_livechat/history", type="jsonrpc", auth="public")
    @add_guest_to_context
    def history_pages(self, pid, channel_id, page_history=None):
        if channel := request.env["discuss.channel"].search([("id", "=", channel_id)]):
            if pid in channel.sudo().channel_member_ids.partner_id.ids:
                request.env["res.partner"].browse(pid)._bus_send_history_message(channel, page_history)

    @http.route("/im_livechat/email_livechat_transcript", type="jsonrpc", auth="public")
    @add_guest_to_context
    def email_livechat_transcript(self, channel_id, email):
        if channel := request.env["discuss.channel"].search([("id", "=", channel_id)]):
            channel._email_livechat_transcript(email)

    @http.route("/im_livechat/visitor_leave_session", type="jsonrpc", auth="public")
    @add_guest_to_context
    def visitor_leave_session(self, channel_id):
        """Called when the livechat visitor leaves the conversation.
        This will clean the chat request and warn the operator that the conversation is over.
        This allows also to re-send a new chat request to the visitor, as while the visitor is
        in conversation with an operator, it's not possible to send the visitor a chat request."""
        if channel := request.env["discuss.channel"].search([("id", "=", channel_id)]):
            channel._close_livechat_session()
