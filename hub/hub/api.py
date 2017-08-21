# Copyright (c) 2015, Web Notes Technologies Pvt. Ltd. and Contributors and contributors
# For license information, please see license.txt

import frappe, json, requests, os
from frappe.utils import now
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

user_config_fields = ["enabled", "public_key_pem"]
user_profile_fields = ["hub_user_name", "email", "country", "company"]
seller_fields = ["seller_website", "seller_city", "seller_description"]
publishing_fields = ["publish", "publish_pricing", "publish_availability"]

private_files = frappe.get_site_path('private', 'files')
public_key_path = os.path.join(private_files, "hub_rsa.pub")
private_key_path = os.path.join(private_files, "hub_rsa")

if os.path.exists(public_key_path):
	with open(public_key_path, "rb") as public_key_file:
		hub_public_key_pem = public_key_file.read()

### Commands
@frappe.whitelist(allow_guest=True)
def register(args_data):
	"""Register on the hub."""
	args = json.loads(args_data)
	if frappe.get_all("Hub User", filters = {"email": args["email"]}):
		return

	hub_user = frappe.new_doc("Hub User")
	for key in user_profile_fields + user_config_fields:
		hub_user.set(key, args[key])

	hub_user.insert(ignore_permissions=True)
	response = hub_user.as_dict()
	response["hub_public_key_pem"] = hub_public_key_pem
	return response

@frappe.whitelist(allow_guest=True)
def call_method(access_token, method, message):
	args = json.loads(message)
	if args:
		return globals()[method](access_token, args)
	else:
		return globals()[method](access_token)

def unregister(access_token):
	hub_user = get_user(access_token)
	unpublish_items(access_token)

	# TODO: Delete all of user's transactions

	# Delete user
	frappe.delete_doc('Hub User', hub_user.name, ignore_permissions=True)

def update_user_details(access_token, args):
	hub_user = get_user(access_token)
	return hub_user.update_user_details(args)

def update_items(access_token, args):
	hub_user = get_user(access_token)
	return hub_user.update_items(args)

def add_item_fields(access_token, args):
	hub_user = get_user(access_token)
	return hub_user.add_item_fields(args)

def remove_item_fields(access_token, args):
	hub_user = get_user(access_token)
	return hub_user.remove_item_fields(args)

def unpublish_items(access_token):
	hub_user = get_user(access_token)
	return hub_user.unpublish_items()


def update_item(access_token, args):
	hub_user = get_user(access_token)
	item_code = args["item_code"]
	item_dict = json.loads(args["item_dict"])
	item = frappe.get_doc("Hub Item", {"hub_user_name": hub_user.name, "item_code":item_code})
	return item.update_item_details(item_dict)

def insert_item(access_token, args):
	hub_user = get_user(access_token)
	item = frappe.new_doc("Hub Item")
	item_dict = json.loads(args["item_dict"])
	item.update_item_details(item_dict)
	for key in user_profile_fields + ["seller_website", "seller_city"]:
		item.set(key, hub_user.get(key))
	item.published = 1
	item.save(ignore_permissions=True)

def delete_item(access_token, args):
	hub_user = get_user(access_token)
	item_code = args["item_code"]
	item = frappe.get_doc("Hub Item", {"hub_user_name": hub_user.name, "item_code":item_code})
	frappe.delete_doc('Hub Item', item.name, ignore_permissions=True)


### Queries
def get_items(access_token, args):
	"""Returns list of items by filters"""
	# args["text"]=None, args["category"]=None, args["company"]=None, args["country"]=None, args["start"]=0, args["limit"]=50
	get_user(access_token)
	or_filters = [
		{"item_name": ["like", "%{0}%".format(args["text"])]},
		{"description": ["like", "%{0}%".format(args["text"])]}
	]
	filters = {
		"published": "1"
	}
	if args["category"]:
		filters["item_group"] = args["category"]
	if args["company"]:
		filters["company"] = args["company"]
	if args["country"]:
		filters["country"] = args["country"]
	return frappe.get_all("Hub Item", fields=["item_code", "item_name", "item_group", "description", "image",
		"hub_user_name", "email", "country", "seller_city", "company", "seller_website", "standard_rate"],
			filters=filters, or_filters=or_filters, limit_start = args["start"], limit_page_length = args["limit"])

def get_user(access_token):
	return frappe.get_doc("Hub User", {"access_token": access_token})

def get_all_users(access_token):
	return frappe.get_all("Hub User", fields=["hub_user_name", "country"])

def get_categories(access_token):
	return frappe.get_all("Hub Category", fields=["category_name"])

def get_user_details(access_token, user_name):
	return frappe.get_doc("Hub User", {"hub_user_name": user_name})



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