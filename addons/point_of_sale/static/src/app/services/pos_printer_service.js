import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { PrinterService } from "@point_of_sale/app/services/printer_service";
import { ConfirmationDialog, AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

export const posPrinterService = {
    dependencies: ["hardware_proxy", "dialog", "renderer"],
    start(env, { hardware_proxy, dialog, renderer }) {
        return new PosPrinterService(env, { hardware_proxy, dialog, renderer });
    },
};
export class PosPrinterService extends PrinterService {
    constructor(...args) {
        super(...args);
        this.setup(...args);
    }
    setup(env, { hardware_proxy, dialog, renderer }) {
        super.setup(...arguments);
        this.renderer = renderer;
        this.hardware_proxy = hardware_proxy;
        this.dialog = dialog;
        this.device = hardware_proxy.printer;
    }
    printWeb() {
        try {
            return super.printWeb(...arguments);
        } catch {
            this.dialog.add(AlertDialog, {
                title: _t("Printing is not supported on some browsers"),
                body: _t("It is possible to print your tickets by making use of an IoT Box."),
            });
            return false;
        }
    }
    async printHtml() {
        this.setPrinter(this.hardware_proxy.printer);
        try {
            return await super.printHtml(...arguments);
        } catch (error) {
            return this.printHtmlAlternative(error, ...arguments);
        }
    }
    async printHtmlAlternative(error, ...printArguments) {
        if (error.body === undefined) {
            console.error("An unknown error occured in printHtml:", error);
        }
        this.dialog.add(ConfirmationDialog, {
            title: error.title || _t("Printing error"),
            body: (error.body ?? "") + _t("Do you want to print using the web printer? "),
            confirm: async () => {
                // We want to call the _printWeb when the dialog is fully gone
                // from the screen which happens after the next animation frame.
                await new Promise(requestAnimationFrame);

                // Element is the first argument of the printHtml function
                this.printWeb(printArguments[0]);
            },
        });
    }
}

registry.category("services").add("printer", posPrinterService);
