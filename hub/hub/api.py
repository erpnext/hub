# Copyright (c) 2015, Web Notes Technologies Pvt. Ltd. and Contributors and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import json

from frappe import _
from frappe.utils import random_string
from six import string_types
from urlparse import urljoin

from .curation import Curation
from .utils import save_remote_file_locally

from .log import (
	add_log,
	add_saved_item,
	remove_saved_item,
	get_seller_items_synced_count,
	add_seller_publish_stats,
	add_hub_seller_activity,
)


current_hub_user = frappe.session.user


@frappe.whitelist(allow_guest=True)
def add_hub_seller(company_details):
	"""Register on the hub."""
	try:
		company_details = frappe._dict(json.loads(company_details))

		hub_seller = frappe.get_doc({
			'doctype': 'Hub Seller',
			'company': company_details.company,
			'country': company_details.country,
			'city': company_details.city,
			'currency': company_details.currency,
			'site_name': company_details.site_name,
			'company_description': company_details.company_description
		}).insert(ignore_permissions=True)

		# try and save company logo locally
		company_logo = company_details.company_logo
		if company_logo:
			if company_logo.startswith('/files/'):
				company_logo = urljoin(company_details.site_name, company_logo)

			if company_logo.startswith('http'):
				try:
					logo = save_remote_file_locally(company_logo, 'Hub Seller', hub_seller.name)
					hub_seller.logo = logo.file_url
					hub_seller.save()
				except Exception:
					frappe.log_error(title='Hub Company Logo Exception')


		return {
			'hub_seller_name': hub_seller.name
		}

	except Exception as e:
		print("Hub Server Exception")
		print(frappe.get_traceback())
		frappe.log_error(title="Hub Server Exception")
		frappe.throw(frappe.get_traceback())

@frappe.whitelist(allow_guest=True)
def add_hub_user(user_email, hub_seller, first_name, last_name=None):
	password = random_string(16)

	user = frappe.get_doc({
		'doctype': 'User',
		'email': user_email,
		'first_name': first_name,
		'last_name': last_name,
		'new_password': password
	})

	user.append_roles('System Manager', 'Hub User', 'Hub Buyer')
	user.flags.delay_emails = True
	user.insert(ignore_permissions=True)

	hub_user = frappe.get_doc({
		'doctype': 'Hub User',
		'hub_seller': hub_seller,
		'user_email': user_email,
		'first_name': first_name,
		'last_name': last_name,
		'user': user.name
	}).insert(ignore_permissions=True)

	return {
		'user_email': user_email,
		'hub_user_name': hub_user.name,
		'password': password
	}


# @frappe.whitelist()
# def unregister():
# 	frappe.db.set_value('Hub Seller', hub_seller, 'enabled', 0)
# 	return hub_seller


@frappe.whitelist()
def update_profile(hub_seller, updated_profile):
	'''
	Update Seller Profile
	'''

	updated_profile = json.loads(updated_profile)

	profile = frappe.get_doc("Hub Seller", hub_seller)
	if updated_profile.get('company_description') != profile.company_description:
		profile.company_description = updated_profile.get('company_description')

	profile.save()

	return profile.as_dict()

@frappe.whitelist(allow_guest=True)
def get_data_for_homepage(country=None):
	'''
	Get curated item list for the homepage.
	'''
	c = Curation(current_hub_user, country)
	return c.get_data_for_homepage()


@frappe.whitelist(allow_guest=True)
def get_items(keyword='', hub_seller=None, filters={}):
	'''
	Get items by matching it with the keywords field
	'''
	c = Curation(current_hub_user)

	if isinstance(filters, string_types):
		filters = json.loads(filters)

	if keyword:
		filters['keywords'] = ['like', '%' + keyword + '%']

	if hub_seller:
		filters["hub_seller"] = hub_seller

	return c.get_items(filters=filters)


