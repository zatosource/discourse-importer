# -*- coding: utf-8 -*-

"""
Copyright (C) 2016 Dariusz Suchojad <dsuch at zato.io>
Licensed under LGPLv3, see LICENSE.txt for terms and conditions.

Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
https://zato.io
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
import operator
import os
import sys
from base64 import decodestring as b64decode
from email.header import decode_header
from email.utils import parseaddr, parsedate
from json import loads
from logging import getLogger
from http.client import OK
from mailbox import mbox
from random import choice
from urllib.parse import urlencode
from uuid import uuid4

# Bunch
from bunch import bunchify

# ConfigObj
from configobj import ConfigObj

# Requests
import requests

# ################################################################################################################################

logger = getLogger(__name__)

# ################################################################################################################################

rand_suffix = range(1, 100)

# ################################################################################################################################

class Client(object):
    """ A light-weight Discourse API client.
    """
    def __init__(self, address, username, api_key, verify_tls):
        self.address = address
        self.username = username
        self.api_key = api_key
        self.verify_tls = verify_tls

        self.cookie = '<no-cookie>'
        self.qs = {'api_username':self.username, 'api_key':self.api_key}

# ################################################################################################################################

    def _http(self, method, path, *args, **kwargs):
        func = getattr(requests, method)

        response = func(self.address + path, data=kwargs.get('data', ''), params=self.qs, verify=self.verify_tls)
        if kwargs.get('needs_raw_response'):
            return response

        if 'application/json' in response.headers.get('Content-Type', ''):
            return loads(response.text)

        return response

# ################################################################################################################################

    def _get(self, *args, **kwargs):
        return self._http('get', *args, **kwargs)

# ################################################################################################################################

    def _put(self, *args, **kwargs):
        return self._http('put', *args, **kwargs)

# ################################################################################################################################

    def _post(self, *args, **kwargs):
        return self._http('post', *args, **kwargs)

# ################################################################################################################################

    def connect(self):
        """ Connects to Discourse and obtains a session cookie.
        """
        self.cookie = self._get('/').cookies['_forum_session']

# ################################################################################################################################

    def ping(self):
        """ Pings Discourse by fetching a list of its categories. Even if empty, the call as such should succeed
        allowing us to assume that the endpoint responds OK and we are actually connected to Discourse.
        """
        path = '/categories.json'
        response = self._get(path, needs_raw_response=True)

        if response.status_code != OK:
            logger.warn('Call to %s:%s did not return OK, quitting, headers and data below', self.address, path)
            logger.warn(response.headers)
            logger.warn(response.text)
            sys.exit(1)

# ################################################################################################################################

    def get_users(self):
        return self._get('/admin/users/list/active.json')

# ################################################################################################################################

    def get_user_email(self, user_id, user_name):

        request = urlencode({
            'context': '/admin/users/{}/{}'.format(user_id, user_name)
            })

        return self._put('/users/{}/emails.json'.format(user_name), request)['email']

# ################################################################################################################################

    def create_user(self, name, user_name, email, password):
        request = urlencode({
            'name': name,
            'username': user_name,
            'email': email,
            'password': password,
            })

        self._post('/users', data=request)

# ################################################################################################################################

    def create_topic(self, category_id, title, raw, topic_id=None):
        request = {
            'archetype': 'regular',
            'category': category_id,
            'composer_open_duration_msecs': 22602,
            'is_warning': False,
            'nested_post': True,
            'raw': raw,
            'title': title,
            'typing_duration_msecs': 6600,
        }

        if topic_id:
            request['topic_id'] = topic_id

        return self._post('/posts', data=urlencode(request)).get('post', {}).get('topic_id')

# ################################################################################################################################

class Message(object):
    """ An individual message read from an mbox file.
    """
    def __init__(self):
        self.id = ''
        self.from_ = ''
        self.subject = ''
        self.body = ''
        self.children = []
        self.is_top_level = False
        self.date = ''

    def __lt__(self, other):
        return self.date < other.date

    def _b64decode(self, msg, body):
        if msg.get('Content-Transfer-Encoding') == 'base64':
            return b64decode(bytes(body, 'utf8')).decode('utf8', 'ignore')
        else:
            return body

    def get_body(self, msg, list_footer_start):
        body = msg.get_payload()
        body = self._b64decode(msg, body)

        # Handle multipart messages
        while isinstance(body, list):
            sub_msg = body[0]
            body = self._b64decode(sub_msg, sub_msg.get_payload())

        body = body.split(list_footer_start)[0]
        body = body.split('cheers,')[0]
        body = body.split('-- ')[0]
        return body.strip()

    @staticmethod
    def from_mbox_object(raw, from_, list_footer_start, skip_subject):

        subject = raw['Subject']
        if skip_subject and skip_subject in subject:
            return

        try:
            subject = subject.replace('[Zato-discuss] ', '')
        except AttributeError:
            return

        subject = ' '.join(subject.split())

        msg = Message()
        msg.id = raw['Message-ID']
        msg.date = parsedate(raw['Date'])
        msg.subject = '(Migrated) {}'.format(subject)
        msg.from_ = from_
        msg.is_top_level = 'In-Reply-To' not in raw

        msg.body = msg.get_body(raw, list_footer_start)

        if not msg.body:
            return

        if msg.is_top_level:
            msg.body = '\n<b>(This message has been automatically imported from the retired mailing list)</b>'\
                          '\n\n{}'.format(msg.body)

        return msg

# ################################################################################################################################

class User(object):
    def __init__(self, user_name, email, password):
        self.user_name = user_name
        self.email = email
        self.password = password

# ################################################################################################################################

class Importer(object):
    """ Imports mbox files to Discourse, creating users on fly if needed.
    """
    def __init__(self, mbox_path, address, username, api_key, verify_tls, list_footer_start, emails_ignore, emails_require,
            emails_add, category_id, skip_subject):
        self.mbox_path = os.path.abspath(os.path.expanduser(mbox_path))
        self.mbox = mbox(self.mbox_path)
        self.address = address
        self.username = username
        self.api_key = api_key
        self.verify_tls = verify_tls
        self.list_footer_start = list_footer_start
        self.emails_ignore = emails_ignore
        self.emails_require = emails_require
        self.emails_add = emails_add
        self.category_id = category_id
        self.skip_subject = skip_subject
        self.missing_users = set()
        self.discourse_users = set()

        self.mbox_messages = {}
        self.mbox_users = {}

        self.client = (Client(self.address, self.username, self.api_key, self.verify_tls))

# ################################################################################################################################

    def _get_name_from(self, msg):
        """ Returns email of a message's author.
        """
        name, from_ = parseaddr(msg['From'])
        return decode_header(name)[0][0], from_.lower()

# ################################################################################################################################

    def read_mbox(self):
        """ Reads all import from the mailbox, populating internal user and mail structures along the way.
        """
        if not self.mbox:
            logger.warn('Mbox file `%s` does not exist or is empty', self.mbox_path)
            sys.exit(1)

        #
        # First pass - collect users
        #

        for msg in self.mbox:
            name, from_ = self._get_name_from(msg)

            # We do not always want to import everyone
            if (from_ in self.emails_ignore) or (not self.emails_require in from_):
                continue

            self.mbox_users[from_] = name

        #
        # Second pass - collect top-level messages
        #

        for msg in self.mbox:
            _, from_ = self._get_name_from(msg)
            if from_ not in self.mbox_users:
                continue

            msg = Message.from_mbox_object(msg, from_, self.list_footer_start, self.skip_subject)
            if msg:
                self.mbox_messages[msg.id] = msg

        # Third pass - collect children messages
        for msg in self.mbox:
            refs = msg['References']
            if refs:
                refs = refs.split('\n')
                refs = [elem.strip() for elem in refs]
                from_ = self._get_name_from(msg)

                for ref in refs:
                    if ref in self.mbox_messages:
                        top_level_id = ref
                        children = self.mbox_messages[top_level_id].children
                        child_msg = Message.from_mbox_object(msg, from_, self.list_footer_start, self.skip_subject)
                        if child_msg:
                            children.append(child_msg)

# ################################################################################################################################

    def set_missing_users(self):
        """ Returns a list of users that are not in Discourse yet.
        """
        existing = set()
        missing = []

        # All users currnetly existing in Discourse
        for item in self.client.get_users():
            email = self.client.get_user_email(item['id'], item['username'])
            existing.add(email)
            self.discourse_users.add(item['username'])

        for item in self.mbox_users:
            if item not in existing:
                self.missing_users.add(item)

        if self.missing_users:
            logger.info('Found %d users to add, listed below:', len(self.missing_users))
            logger.info('%s', sorted(self.missing_users))
            return True

# ################################################################################################################################

    def _get_username(self, email):
        return email.split('@')[0]

# ################################################################################################################################

    def add_missing_users(self):

        new = []
        duplicates = []
        used = set()

        for item in self.missing_users:
            new.append(self._get_username(item))

        for item in set(new):
            if new.count(item) > 1:
                duplicates.append(item)

        for item in sorted(self.missing_users):
            user_name = self._get_username(item)

            if user_name in duplicates:
                suffix = choice(rand_suffix)

                while '{}{}'.format(user_name, suffix)in used:
                    suffix = choice(rand_suffix)

                user_name = '{}{}'.format(user_name, suffix )
                used.add(user_name)

            if len(user_name) < 3:
                user_name = user_name + '123'

            name = self.mbox_users[item]
            password = uuid4().hex

            self.client.create_user(name, user_name, item, password)

# ################################################################################################################################

    def create_topics(self):

        for msg_id in sorted(self.mbox_messages, key=self.mbox_messages.get):

            msg = self.mbox_messages[msg_id]

            if msg.is_top_level:
                logger.info('Creating %s', msg.subject)

                topic_id = self.client.create_topic(self.category_id, msg.subject, msg.body)

                for child in sorted(msg.children, key=lambda x: x.date):
                    self.client.create_topic(self.category_id, child.subject, child.body, topic_id)

# ################################################################################################################################

    def run(self):

        self.client.connect()
        self.client.ping()
        self.read_mbox()

        if self.set_missing_users():
            self.add_missing_users()

        self.create_topics()

# ################################################################################################################################

def handle(config_path):
    logger.info('Using config from `%s`', config_path)

    config = bunchify(ConfigObj(config_path)['discourse_importer'])

    for name in 'mbox_path', 'address', 'username', 'api_key':
        if not config.get(name):
            logger.warn('`%s` key missing or empty in [discourse_importer], quitting', name)
            sys.exit(1)

    imp = Importer(config.mbox_path, config.address, config.username, config.api_key, config.verify_tls,
        config.list_footer_start, config.emails_ignore, config.emails_require, config.emails_add,
        config.category_id, config.skip_subject)
    imp.run()

# ################################################################################################################################
