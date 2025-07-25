# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields
from odoo.tools import groupby
from odoo.addons.mail.tools.discuss import Store


class MailMessageReaction(models.Model):
    _name = 'mail.message.reaction'
    _description = 'Message Reaction'
    _order = 'id desc'
    _log_access = False

    message_id = fields.Many2one(string="Message", comodel_name='mail.message', ondelete='cascade', required=True, readonly=True)
    content = fields.Char(string="Content", required=True, readonly=True)
    partner_id = fields.Many2one(string="Reacting Partner", comodel_name='res.partner', ondelete='cascade', readonly=True)
    guest_id = fields.Many2one(string="Reacting Guest", comodel_name='mail.guest', ondelete='cascade', readonly=True)

    _partner_unique = models.UniqueIndex("(message_id, content, partner_id) WHERE partner_id IS NOT NULL")
    _guest_unique = models.UniqueIndex("(message_id, content, guest_id) WHERE guest_id IS NOT NULL")

    _partner_or_guest_exists = models.Constraint(
        'CHECK((partner_id IS NOT NULL AND guest_id IS NULL) OR (partner_id IS NULL AND guest_id IS NOT NULL))',
        'A message reaction must be from a partner or from a guest.',
    )

    def _to_store(self, store: Store, fields):
        if fields:
            raise NotImplementedError("Fields are not supported for reactions.")
        self._persona_to_store(store)
        for (message_id, content), reactions in groupby(self, lambda r: (r.message_id, r.content)):
            reactions = self.env["mail.message.reaction"].union(*reactions)
            data = {
                "content": content,
                "count": len(reactions),
                "sequence": min(reactions.ids),
                "personas": Store.Many(reactions.guest_id)._get_id()
                + Store.Many(reactions.partner_id)._get_id(),
                "message": message_id.id,
            }
            store.add_model_values("MessageReactions", data)

    def _persona_to_store(self, store: Store):
        store.add(self.guest_id, ["avatar_128", "name"])
        store.add(self.partner_id, ["avatar_128", "name"])