@frappe.whitelist()
def pre_items_publish(intended_item_publish_count):
	log = add_log(
		log_type = 'Hub Seller Publish',
		hub_user = current_hub_user,
		data = {
			'status': 'Pending',
			'number_of_items_to_sync': intended_item_publish_count
		}
	)

	# add_hub_seller_activity(
	# 	current_hub_user,
	# 	'Hub Seller Publish',
	# 	{
	# 		'number_of_items_to_sync': intended_item_publish_count
	# 	},
	# 	'Pending'
	# )

	return log


@frappe.whitelist()
def post_items_publish():
	items_synced_count = get_seller_items_synced_count(current_hub_user)

	log = add_log(
		log_type = 'Hub Seller Publish',
		hub_user = current_hub_user,
		data = {
			'status': 'Completed',
			'items_synced_count': items_synced_count
		}
	)

	# add_hub_seller_activity(
	# 	current_hub_user,
	# 	'Hub Seller Publish',
	# 	{
	# 		'items_synced_count': items_synced_count
	# 	},
	# 	'Completed'
	# )

	add_seller_publish_stats(current_hub_user)

	return log


@frappe.whitelist(allow_guest=True)
def get_hub_seller_page_info(hub_seller='', company=''):
	if not hub_seller and company:
		hub_seller = frappe.db.get_all(
			"Hub Seller", filters={'company': company})[0].name
	else:
		frappe.throw('No Seller or Company Name received.')

	items_by_seller = Curation().get_items(filters={
		'hub_seller': hub_seller
	})

	return {
		'profile': get_hub_seller_profile(hub_seller),
		'items': items_by_seller
	}


@frappe.whitelist()
def get_hub_seller_profile(hub_seller=''):
	profile = frappe.get_doc("Hub Seller", hub_seller).as_dict()

	if profile.hub_seller_activity:
		for log in profile.hub_seller_activity:
			log.pretty_date = frappe.utils.pretty_date(log.get('creation'))

	return profile


@frappe.whitelist(allow_guest=True)
def get_item_details(hub_item_name):
	c = Curation()
	items = c.get_items(filters={'name': hub_item_name})
	return items[0] if len(items) == 1 else None


@frappe.whitelist(allow_guest=True)
def get_item_reviews(hub_item_name):
	reviews = frappe.db.get_all('Hub Item Review', fields=['*'],
	filters={
		'parenttype': 'Hub Item',
		'parentfield': 'reviews',
		'parent': hub_item_name
	}, order_by='modified desc')

	return reviews or []



@frappe.whitelist()
def add_item_review(hub_item_name, review):
	'''Adds a review record for Hub Item and limits to 1 per user'''
	new_review = json.loads(review)

	item_doc = frappe.get_doc('Hub Item', hub_item_name)
	existing_reviews = item_doc.get('reviews')

	# dont allow more than 1 review
	for review in existing_reviews:
		if review.get('user') == new_review.get('user'):
			return dict(error='Cannot add more than 1 review for the user {0}'.format(new_review.get('user')))

	item_doc.append('reviews', new_review)
	item_doc.save()

	return item_doc.get('reviews')[-1]


@frappe.whitelist(allow_guest=True)
def get_categories(parent='All Categories'):
	# get categories info with parent category and stuff
	categories = frappe.get_all('Hub Category',
		filters={'parent_hub_category': parent},
		fields=['name'],
		order_by='name asc')

	return categories

# Hub Item View

@frappe.whitelist(allow_guest=True)
def add_item_view(hub_item_name):
	current_hub_user = frappe.session.user
	if current_hub_user == 'Guest':
		current_hub_user = None

	log = add_log('Hub Item View', hub_item_name, current_hub_user)
	return log

# Report Item

@frappe.whitelist()
def add_reported_item(hub_item_name, message=None):
	hub_seller = frappe.session.user

	if message:
		data = {
			'message': message
		}

	log = add_log('Hub Reported Item', hub_item_name, hub_seller, data)
	return log

# Saved Items

@frappe.whitelist()
def add_item_to_user_saved_items(hub_item_name):
	hub_user = frappe.session.user
	log = add_log('Hub Item Save', hub_item_name, hub_user, 1)
	add_saved_item(hub_item_name, hub_user)
	return log


