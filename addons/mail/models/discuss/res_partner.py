# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.osv import expression
from odoo.tools import SQL
from odoo.addons.mail.tools.discuss import Store
from odoo.fields import Domain

class ResPartner(models.Model):
    _inherit = "res.partner"

    channel_ids = fields.Many2many(
        "discuss.channel",
        "discuss_channel_member",
        "partner_id",
        "channel_id",
        string="Channels",
        copy=False,
    )
    channel_member_ids = fields.One2many("discuss.channel.member", "partner_id")

    @api.readonly
    @api.model
    def search_for_channel_invite(self, search_term, channel_id=None, limit=30):
        """Returns partners matching search_term that can be invited to a channel.
        If the channel_id is specified, only partners that can actually be invited to the channel
        are returned (not already members, and in accordance to the channel configuration).
        """
        store = Store()
        count = self._search_for_channel_invite(store, search_term, channel_id, limit)
        return {"count": count, "data": store.get_result()}

    @api.readonly
    @api.model
    def _search_for_channel_invite(self, store: Store, search_term, channel_id=None, limit=30):
        domain = expression.AND(
            [
                expression.OR([
                    [("name", "ilike", search_term)],
                    [("email", "ilike", search_term)],
                ]),
                [('id', '!=', self.env.user.partner_id.id)],
                [("active", "=", True)],
                [("user_ids", "!=", False)],
                [("user_ids.active", "=", True)],
                [("user_ids.share", "=", False)],
            ]
        )
        channel = self.env["discuss.channel"]
        if channel_id:
            channel = self.env["discuss.channel"].search([("id", "=", int(channel_id))])
            domain = expression.AND([domain, [("channel_ids", "not in", channel.id)]])
            if channel.group_public_id:
                domain = expression.AND(
                    [domain, [("user_ids.all_group_ids", "in", channel.group_public_id.id)]]
                )
        query = self._search(domain, limit=limit)
        # bypass lack of support for case insensitive order in search()
        query.order = SQL('LOWER(%s), "res_partner"."id"', self._field_to_sql(self._table, "name"))
        self.env["res.partner"].browse(query)._search_for_channel_invite_to_store(store, channel)
        return self.env["res.partner"].search_count(domain)

    def _search_for_channel_invite_to_store(self, store: Store, channel):
        store.add(self)

    @api.readonly
    @api.model
    def get_mention_suggestions_from_channel(self, channel_id, search, limit=8):
        """Return 'limit'-first partners' such that the name or email matches a 'search' string.
        Prioritize partners that are also (internal) users, and then extend the research to all partners.
        Only members of the given channel are returned.
        The return format is a list of partner data (as per returned by `_to_store()`).
        """
        channel = self.env["discuss.channel"].search([("id", "=", channel_id)])
        if not channel:
            return []
        domain = expression.AND(
            [
                self._get_mention_suggestions_domain(search),
                [("channel_ids", "in", channel.id)],
            ]
        )
        extra_domain = expression.AND([
            [('user_ids', '!=', False)],
            [('user_ids.active', '=', True)],
            [('partner_share', '=', False)]
        ])
        allowed_group = (channel.parent_channel_id or channel).group_public_id
        if allowed_group:
            extra_domain = expression.AND(
                [
                    extra_domain,
                    [("user_ids.all_group_ids", "in", allowed_group.id)],
                ]
            )
        partners = self._search_mention_suggestions(domain, limit, extra_domain)
        members_domain = [("channel_id", "=", channel.id), ("partner_id", "in", partners.ids)]
        members = self.env["discuss.channel.member"].search(members_domain)
        member_fields = [
            Store.One("channel_id", [], as_thread=True, rename="thread"),
            *self.env["discuss.channel.member"]._to_store_persona([]),
        ]
        store = Store(members, member_fields).add(partners)
        store.add(channel, "group_public_id")
        if allowed_group:
            for p in partners:
                store.add(p, {"group_ids": [("ADD", (allowed_group & p.user_ids.all_group_ids).ids)]})
        return store.get_result()
