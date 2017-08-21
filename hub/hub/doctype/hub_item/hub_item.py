# -*- coding: utf-8 -*-
# Copyright (c) 2017, Frappe and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe, json
from frappe.model.document import Document

class HubItem(Document):
	def update_item_details(self, item_dict):
		self.old = None
		if frappe.db.exists('Hub Item', self.item_code):
			self.old = frappe.get_doc('Hub Item', self.item_code)
		for field, new_value in item_dict.iteritems():
			old_value = self.old.get(field) if self.old else None
			if(new_value != old_value):
				self.set(field, new_value)
				frappe.db.set_value("Hub Item", self.name, field, new_value)
