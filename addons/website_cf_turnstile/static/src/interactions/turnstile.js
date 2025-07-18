import { renderToElement } from "@web/core/utils/render";
import { session } from "@web/session";

export class TurnStile {
    static turnstileURL = "https://challenges.cloudflare.com/turnstile/v0/api.js";

    constructor(action) {
        const cf = new URLSearchParams(window.location.search).get("cf");
        const mode = cf == "show" ? "always" : "interaction-only";
        const turnstileContainer = renderToElement("website_cf_turnstile.turnstile_container", {
            action: action,
            appearance: mode,
            beforeInteractiveGlobalCallback: "turnstileBecomeVisible",
            errorGlobalCallback: "throwTurnstileErrorCode",
            executeGlobalCallback: "turnstileSuccess",
            sitekey: session.turnstile_site_key,
            style: "display: none;",
        });

        // Rethrow the error, or we only will catch a "Script error" without any info
        // because of the script api.js originating from a different domain.
        globalThis.throwTurnstileErrorCode = function (code) {
            const error = new Error("Turnstile Error");
            error.code = code;
            throw error;
        };
        // `this` is bound to the turnstile widget calling the callback
        globalThis.turnstileSuccess = function () {
            const form = this.wrapper.closest("form") || this.wrapper.parentElement.parentElement;
            const buttons = form.querySelectorAll(".cf_form_disabled");
            for (const button of buttons) {
                button.classList.remove("disabled", "cf_form_disabled");
            }
            form.querySelector("input.turnstile_captcha_valid").value = "done";
        };
        // unhide if interaction is needed
        globalThis.turnstileBecomeVisible = function () {
            const turnstileContainer = this.wrapper.parentElement;
            turnstileContainer.style.display = "";
        };
        // avoid modifying shape of return, for stable compatibility
        const script1El = document.createElement("script");

        // on first load of the remote script, all turnstile containers are rendered
        // if render=explicit is not set in the script url.
        // For subsequent insertion of turnstile containers, we need to call turnstile.render on the container
        // see `render`.
        const turnstileScript = renderToElement("website_cf_turnstile.turnstile_remote_script", {
            remoteScriptUrl: !window.turnstile?.render ? TurnStile.turnstileURL : "",
        });

        // avoid autosubmit from password manager
        const inputValidation = document.createElement("input");
        inputValidation.style = 'display: none;';
        inputValidation.className = 'turnstile_captcha_valid';
        inputValidation.required = true;

        this.turnstileEl = turnstileContainer;
        this.script1El = script1El;
        this.script2El = turnstileScript;
        this.inputValidation = inputValidation;
    }

    /**
     * Remove potential existing loaded script/token
     *
     * @param {HTMLElement} el
     */
    static clean(el) {
        const turnstileEls = el.querySelectorAll(".s_turnstile");
        turnstileEls.forEach(element => element.remove());
    }

    static disableSubmit(submitButton) {
        if (
            !submitButton.classList.contains("disabled") &&
            !submitButton.classList.contains("no_auto_disable")
        ) {
            submitButton.classList.add("disabled", "cf_form_disabled");
        }
    }

    /**
     * Insert scripts and invisible inputs into the form
     * Best called after `turnstileEl` is inserted
     */
    insertScripts(formEl) {
        formEl.appendChild(this.inputValidation);
        formEl.appendChild(this.script1El);
        if (!window.turnstile?.render) {
            formEl.appendChild(this.script2El);
        }
    }

    /**
     * Render the turnstile container generated by the constructor
     */
    render() {
        if (
            window.turnstile?.render &&
            this.turnstileEl &&
            !this.turnstileEl.querySelector("iframe")
        ) {
            window.turnstile.render(this.turnstileEl);
            return true;
        }
        return false;
    }
}
