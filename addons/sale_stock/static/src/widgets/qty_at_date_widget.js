import { formatDateTime } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/core/popover/popover_hook";
import { Component, onWillRender } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { roundPrecision } from "@web/core/utils/numbers";

export class QtyAtDatePopover extends Component {
    static template = "sale_stock.QtyAtDatePopover";
    static props = {
        record: Object,
        calcData: Object,
        close: Function,
    };
    setup() {
        this.actionService = useService("action");
    }

    openForecast() {
        this.actionService.doAction("stock.stock_forecasted_product_product_action", {
            additionalContext: {
                active_model: 'product.product',
                active_id: this.props.record.data.product_id[0],
                warehouse_id: this.props.record.data.warehouse_id && this.props.record.data.warehouse_id[0],
                move_to_match_ids: this.props.record.data.move_ids.records.map(record => record.resId),
                sale_line_to_match_id: this.props.record.resId,
            },
        });
    }
}


export class QtyAtDateWidget extends Component {
    static components = { Popover: QtyAtDatePopover };
    static template = "sale_stock.QtyAtDate";
    static props = {...standardWidgetProps};
    setup() {
        this.popover = usePopover(this.constructor.components.Popover, { position: "top" });
        this.orm = useService("orm");
        this.calcData = {};
        onWillRender(async () => {
            await this.initCalcData();
        })
    }

    async initCalcData() {
        // calculate data not in record
        const { data } = this.props.record;
        let lineUom;
        if (data.product_uom_id?.[0]) {
            lineUom = (await this.orm.read("uom.uom", [data.product_uom_id[0]], ["factor", "rounding"]))[0];
        }
        let lineProduct;
        if (data.product_id?.[0]) {
            lineProduct = await this.orm.searchRead("product.product", [["id", "=", data.product_id[0]]], ["uom_id"]);
        }
        let productUom;
        if (lineProduct?.[0]?.uom_id?.[0]) {
            productUom = (await this.orm.searchRead("uom.uom", [["id", "=", lineProduct[0].uom_id[0]]], ["factor", "name"]))[0];
        }
        if (data.date_scheduled) {
            // TODO: might need some round_decimals to avoid errors
            if (data.state === 'sale') {
                this.calcData.will_be_fulfilled = data.qty_free_today >= data.qty_to_transfer;
            } else {
                this.calcData.will_be_fulfilled = data.qty_available_virtual_at_date >= data.qty_to_transfer;
            }
            this.calcData.will_be_late = data.date_planned_forecast && data.date_planned_forecast > data.date_scheduled;
            if (['draft', 'sent'].includes(data.state)) {
                // Moves aren't created yet, then the forecasted is only based on virtual_available of quant
                this.calcData.forecasted_issue = !this.calcData.will_be_fulfilled && !data.is_mto;
            } else {
                // Moves are created, using the forecasted data of related moves
                this.calcData.forecasted_issue = !this.calcData.will_be_fulfilled || this.calcData.will_be_late;
            }
        }
        if (lineUom && productUom) {
            this.calcData.product_uom_qty_available_virtual_at_date = roundPrecision(data.qty_available_virtual_at_date * lineUom.factor / productUom.factor, 1);
            this.calcData.product_uom_qty_free_today = roundPrecision(data.qty_free_today * lineUom.factor / productUom.factor, 1);
            this.calcData.product_uom_name = productUom.name;
        }
    }

    updateCalcData() {
        // popup specific data
        const { data } = this.props.record;
        if (!data.date_scheduled) {
            return;
        }
        this.calcData.delivery_date = formatDateTime(data.date_scheduled, { format: localization.dateFormat });
        if (data.date_planned_forecast) {
            this.calcData.date_planned_forecast_str = formatDateTime(data.date_planned_forecast, { format: localization.dateFormat });
        }
    }

    showPopup(ev) {
        this.updateCalcData();
        this.popover.open(ev.currentTarget, {
            record: this.props.record,
            calcData: this.calcData,
        });
    }
}

export const qtyAtDateWidget = {
    component: QtyAtDateWidget,
};
registry.category("view_widgets").add("qty_at_date_widget", qtyAtDateWidget);
