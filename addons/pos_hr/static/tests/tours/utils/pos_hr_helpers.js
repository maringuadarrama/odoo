import * as SelectionPopup from "@point_of_sale/../tests/generic_helpers/selection_popup_util";
import * as Dialog from "@point_of_sale/../tests/generic_helpers/dialog_util";
import * as NumberPopup from "@point_of_sale/../tests/generic_helpers/number_popup_util";

export function clickLoginButton() {
    return [
        {
            content: "click login button",
            trigger: ".login-overlay .select-cashier",
            run: "click",
        },
    ];
}
export function clickCashierName() {
    return [
        {
            content: "click cashier name",
            trigger: ".cashier-name",
            run: "click",
        },
    ];
}
export function loginScreenIsShown() {
    return [
        {
            content: "login screen is shown",
            trigger: ".login-overlay .screen-login",
        },
    ];
}
export function login(name, pin) {
    const res = [...clickLoginButton(), ...SelectionPopup.has(name, { run: "click" })];
    if (!pin) {
        return res;
    }
    return res.concat([
        ...NumberPopup.enterValue(pin),
        ...NumberPopup.isShown("••••"),
        Dialog.confirm(),
    ]);
}
export function clickLockButton() {
    return {
        content: "Click on the menu button",
        trigger: ".pos-rightheader i.fa-unlock",
        run: "click",
    };
}

export function refreshPage() {
    return [
        {
            trigger: ".pos",
            run: () => {
                window.location.reload();
            },
            expectUnloadPage: true,
        },
    ];
}
