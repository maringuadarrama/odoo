import { createDocumentFragmentFromContent } from "@mail/utils/common/html";

import { EventBus, useSubEnv } from "@odoo/owl";

import { x2ManyCommands } from "@web/core/orm_service";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

FormController.props = {
    ...FormController.props,
    fullComposerBus: { type: EventBus, optional: true },
};

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.env.services["mail.store"]) {
            this.mailStore = useService("mail.store");
        }
        useSubEnv({
            chatter: {
                fetchThreadData: true,
                fetchMessages: true,
            },
        });
    },
    onWillLoadRoot(nextConfiguration) {
        super.onWillLoadRoot(...arguments);
        this.env.chatter.fetchThreadData = true;
        this.env.chatter.fetchMessages = true;
        const isSameThread =
            this.model.root?.resId === nextConfiguration.resId &&
            this.model.root?.resModel === nextConfiguration.resModel;
        if (isSameThread) {
            // not first load
            const { resModel, resId } = this.model.root;
            this.env.bus.trigger("MAIL:RELOAD-THREAD", { model: resModel, id: resId });
        }
    },

    async onWillSaveRecord(record, changes) {
        if (record.resModel === "mail.compose.message") {
            const doc = createDocumentFragmentFromContent(changes.body);
            const partnerElements = doc.querySelectorAll('[data-oe-model="res.partner"]');
            const partnerIds = Array.from(partnerElements).map((element) =>
                parseInt(element.dataset.oeId)
            );
            if (partnerIds.length) {
                if (changes.partner_ids[0] && changes.partner_ids[0][0] === x2ManyCommands.SET) {
                    partnerIds.push(...changes.partner_ids[0][2]);
                }
                changes.partner_ids.push(...partnerIds.map((pid) => x2ManyCommands.link(pid)));
            }
        }
    },
});
