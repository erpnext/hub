# Copyright (c) 2015, Web Notes Technologies Pvt. Ltd. and Contributors and contributors
# For license information, please see license.txt

import frappe, json
from frappe.utils import now

@frappe.whitelist(allow_guest=True)
def register(enabled, hub_user_name, email, company, country, publish, seller_website=None, seller_city=None,
		seller_description=None):
	"""Register on the hub."""
	hub_user = frappe.new_doc("Hub User")
	for key in ("enabled", "hub_user_name", "email", "company", "country", "publish", "seller_website", "seller_city", "seller_description"):
		hub_user.set(key, locals()[key])
	hub_user.insert(ignore_permissions=True)
	return hub_user.as_dict()

@frappe.whitelist(allow_guest=True)
def update_user_details(password, args):
	hub_user = get_user(password)
	for key, val in json.loads(args).iteritems():
		hub_user.set(key, val)
	hub_user.save(ignore_permissions=True)

@frappe.whitelist(allow_guest=True)
def unpublish(password):
	"""Un publish seller"""
	hub_user = get_user(password)
	if hub_user:
		hub_user.publish = 0
		hub_user.save(ignore_permissions=True)

@frappe.whitelist(allow_guest=True)
def delete(password, item_code):
	"""Delete item on portal"""
	hub_user = get_user(password)
	item = frappe.db.get_value("Hub Item", {"item_code": item_code, "hub_user": hub_user.name})
	if item:
		frappe.delete_doc("Hub Item", item)

@frappe.whitelist(allow_guest=True)
def sync(password, items, item_list):
	"""Sync new items"""
	hub_user = get_user(password)
	# delete if not in item list
	all_items = frappe.db.sql_list("select item_code from `tabHub Item` where hub_user=%s", hub_user.name)
	item_list = json.loads(item_list)
	for item in all_items:
		if item not in item_list:
			frappe.delete_doc("Hub Item", item)

	# insert / update items
	for item in json.loads(items):
		item_code = frappe.db.get_value("Hub Item",
			{"hub_user": hub_user.name, "item_code": item.get("item_code")})
		if item_code:
			hub_item = frappe.get_doc("Hub Item", item_code)
		else:
			hub_item = frappe.new_doc("Hub Item")
			hub_item.hub_user = hub_user.name

		for key in ("item_code", "item_name", "description", "image", "item_group", "price", "stock_qty", "stock_uom"):
			hub_item.set(key, item.get(key))

		for key in ("hub_user_name", "email", "country", "seller_city"):
			hub_item.set(key, hub_user.get(key))

		hub_item.published = 1
		hub_item.save(ignore_permissions=True)
	return frappe._dict({"last_sync_datetime":now()})

@frappe.whitelist(allow_guest=True)
def get_items(password, text, country=None, start=0, limit=50):
	"""Returns list of items by filters"""
	get_user(password)
	or_filters = [
		{"item_name": ["like", "%{0}%".format(text)]},
		{"description": ["like", "%{0}%".format(text)]}
	]
	filters = {
		"published": 1
	}
	if country:
		filters["country"] = country
	return frappe.get_all("Hub Item", fields=["item_code", "item_name", "description", "image",
		"hub_user_name", "email", "country", "seller_city"],
			filters=filters, or_filters=or_filters, limit_start = start, limit_page_length = limit)

def get_user(password):
	return frappe.get_doc("Hub User", {"password": password})