@frappe.whitelist()
def remove_item_from_user_saved_items(hub_item_name):
	hub_user = frappe.session.user
	log = add_log('Hub Item Save', hub_item_name, hub_user, 0)
	remove_saved_item(hub_item_name, hub_user)
	return log


@frappe.whitelist()
def get_saved_items_of_user():
	saved_items = frappe.get_all('Hub Saved Item', fields=['hub_item'], filters = {
		'hub_user': current_hub_user
	})

	saved_item_names = [d.hub_item for d in saved_items]

	return get_items(filters={'name': ['in', saved_item_names]})


@frappe.whitelist()
def get_sellers_with_interactions(for_seller):
	'''Return all sellers `for_seller` has sent a message to or received a message from'''

	res = frappe.db.sql('''
		SELECT sender, receiver
		FROM `tabHub Seller Message`
		WHERE sender = %s OR receiver = %s
	''', [for_seller, for_seller])

	sellers = []
	for row in res:
		sellers += row

	sellers = [seller for seller in sellers if seller != for_seller]

	sellers_with_details = frappe.db.get_all('Hub Seller',
											 fields=['name as email', 'company'],
											 filters={'name': ['in', sellers]})

	return sellers_with_details


@frappe.whitelist()
def get_messages(against_seller, against_item, order_by='creation asc', limit=None):
	'''Return all messages sent between `for_seller` and `against_seller`'''

	for_seller = frappe.session.user

	messages = frappe.get_all('Hub Seller Message',
		fields=['name', 'sender', 'receiver', 'content', 'creation'],
		filters={
			'sender': ['in', (for_seller, against_seller)],
			'receiver': ['in', (for_seller, against_seller)],
			'reference_hub_item': against_item,
		}, limit=limit, order_by=order_by)

	return messages

@frappe.whitelist()
def get_buying_items_for_messages(hub_seller=None):
	if not hub_seller:
		hub_seller = frappe.session.user

	validate_session_user(hub_seller)

	items = frappe.db.get_all('Hub Seller Message',
		fields='reference_hub_item',
		filters={
			'sender': hub_seller,
			'reference_hub_seller': ('!=', hub_seller)
		},
		group_by='reference_hub_item'
	)

	item_names = [item.reference_hub_item for item in items]

	items = get_items(filters={
		'name': ['in', item_names]
	})

	for item in items:
		item['recent_message'] = get_recent_message(item)

	return items

@frappe.whitelist()
def get_selling_items_for_messages(hub_seller=None):
	# TODO: Refactor (get_all calls seems redundant)
	if not hub_seller:
		hub_seller = frappe.session.user

	validate_session_user(hub_seller)

	items = frappe.db.get_all('Hub Seller Message',
		fields='reference_hub_item',
		filters={
			'receiver': hub_seller,
		},
		group_by='reference_hub_item'
	)

	item_names = [item.reference_hub_item for item in items]

	items = get_items(filters={
		'name': ['in', item_names]
	})

	for item in items:
		item.received_messages = frappe.get_all('Hub Seller Message',
			fields=['sender', 'receiver', 'content', 'creation'],
			filters={
				'receiver': hub_seller,
				'reference_hub_item': item.name
			}, distinct=True, order_by='creation DESC')

		for message in item.received_messages:
			buyer_email = message.sender if message.sender != hub_seller else message.receiver
			message.buyer_email = buyer_email
			message.buyer = frappe.db.get_value('Hub Seller', buyer_email, 'company')

	return items


@frappe.whitelist()
def send_message(from_seller, to_seller, message, hub_item):
	validate_session_user(from_seller)

	msg = frappe.get_doc({
		'doctype': 'Hub Seller Message',
		'sender': from_seller,
		'receiver': to_seller,
		'content': message,
		'reference_hub_item': hub_item
	}).insert(ignore_permissions=True)

	return msg

def validate_session_user(user):
	if frappe.session.user == 'Administrator':
		return True
	if frappe.session.user != user:
		frappe.throw(_('Not Permitted'), frappe.PermissionError)

def get_recent_message(item):
	message = get_messages(item.hub_seller, item.hub_item_name, limit=1, order_by='creation desc')
	message_object = message[0] if message else {}
	return message_object
