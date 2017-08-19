# -*- coding: utf-8 -*-
# Copyright (c) 2015, Frappe and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe, json
from frappe.model.document import Document
from frappe.utils import random_string, now

class HubUser(Document):
	def autoname(self):
		access_token = random_string(16)
		self.access_token = access_token

	def update_user_details(self, args):
		self.old = frappe.get_doc('Hub User', self.name)
		for key, new_value in args.iteritems():
			old_value = self.old.get(key)
			if(new_value != old_value):
				self.set(key, new_value)

	def unpublish(self):
		"""Un publish seller, delete items"""
		self.publish = 0

	def delete(self, item_code):
		"""Delete item on portal"""
		item = frappe.db.get_value("Hub Item", {"item_code": item_code, "hub_user_name": self.name})
		if item:
			frappe.delete_doc("Hub Item", item)

	def unregister(self):
		"""Unregister user"""
		pass

	def update_items(self, args):
		"""Update items"""
		all_items = frappe.db.sql_list("select item_code from `tabHub Item` where hub_user_name=%s", self.name)
		item_list = json.loads(args["item_list"])
		for item in all_items:
			if item not in item_list:
				frappe.delete_doc("Hub Item", item)

		item_fields = ["item_code", "item_name", "description", "image",
			"item_group", "price", "stock_qty", "stock_uom"]

		# item_fields = json.loads(args["item_fields"])

		# insert / update items
		for item in json.loads(args["items_to_update"]):
			item_code = frappe.db.get_value("Hub Item",
				{"hub_user_name": self.name, "item_code": item.get("item_code")})
			if item_code:
				hub_item = frappe.get_doc("Hub Item", item_code)
			else:
				hub_item = frappe.new_doc("Hub Item")
				hub_item.hub_user_name = self.name

			for key in item_fields:
				hub_item.set(key, item.get(key))

			for key in ("hub_user_name", "email", "country", "seller_city", "company", "seller_website"):
				hub_item.set(key, self.get(key))

			hub_item.published = 1
			hub_item.save(ignore_permissions=True)
		return frappe._dict({"last_sync_datetime":now()})

	def add_item_fields(self, args):
		items_with_new_fields = json.loads(args["items_with_new_fields"])
		new_fields = json.loads(args["new_fields"])
		for item in items_with_new_fields:
			item_code = frappe.db.get_value("Hub Item",
				{"hub_user_name": self.name, "item_code": item.get("item_code")})
			hub_item = frappe.get_doc("Hub Item", item_code)
			for key in new_fields:
				hub_item.set(key, item.get(key))
			hub_item.save(ignore_permissions=True)

	def remove_item_fields(self, args):
		fields_to_remove = json.loads(args["fields_to_remove"])
		# #######