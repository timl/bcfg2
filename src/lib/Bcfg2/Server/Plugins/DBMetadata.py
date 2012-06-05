"""
This file stores persistent metadata for the Bcfg2 Configuration Repository.
"""

import copy
import fcntl
import lxml.etree
import os
import os.path
import socket
import sys
import time

from django.db import models

import Bcfg2.Server.FileMonitor
import Bcfg2.Server.Plugin

from Bcfg2.Server.Plugins.Metadata import *

class MetadataClient(models.Model,
                     Bcfg2.Server.Plugin.PluginDatabaseModel):
    hostname = models.CharField(max_length=255)


class DBMetadata(Metadata, Bcfg2.Server.Plugin.DatabaseBacked):
    __files__ = ["groups.xml"]

    def __init__(self, core, datastore, watch_clients=True):
        Metadata.__init__(self, core, datastore, watch_clients=watch_clients)
        Bcfg2.Server.Plugin.DatabaseBacked.__init__(self)
        if os.path.exists(os.path.join(self.data, "clients.xml")):
            self.logger.warning("clients.xml found, parsing in compatibility mode")
            self._handle_file("clients.xml")

    def add_group(self, group_name, attribs):
        msg = "DBMetadata does not support adding groups"
        self.logger.error(msg)
        raise Bcfg2.Server.Plugin.PluginExecutionError(msg)

    def add_bundle(self, bundle_name):
        msg = "DBMetadata does not support adding bundles"
        self.logger.error(msg)
        raise Bcfg2.Server.Plugin.PluginExecutionError(msg)

    def add_client(self, client_name):
        """Add client to clients database."""
        client = MetadataClient(hostname=client_name)
        client.save()
        return client

    def update_group(self, group_name, attribs):
        msg = "DBMetadata does not support updating groups"
        self.logger.error(msg)
        raise Bcfg2.Server.Plugin.PluginExecutionError(msg)

    def update_bundle(self, bundle_name):
        msg = "DBMetadata does not support updating bundles"
        self.logger.error(msg)
        raise Bcfg2.Server.Plugin.PluginExecutionError(msg)

    def update_client(self, client_name, attribs):
        msg = "DBMetadata does not support updating clients"
        self.logger.error(msg)
        raise Bcfg2.Server.Plugin.PluginExecutionError(msg)

    def list_clients(self):
        """ List all clients in client database """
        return MetadataClient.objects.all()

    def remove_group(self, group_name, attribs):
        msg = "DBMetadata does not support removing groups"
        self.logger.error(msg)
        raise Bcfg2.Server.Plugin.PluginExecutionError(msg)

    def remove_bundle(self, bundle_name):
        msg = "DBMetadata does not support removing bundles"
        self.logger.error(msg)
        raise Bcfg2.Server.Plugin.PluginExecutionError(msg)

    def remove_client(self, client_name):
        """Remove a client"""
        try:
            client = MetadataClient.objects.get(name=client_name)
        except DoesNotExist:
            logger.warning("Client %s does not exist" % client_name)
            return
        client.delete()

    def set_profile(self, client, profile, addresspair):
        msg = "DBMetadata does not support asserting client profiles"
        self.logger.error(msg)
        raise Bcfg2.Server.Plugin.PluginExecutionError(msg)

