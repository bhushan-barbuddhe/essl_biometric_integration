frappe.ui.form.on("eSSL Integration Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Sync Now"), function () {
			frappe.call({
				method: "sync_now",
				doc: frm.doc,
				freeze: true,
				freeze_message: __("Syncing all enabled devices..."),
				callback: function (r) {
					if (r.exc) {
						frappe.show_alert({
							message: __("Sync failed. Check Error Log for details."),
							indicator: "red",
						});
						return;
					}

					const { synced = [], errors = [] } = r.message || {};

					if (errors.length) {
						const lines = errors
							.map(
								(e) =>
									`<b>${frappe.utils.escape_html(e.device)}</b>: ${frappe.utils.escape_html(e.error)}`
							)
							.join("<br>");
						frappe.msgprint({
							title: __("Sync Errors"),
							indicator: "red",
							message: lines,
						});
					}

					if (synced.length) {
						frappe.show_alert({
							message: __("Sync complete: {0}", [synced.join(", ")]),
							indicator: errors.length ? "orange" : "green",
						});
					} else if (!errors.length) {
						frappe.show_alert({
							message: __("No enabled devices found"),
							indicator: "blue",
						});
					}

					frm.reload_doc();
				},
			});
		});
	},
});
