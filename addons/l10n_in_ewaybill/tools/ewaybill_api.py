# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import contextlib

from datetime import timedelta
from markupsafe import Markup

from odoo import fields
from odoo.exceptions import AccessError
from odoo.addons.l10n_in_ewaybill.models.error_codes import ERROR_CODES
from odoo.tools import _, LazyTranslate


_logger = logging.getLogger(__name__)


class EWayBillError(Exception):

    def __init__(self, response):
        self.error_json = self._set_missing_error_message(response)
        self.error_json.setdefault('odoo_warning', [])
        self.error_codes = self.get_error_codes()
        super().__init__(response)

    def _set_missing_error_message(self, response):
        for error in response.get('error', []):
            if error.get('code') and not error.get('message'):
                error['message'] = self._find_missing_error_message(error.get('code'))
        return response

    @staticmethod
    def _find_missing_error_message(code):
        return (
            ERROR_CODES.get(code)
            or _("We don't know the error message for this error code. Please contact support.")
        )

    def get_all_error_message(self):
        return Markup("<br/>").join(
            ["[%s] %s" % (e.get("code"), e.get("message")) for e in self.error_json.get('error')]
        )

    def get_error_codes(self):
        return [e.get("code") for e in self.error_json['error']]


class EWayBillApi:

    def __init__(self, company):
        company.ensure_one()
        self.company = company
        self.env = self.company.env

    def _ewaybill_jsonrpc_to_server(self, url_path, params):
        params.update({
            "username": self.company.sudo().l10n_in_ewaybill_username,
            "gstin": self.company.vat,
        })
        try:
            response = self.env['iap.account']._l10n_in_connect_to_server(
                is_production=self.company.sudo().l10n_in_edi_production_env,
                params=params,
                url_path=url_path,
                config_parameter="l10n_in_edi_ewaybill.endpoint",
                timeout=10
            )
            if response.get('error'):
                raise EWayBillError(response)
        except AccessError as e:
            _logger.warning("Connection error: %s", e.args[0])
            raise EWayBillError({
                "error": [{
                    "code": "access_error",
                    "message": _(
                        "Unable to connect to the E-WayBill service."
                        "The web service may be temporary down. Please try again in a moment."
                    )
                }]
            })
        return response

    def _ewaybill_check_authentication(self):
        sudo_company = self.company.sudo()
        if sudo_company.l10n_in_ewaybill_username and sudo_company._l10n_in_ewaybill_token_is_valid():
            return True
        elif sudo_company.l10n_in_ewaybill_username and sudo_company.l10n_in_ewaybill_password:
            try:
                self._ewaybill_authenticate()
                return True
            except EWayBillError:
                return False
        return False

    def _ewaybill_authenticate(self):
        params = {"password": self.company.sudo().l10n_in_ewaybill_password}
        response = self._ewaybill_jsonrpc_to_server(
            url_path="/iap/l10n_in_edi_ewaybill/1/authenticate",
            params=params
        )
        if response and response.get("status_cd") == "1":
            self.company.sudo().l10n_in_ewaybill_auth_validity = (
                fields.Datetime.now()
                + timedelta(hours=6, minutes=00, seconds=00)
            )

    def _ewaybill_make_transaction(self, operation_type, json_payload):
        """
        :params operation_type: operation_type must be strictly `generate` or `cancel`
        :params json_payload: to be sent as params
        This method handles the common errors in generating and canceling the ewaybill
        """
        try:
            if not self._ewaybill_check_authentication():
                self._raise_ewaybill_no_config_error()
            params = {"json_payload": json_payload}
            url_path = f"/iap/l10n_in_edi_ewaybill/1/{operation_type}"
            response = self._ewaybill_jsonrpc_to_server(
                url_path=url_path,
                params=params
            )
            return response
        except EWayBillError as e:
            if "no-credit" in e.error_codes:
                e.error_json['odoo_warning'].append({
                    'message': self.env['account.move']._l10n_in_edi_get_iap_buy_credits_message()
                })
                raise

            if '238' in e.error_codes:
                # Invalid token eror then create new token and send generate request again.
                # This happens when authenticate called from another odoo instance with same credentials
                # (like. Demo/Test)
                with contextlib.suppress(EWayBillError):
                    self._ewaybill_authenticate()
                return self._ewaybill_jsonrpc_to_server(
                    url_path=url_path,
                    params=params,
                )

            if operation_type == "cancel" and "312" in e.error_codes:
                # E-waybill is already canceled
                # this happens when timeout from the Government portal but IRN is generated
                # Avoid raising error in this case, since it is already cancelled
                response = e.error_json
                response['odoo_warning'].append({
                    'message': Markup("%s<br/>%s:<br/>%s") % (
                        self.env['l10n.in.ewaybill']._get_default_help_message(
                            self.env._('cancelled')
                        ),
                        _("Error"),
                        e.get_all_error_message()
                    ),
                    'message_post': True
                })
                # We return the error json as this a government document
                # On which in case of error 312, consider the ewaybill
                # as already cancelled
                return response

            if operation_type == "generate" and "604" in e.error_codes:
                # Get E-waybill by details in case of E-waybill is already generated
                # this happens when timeout from the Government portal but E-waybill is generated
                response = self._ewaybill_get_by_consigner(
                    document_type=json_payload.get("docType"),
                    document_number=json_payload.get("docNo")
                )
                return response
            raise

    def _ewaybill_generate(self, json_payload):
        return self._ewaybill_make_transaction("generate", json_payload)

    def _ewaybill_cancel(self, json_payload):
        return self._ewaybill_make_transaction("cancel", json_payload)

    def _ewaybill_get_by_consigner(self, document_type, document_number):
        if not self._ewaybill_check_authentication():
            self._raise_ewaybill_no_config_error()
        params = {"document_type": document_type, "document_number": document_number}
        response = self._ewaybill_jsonrpc_to_server(
            url_path="/iap/l10n_in_edi_ewaybill/1/getewaybillgeneratedbyconsigner",
            params=params
        )
        # Add warning that ewaybill was already generated
        response.update({
            'odoo_warning': [{
                'message': self.env['l10n.in.ewaybill']._get_default_help_message(
                    self.env._('generated')
                ),
                'message_post': True
            }]
        })
        return response

    @staticmethod
    def _raise_ewaybill_no_config_error():
        raise EWayBillError({
            "error": [{
                "code": "0",
                "message": _(
                    "Unable to send E-waybill."
                    "Create an API user in NIC portal, and set it using the top menu: "
                    "Configuration > Settings."
                )
            }]
        })
