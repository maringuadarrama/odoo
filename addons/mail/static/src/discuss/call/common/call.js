import { CallActionList } from "@mail/discuss/call/common/call_action_list";
import { CallParticipantCard } from "@mail/discuss/call/common/call_participant_card";
import { PttAdBanner } from "@mail/discuss/call/common/ptt_ad_banner";
import { isEventHandled, markEventHandled } from "@web/core/utils/misc";
import { isMobileOS } from "@web/core/browser/feature_detection";

import {
    Component,
    onMounted,
    onPatched,
    onWillUnmount,
    toRaw,
    useExternalListener,
    useRef,
    useState,
} from "@odoo/owl";

import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

/**
 * @typedef CardData
 * @property {string} key
 * @property {import("models").RtcSession} session
 * @property {MediaStream} videoStream
 * @property {import("models").ChannelMember} [member]
 */

/**
 * @typedef {Object} Props
 * @property {import("models").Thread} thread
 * @property {boolean} [compact]
 * @extends {Component<Props, Env>}
 */
export class Call extends Component {
    static components = { CallActionList, CallParticipantCard, PttAdBanner };
    static props = ["thread", "compact?"];
    static template = "discuss.Call";

    overlayTimeout;

    setup() {
        super.setup();
        this.grid = useRef("grid");
        this.notification = useService("notification");
        this.rtc = useService("discuss.rtc");
        this.ui = useService("ui");
        this.isMobileOs = isMobileOS();
        this.state = useState({
            isFullscreen: false,
            sidebar: false,
            tileWidth: 0,
            tileHeight: 0,
            columnCount: 0,
            overlay: false,
            /** @type {CardData|undefined} */
            insetCard: undefined,
        });
        this.store = useService("mail.store");
        onMounted(() => {
            this.resizeObserver = new ResizeObserver(() => this.arrangeTiles());
            this.resizeObserver.observe(this.grid.el);
            this.arrangeTiles();
        });
        onPatched(() => this.arrangeTiles());
        onWillUnmount(() => {
            this.resizeObserver.disconnect();
            browser.clearTimeout(this.overlayTimeout);
        });
        useExternalListener(browser, "fullscreenchange", this.onFullScreenChange);
    }

    get isActiveCall() {
        return Boolean(this.props.thread.eq(this.rtc.channel));
    }

    get minimized() {
        if (this.state.isFullscreen || this.props.thread.activeRtcSession) {
            return false;
        }
        if (!this.isActiveCall || this.props.thread.videoCount === 0 || this.props.compact) {
            return true;
        }
        return false;
    }

    /** @returns {CardData[]} */
    get visibleCards() {
        const raisingHandCards = [];
        const sessionCards = [];
        const invitationCards = [];
        const filterVideos = this.store.settings.showOnlyVideo && this.props.thread.videoCount > 0;
        for (const session of this.props.thread.rtcSessions) {
            const target = session.raisingHand ? raisingHandCards : sessionCards;
            const cameraStream = session.is_camera_on
                ? session.videoStreams.get("camera")
                : undefined;
            if (!filterVideos || cameraStream) {
                target.push({
                    key: "session_main_" + session.id,
                    session,
                    type: "camera",
                    videoStream: cameraStream,
                });
            }
            const screenStream = session.is_screen_sharing_on
                ? session.videoStreams.get("screen")
                : undefined;
            if (screenStream) {
                target.push({
                    key: "session_secondary_" + session.id,
                    session,
                    type: "screen",
                    videoStream: screenStream,
                });
            }
        }
        if (!filterVideos) {
            for (const member of this.props.thread.invitedMembers) {
                invitationCards.push({
                    key: "member_" + member.id,
                    member,
                });
            }
        }
        raisingHandCards.sort((c1, c2) => c1.session.raisingHand - c2.session.raisingHand);
        sessionCards.sort(
            (c1, c2) =>
                c1.session.channel_member_id?.persona?.name?.localeCompare(
                    c2.session.channel_member_id?.persona?.name
                ) ?? 1
        );
        invitationCards.sort(
            (c1, c2) => c1.member.persona?.name?.localeCompare(c2.member.persona?.name) ?? 1
        );
        return raisingHandCards.concat(sessionCards, invitationCards);
    }

    /** @returns {CardData[]} */
    get visibleMainCards() {
        const activeSession = this.props.thread.activeRtcSession;
        if (!activeSession) {
            this.state.insetCard = undefined;
            return this.visibleCards;
        }
        const type = activeSession.mainVideoStreamType;
        if (type === "screen" || activeSession.is_screen_sharing_on) {
            this.setInset(activeSession, type === "camera" ? "screen" : "camera");
        } else {
            this.state.insetCard = undefined;
        }
        return [
            {
                key: "session_" + activeSession.id,
                session: activeSession,
                type,
                videoStream: activeSession.getStream(type),
            },
        ];
    }

