# -*- coding: utf-8 -*-

"""
Copyright (C) 2016 Dariusz Suchojad <dsuch at zato.io>
Licensed under LGPLv3, see LICENSE.txt for terms and conditions.

Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
https://zato.io
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
import sys
from logging import getLogger
from http.client import OK

# Bunch
from bunch import bunchify

# ConfigObj
from configobj import ConfigObj

# Requests
import requests

# ################################################################################################################################

logger = getLogger(__name__)

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

    def _get(self, path):
        return requests.get(self.address + path, params=self.qs, verify=self.verify_tls)

# ################################################################################################################################

    def connect(self):
        """ Connects to Discourse and obtains a session cookie.
        """
        self.cookie = self._get('/').cookies["_forum_session"]

# ################################################################################################################################

    def ping(self):
        """ Pings Discourse by fetching a list of its categories. Even if empty, the call as such should succeed
        allowing us to assume that the endpoint responds OK and we are actually connected to Discourse.
        """
        path = '/categories.json'
        response = self._get(path)

        if response.status_code != OK:
            logger.warn('Call to %s:%s did not return OK, quitting, headers and data below', self.address, path)
            logger.warn(response.headers)
            logger.warn(response.text)
            sys.exit(1)

# ################################################################################################################################

class Importer(object):
    """ Imports mbox files to Discourse, creating users on fly if needed.
    """
    def __init__(self, address, username, api_key, verify_tls):
        self.address = address
        self.username = username
        self.api_key = api_key
        self.verify_tls = verify_tls

        self.messages = []
        self.client = (Client(self.address, self.username, self.api_key, self.verify_tls))

# ################################################################################################################################

    def run(self):
        self.client.connect()
        self.client.ping()

# ################################################################################################################################

def handle(config_path):
    logger.info('Using config from `%s`', config_path)

    config = bunchify(ConfigObj(config_path)['discourse_importer'])

    for name in 'address', 'username', 'api_key':
        if not config.get(name):
            logger.warn('`%s` key missing or empty in [discourse_importer], quitting', name)
            sys.exit(1)

    imp = Importer(config.address, config.username, config.api_key, config.verify_tls)
    imp.run()

# ################################################################################################################################
