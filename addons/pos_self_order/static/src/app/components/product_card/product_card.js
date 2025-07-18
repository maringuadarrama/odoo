import { Component, useRef } from "@odoo/owl";
import { useSelfOrder } from "@pos_self_order/app/services/self_order_service";
import { useService, useForwardRefToParent } from "@web/core/utils/hooks";
import { ProductInfoPopup } from "@pos_self_order/app/components/product_info_popup/product_info_popup";

export class ProductCard extends Component {
    static template = "pos_self_order.ProductCard";
    static props = ["productTemplate", "currentProductCard?"];

    selfRef = useRef("selfProductCard");
    currentProductCardRef = useRef("currentProductCard");

    setup() {
        this.selfOrder = useSelfOrder();
        this.router = useService("router");
        this.dialog = useService("dialog");

        useForwardRefToParent("currentProductCard");
    }

    flyToCart() {
        const productCardEl = this.selfRef.el;
        if (!productCardEl) {
            return;
        }

        const toOrder = document.querySelector(".to-order");
        if (!toOrder || window.getComputedStyle(toOrder).display === "none") {
            return;
        }

        let pic = this.selfRef.el.querySelector(".o_self_order_item_card_image");
        if (!pic) {
            pic = this.selfRef.el.querySelector(".o_self_order_item_card_no_image");
        }

        const picRect = pic.getBoundingClientRect();
        const clonedPic = pic.cloneNode(true);
        const toOrderRect = toOrder.getBoundingClientRect();

        clonedPic.classList.remove("w-100", "h-100");
        clonedPic.classList.add("position-fixed", "border", "border-white", "border-4", "z-1");
        clonedPic.style.top = `${picRect.top}px`;
        clonedPic.style.left = `${picRect.left}px`;
        clonedPic.style.width = `${picRect.width}px`;
        clonedPic.style.height = `${picRect.height}px`;
        clonedPic.style.transition = "all 400ms cubic-bezier(0.6, 0, 0.9, 1.000)";

        document.body.appendChild(clonedPic);

        requestAnimationFrame(() => {
            const offsetTop = toOrderRect.top - picRect.top - picRect.height * 0.5;
            const offsetLeft = toOrderRect.left - picRect.left - picRect.width * 0.25;
            clonedPic.style.transform =
                "translateY(" + offsetTop + "px) translateX(" + offsetLeft + "px) scale(0.5)";
            clonedPic.style.opacity = "0"; // Fading out the card
        });

        clonedPic.addEventListener("transitionend", () => {
            clonedPic.remove();
        });
    }

    get isAvailable() {
        if (this.props.productTemplate.pos_categ_ids.length === 0) {
            return true;
        }

        return this.props.productTemplate.pos_categ_ids.some((categ) =>
            this.selfOrder.isCategoryAvailable(categ.id)
        );
    }

    scaleUpPrice() {
        const priceElement = document.querySelector(".total-price");

        if (!priceElement) {
            return;
        }

        priceElement.classList.add("scale-up");

        setTimeout(() => {
            priceElement.classList.remove("scale-up");
        }, 600);
    }

    async selectProduct(qty = 1) {
        const product = this.props.productTemplate;

        if (!product.self_order_available || !this.isAvailable) {
            return;
        }

        if (product.isCombo()) {
            const selectedCombos = [];
            let showComboSelectionPage = false;
            for (const combo of product.combo_ids) {
                const { combo_item_ids } = combo;
                if (combo_item_ids.length > 1 || combo_item_ids[0]?.product_id.isConfigurable()) {
                    showComboSelectionPage = true;
                    break;
                }
                selectedCombos.push({
                    combo_item_id: this.selfOrder.models["product.combo.item"].get(
                        combo_item_ids[0].id
                    ),
                    configuration: {
                        attribute_custom_values: [],
                        attribute_value_ids: [],
                        price_extra: 0,
                    },
                });
            }

            if (showComboSelectionPage) {
                this.router.navigate("combo_selection", { id: product.id });
            } else {
                this.flyToCart();
                this.selfOrder.editedLine?.delete();
                this.selfOrder.addToCart(product, 1, "", {}, {}, selectedCombos);
            }
        } else if (product.isConfigurable()) {
            this.router.navigate("product", { id: product.id });
        } else {
            if (!this.selfOrder.ordering) {
                return;
            }
            this.flyToCart();
            this.scaleUpPrice();

            this.selfOrder.addToCart(product, qty);
        }
    }

    showProductInfo() {
        this.dialog.add(ProductInfoPopup, {
            productTemplate: this.props.productTemplate,
            addToCart: (qty) => {
                this.selectProduct(qty);
            },
        });
    }
}
