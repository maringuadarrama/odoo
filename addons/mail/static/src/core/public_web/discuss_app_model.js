import { Record } from "@mail/core/common/record";
import { browser } from "@web/core/browser/browser";

const NO_MEMBERS_DEFAULT_OPEN_LS = "mail.user_setting.no_members_default_open";
export const DISCUSS_SIDEBAR_COMPACT_LS = "mail.user_setting.discuss_sidebar_compact";

export class DiscussApp extends Record {
    /** @returns {import("models").DiscussApp} */
    static get(data) {
        return super.get(data);
    }
    /** @returns {import("models").DiscussApp|import("models").DiscussApp[]} */
    static insert(data) {
        return super.insert(...arguments);
    }

    INSPECTOR_WIDTH = 300;
    /** @type {'main'|'channel'|'chat'|'livechat'} */
    activeTab = "main";
    searchTerm = "";
    isActive = false;
    isMemberPanelOpenByDefault = Record.attr(true, {
        compute() {
            return browser.localStorage.getItem(NO_MEMBERS_DEFAULT_OPEN_LS) !== "true";
        },
        /** @this {import("models").DiscussApp} */
        onUpdate() {
            if (this.isMemberPanelOpenByDefault) {
                browser.localStorage.removeItem(NO_MEMBERS_DEFAULT_OPEN_LS);
            } else {
                browser.localStorage.setItem(NO_MEMBERS_DEFAULT_OPEN_LS, "true");
            }
        },
    });
    isSidebarCompact = Record.attr(false, {
        compute() {
            return browser.localStorage.getItem(DISCUSS_SIDEBAR_COMPACT_LS) === "true";
        },
        /** @this {import("models").DiscussApp} */
        onUpdate() {
            if (this.isSidebarCompact) {
                browser.localStorage.setItem(
                    DISCUSS_SIDEBAR_COMPACT_LS,
                    this.isSidebarCompact.toString()
                );
            } else {
                browser.localStorage.removeItem(DISCUSS_SIDEBAR_COMPACT_LS);
            }
        },
    });
    thread = Record.one("Thread");
    hasRestoredThread = false;

    static new() {
        const record = super.new(...arguments);
        record.onStorage = record.onStorage.bind(record);
        browser.addEventListener("storage", record.onStorage);
        return record;
    }

    delete() {
        browser.removeEventListener("storage", this.onStorage);
        super.delete(...arguments);
    }

    onStorage(ev) {
        if (ev.key === DISCUSS_SIDEBAR_COMPACT_LS) {
            this.isSidebarCompact = ev.newValue === "true";
        }
        if (ev.key === NO_MEMBERS_DEFAULT_OPEN_LS) {
            this.isMemberPanelOpenByDefault = ev.newValue !== "true";
        }
    }
}

DiscussApp.register();
