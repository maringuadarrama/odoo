import { expect, test } from "@odoo/hoot";
import { click, press, waitFor, queryOne } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { cleanLinkArtifacts } from "@html_editor/../tests/_helpers/format";
import { getContent, setSelection } from "@html_editor/../tests/_helpers/selection";
import { setupEditor } from "@html_editor/../tests/_helpers/editor";
import { contains, defineModels, onRpc, serverState, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { click as mailClick, mailModels, openFormView, start } from "@mail/../tests/mail_test_helpers";
import { insertText } from "@html_editor/../tests/_helpers/user_actions";
import { HtmlField } from "@html_editor/fields/html_field";

defineModels(mailModels);

test("autocomplete should shown and able to edit the link", async () => {
    onRpc("/website/get_suggested_links", () => {
        expect.step("/website/get_suggested_links");
        return {
            matching_pages: [
                {
                    value: "/contactus",
                    label: "/contactus (Contact Us)",
                },
            ],
            others: [
                {
                    title: "Apps url",
                    values: [
                        {
                            value: "/contactus",
                            icon: "/website/static/description/icon.png",
                            label: "/contactus (Contact Us)",
                        },
                    ],
                },
            ],
        };
    });

    const { el } = await setupEditor('<p>this is a <a href="http://test.com/">li[]nk</a></p>');

    await waitFor(".o-we-linkpopover");
    await click(".o_we_edit_link");
    await animationFrame();
    // the url input should be autocomplete
    await contains(".o-autocomplete--input").focus();

    // autocomplete dropdown should be there
    await press(["ctrl", "a"]);
    await press("c");
    await waitFor(".o-autocomplete--dropdown-menu", { timeout: 3000 });
    expect.verifySteps(["/website/get_suggested_links"]);

    expect(".ui-autocomplete-category").toHaveCount(1);
    expect(".o-autocomplete--dropdown-item img").toHaveCount(1);

    await click(".o-autocomplete--dropdown-item:first");
    await click(".o_we_apply_link");
    // the url should be applied after selecting a dropdown item
    expect(cleanLinkArtifacts(getContent(el))).toBe(
        '<p>this is a <a href="/contactus">li[]nk</a></p>'
    );

    await waitFor(".o_we_edit_link");
    await click(".o_we_edit_link");
    await animationFrame();
    await contains(".o-autocomplete--input").focus();

    await press(["ctrl", "a"]);
    await press("#");
    await waitFor(".o-autocomplete--dropdown-menu", { timeout: 3000 });
    // check the default page anchors are in the autocomplete dropdown
    expect(".o-autocomplete--dropdown-item:first").toHaveText("#top");
    expect(".o-autocomplete--dropdown-item:last").toHaveText("#bottom");
});

test("LinkPopover opens in full composer", async () => {

    let htmlEditor;
    mailModels.MailComposeMessage._views = {
        "form,false": `
        <form js_class="mail_composer_form">
            <field name="body" type="html" widget="html_composer_message"/>
        </form>`,
    };
    patchWithCleanup(HtmlField.prototype, {
        onEditorLoad(editor) {
            htmlEditor = editor;
            return super.onEditorLoad(...arguments);
        },
    });
    await start();
    await openFormView("res.partner", serverState.partnerId);
    await mailClick("button", { text: "Log note" });
    await mailClick("button[title='Open Full Composer']");
    await waitFor(".odoo-editor-editable");
    await insertText(htmlEditor, "test");
    const node = queryOne(".odoo-editor-editable div.o-paragraph");
    setSelection({ anchorNode: node, anchorOffset: 0, focusNode: node, focusOffset: 1 });
    await mailClick(".o-we-toolbar .fa-link");
    await waitFor(".o-we-linkpopover");
    await animationFrame();
    expect(".o-we-linkpopover").toHaveCount(1);
});
