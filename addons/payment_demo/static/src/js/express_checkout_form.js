
import { ConfirmationDialog } from '@web/core/confirmation_dialog/confirmation_dialog';
import { _t } from '@web/core/l10n/translation';
import { rpc } from '@web/core/network/rpc';
import { debounce } from '@web/core/utils/timing';
import publicWidget from '@web/legacy/js/public/public_widget';

import { paymentExpressCheckoutForm } from '@payment/js/express_checkout_form';
import paymentDemoMixin from '@payment_demo/js/payment_demo_mixin';

paymentExpressCheckoutForm.include({
    events: Object.assign({}, publicWidget.Widget.prototype.events, {
        'click button[name="o_payment_submit_button"]': '_initiateExpressPayment',
    }),

    // #=== WIDGET LIFECYCLE ===#

    /**
     * @override
     */
    start: async function () {
        await this._super(...arguments);
        document.querySelector('[name="o_payment_submit_button"]')?.removeAttribute('disabled');
        this._initiateExpressPayment = debounce(this._initiateExpressPayment, 500, true);
    },

    // #=== EVENT HANDLERS ===#

    /**
     * Process the payment.
     *
     * @private
     * @param {Event} ev
     * @return {void}
     */
    async _initiateExpressPayment(ev) {
        ev.stopPropagation();
        ev.preventDefault();

        const shippingInformationRequired = document.querySelector(
            '[name="o_payment_express_checkout_form"]'
        ).dataset.shippingInfoRequired;
        const providerId = ev.target.parentElement.dataset.providerId;
        let expressDeliveryAddress = {};
        if (shippingInformationRequired){
            const shippingInfo = document.querySelector(
                `#o_payment_demo_shipping_info_${providerId}`
            );
            expressDeliveryAddress = {
                'name': shippingInfo.querySelector('#o_payment_demo_shipping_name').value,
                'email': shippingInfo.querySelector('#o_payment_demo_shipping_email').value,
                'street': shippingInfo.querySelector('#o_payment_demo_shipping_address').value,
                'street2': shippingInfo.querySelector('#o_payment_demo_shipping_address2').value,
                'zip': shippingInfo.querySelector('#o_payment_demo_shipping_zip').value,
                'city': shippingInfo.querySelector('#o_payment_demo_shipping_city').value,
                'country': shippingInfo.querySelector('#o_payment_demo_shipping_country').value,
            };
            // Call the shipping address update route to fetch the shipping options.
            const { delivery_methods } = await rpc(
                this.paymentContext['shippingAddressUpdateRoute'],
                {partial_delivery_address: expressDeliveryAddress},
            );
            if (delivery_methods.length > 0) {
                const id = parseInt(delivery_methods[0].id);
                await rpc('/shop/set_delivery_method', {dm_id: id});
            } else {
                this.call('dialog', 'add', ConfirmationDialog, {
                    title: _t("Validation Error"),
                    body: _t("No delivery method is available."),
                });
                return;
            }
        }
        await rpc(
            document.querySelector(
                '[name="o_payment_express_checkout_form"]'
            ).dataset['expressCheckoutRoute'],
            {
                'shipping_address': expressDeliveryAddress,
                'billing_address': {
                    'name': 'Demo User',
                    'email': 'demo@test.com',
                    'street': 'Rue des Bourlottes 9',
                    'street2': '23',
                    'country': 'BE',
                    'city':'Ramillies',
                    'zip':'1367'
                },
            }
        );
        const processingValues = await rpc(
            this.paymentContext['transactionRoute'],
            this._prepareTransactionRouteParams(providerId),
        )
        paymentDemoMixin.processDemoPayment(processingValues);
    },
});
