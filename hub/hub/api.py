# Copyright (c) 2015, Web Notes Technologies Pvt. Ltd. and Contributors and contributors
# For license information, please see license.txt

import frappe, json, requests, os
from frappe.utils import now
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

user_profile_fields = ["enabled", "hub_user_name", "email", "country", "public_key_pem"]
seller_fields = ["publish", "seller_website", "seller_city", "seller_description"]

private_files = frappe.get_site_path('private', 'files')
public_key_path = os.path.join(private_files, "hub_rsa.pub")
private_key_path = os.path.join(private_files, "hub_rsa")

if os.path.exists(public_key_path):
	with open(public_key_path, "rb") as public_key_file:
		hub_public_key_pem = public_key_file.read()

@frappe.whitelist(allow_guest=True)
def register(args_data):
	"""Register on the hub."""
	args = json.loads(args_data)
	if frappe.get_all("Hub User", filters = {"email": args["email"]}):
		return

	hub_user = frappe.new_doc("Hub User")
	for key in user_profile_fields:
		hub_user.set(key, args[key])

	hub_user.insert(ignore_permissions=True)
	response = hub_user.as_dict()
	response["hub_public_key_pem"] = hub_public_key_pem
	return response

@frappe.whitelist(allow_guest=True)
def unregister(access_token):
	# Delete all of user's transactions and items
	print "////////unregister////////"
	hub_user = get_user(access_token)

	# last step
	frappe.delete_doc('Hub User', hub_user.name, ignore_permissions=True)

@frappe.whitelist(allow_guest=True)
def unpublish(access_token):
	"""Un publish seller"""
	seller = get_seller(access_token)
	seller.published=0
	seller.save(ignore_permissions=True)

@frappe.whitelist(allow_guest=True)
def call_method(access_token, method, message):
	hub_user = get_user(access_token)
	args = json.loads(message)
	return getattr(hub_user, method)(args)

@frappe.whitelist(allow_guest=True)
def decrypt_message_and_call_method(access_token, method, signature, encrypted_key, message):
	print type(encrypted_key)
	print len(encrypted_key)
	en_key = str(encrypted_key.encode('latin-1'))

	print en_key
	print len(en_key)

	hub_user = get_user(access_token)
	user_public_key = load_pem_public_key(
		str(hub_user.public_key_pem),
		backend=default_backend()
	)

	# Verify key
	user_public_key.verify(
		signature,
		str(encrypted_key),
		padding.PSS(
			mgf=padding.MGF1(hashes.SHA256()),
			salt_length=padding.PSS.MAX_LENGTH
		),
		hashes.SHA256()
	)

	# Decrypt key
	if os.path.exists(private_key_path):
		with open(private_key_path, "rb") as private_key_file:
			private_key = serialization.load_pem_private_key(
				private_key_file.read(),
				password=None,
				backend=default_backend()
			)

	key = private_key.decrypt(
		en_key,
		padding.OAEP(
			mgf=padding.MGF1(algorithm=hashes.SHA1()),
			algorithm=hashes.SHA1(),
			label=None
		)
	)

	# Decrypt message
	f = Fernet(key)
	plaintext = f.decrypt(str(message))
	args = json.loads(plaintext.decode("utf-8"))
	getattr(hub_user, method)(args)

@frappe.whitelist(allow_guest=True)
def get_items(access_token, text=None, category=None, seller=None, country=None, start=0, limit=50):
	"""Returns list of items by filters"""
	get_user(access_token)
	or_filters = [
		{"item_name": ["like", "%{0}%".format(text)]},
		{"description": ["like", "%{0}%".format(text)]}
	]
	filters = {
		"published": "1"
	}
	if category:
		filters["item_group"] = category
	if seller:
		filters["hub_user_name"] = seller
	if country:
		filters["country"] = country
	return frappe.get_all("Hub Item", fields=["item_code", "item_name", "item_group", "description", "image",
		"hub_user_name", "email", "country", "seller_city", "company", "seller_website"],
			filters=filters, or_filters=or_filters, limit_start = start, limit_page_length = limit)

@frappe.whitelist(allow_guest=True)
def get_user(access_token):
	return frappe.get_doc("Hub User", {"access_token": access_token})

@frappe.whitelist(allow_guest=True)
def get_all_users():
	return frappe.get_all("Hub User", fields=["hub_user_name", "country"])

@frappe.whitelist(allow_guest=True)
def get_categories():
	return frappe.get_all("Hub Category", fields=["category_name"])

@frappe.whitelist(allow_guest=True)
def get_user_details(access_token, user_name):
	return frappe.get_doc("Hub User", {"hub_user_name": user_name})







# TESTER
@frappe.whitelist(allow_guest=True)
def test():
	user = "http://erpnext.reinstall:8000"
	response = requests.get(user + "/api/method/erpnext.hub_node.api.test")
	response.raise_for_status()
	return response.json().get("message")

@frappe.whitelist(allow_guest=True)
def load_message(access_token, msg_type, sender, receiver, receiver_website, msg_data):
	msg = frappe.new_doc("Hub Message")
	msg.message_type = msg_type
	if msg_type == "Request for Quotation":
		msg.naming_series = "DAT-RFQ-"
	else:
		msg.naming_series = "DAT-OPP-"

	msg.sender = sender
	msg.receiver = receiver
	msg.receiver_website = receiver_website

	msg.message_body = msg_data

	msg.save(ignore_permissions=True)
	frappe.db.commit()

	send_messages()

def send_messages():
	for msg in frappe.get_all("Hub Message", fields=["message_type", "receiver_website", "message_body"]):
		send_message(msg)

def send_message(message):
	msg_type = message["message_type"]
	receiver_website = message["receiver_website"]
	msg_data = message["message_body"]
	response = requests.get(receiver_website + "/api/method/erpnext.hub_node.api.make", data={
				"msg_type": msg_type,
				"data": msg_data
			})
	response.raise_for_status()
	return response.json().get("message")

def store_keys():
	pass
