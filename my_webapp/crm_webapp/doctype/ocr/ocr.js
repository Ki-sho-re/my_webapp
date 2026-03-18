frappe.ui.form.on("OCR", {
    refresh(frm) {
        if (!frm.is_new() && frm.doc.upload_file) {
            frm.add_custom_button("Fetch JSON", () => {
                frappe.call({
                    method: "my_webapp.crm_webapp.doctype.ocr.ocr.fetch_from_ai",
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: "Processing PDF with OpenAI...",
                    callback: function(r) {
                        if (!r.exc) {
                            frappe.msgprint("JSON Extracted Successfully!");
                            frm.reload_doc();
                        }
                    }
                });
            });
        }
    }
});