    /**
     * @param {import("models").RtcSession} session
     * @param {String} [videoType]
     */
    setInset(session, videoType) {
        const key = "session_" + session.id;
        if (toRaw(this.state).insetCard?.key === key) {
            this.state.insetCard.type = videoType;
            this.state.insetCard.videoStream = session.getStream(videoType);
        } else {
            this.state.insetCard = {
                key,
                session,
                type: videoType,
                videoStream: session.getStream(videoType),
            };
        }
    }

    get hasCallNotifications() {
        return Boolean(
            (!this.props.compact || this.state.isFullscreen) &&
                this.isActiveCall &&
                this.rtc.notifications.size
        );
    }

    get hasSidebarButton() {
        return Boolean(
            this.props.thread.activeRtcSession && this.state.overlay && !this.props.compact
        );
    }

    get isControllerFloating() {
        return this.state.isFullscreen || (this.props.thread.activeRtcSession && !this.ui.isSmall);
    }

    onMouseleaveMain(ev) {
        if (ev.relatedTarget && ev.relatedTarget.closest(".o-dropdown--menu")) {
            // the overlay should not be hidden when the cursor leaves to enter the controller dropdown
            return;
        }
        this.state.overlay = false;
    }

    onMousemoveMain(ev) {
        if (isEventHandled(ev, "CallMain.MousemoveOverlay")) {
            return;
        }
        this.showOverlay();
    }

    onMousemoveOverlay(ev) {
        markEventHandled(ev, "CallMain.MousemoveOverlay");
        this.state.overlay = true;
        browser.clearTimeout(this.overlayTimeout);
    }

    showOverlay() {
        this.state.overlay = true;
        browser.clearTimeout(this.overlayTimeout);
        this.overlayTimeout = browser.setTimeout(() => {
            this.state.overlay = false;
        }, 3000);
    }

    arrangeTiles() {
        if (!this.grid.el) {
            return;
        }
        const { width, height } = this.grid.el.getBoundingClientRect();
        const aspectRatio = this.minimized ? 1 : 16 / 9;
        const tileCount = this.grid.el.children.length;
        let optimal = {
            area: 0,
            columnCount: 0,
            tileHeight: 0,
            tileWidth: 0,
        };
        for (let columnCount = 1; columnCount <= tileCount; columnCount++) {
            const rowCount = Math.ceil(tileCount / columnCount);
            const potentialHeight = width / (columnCount * aspectRatio);
            const potentialWidth = height / rowCount;
            let tileHeight;
            let tileWidth;
            if (potentialHeight > potentialWidth) {
                tileHeight = Math.floor(potentialWidth);
                tileWidth = Math.floor(tileHeight * aspectRatio);
            } else {
                tileWidth = Math.floor(width / columnCount);
                tileHeight = Math.floor(tileWidth / aspectRatio);
            }
            const area = tileHeight * tileWidth;
            if (area <= optimal.area) {
                continue;
            }
            optimal = {
                area,
                columnCount,
                tileHeight,
                tileWidth,
            };
        }
        Object.assign(this.state, {
            tileWidth: optimal.tileWidth,
            tileHeight: optimal.tileHeight,
            columnCount: optimal.columnCount,
        });
    }

    async enterFullScreen() {
        const el = document.body;
        try {
            if (el.requestFullscreen) {
                await el.requestFullscreen();
            } else if (el.mozRequestFullScreen) {
                await el.mozRequestFullScreen();
            } else if (el.webkitRequestFullscreen) {
                await el.webkitRequestFullscreen();
            }
            this.state.isFullscreen = true;
        } catch {
            this.state.isFullscreen = false;
            this.notification.add(_t("The Fullscreen mode was denied by the browser"), {
                type: "warning",
            });
        }
    }

    async exitFullScreen() {
        const fullscreenElement = document.webkitFullscreenElement || document.fullscreenElement;
        if (fullscreenElement) {
            if (document.exitFullscreen) {
                await document.exitFullscreen();
            } else if (document.mozCancelFullScreen) {
                await document.mozCancelFullScreen();
            } else if (document.webkitCancelFullScreen) {
                await document.webkitCancelFullScreen();
            }
        }
        this.state.isFullscreen = false;
    }

    /**
     * @private
     */
    onFullScreenChange() {
        this.state.isFullscreen = Boolean(
            document.webkitFullscreenElement || document.fullscreenElement
        );
    }
}
