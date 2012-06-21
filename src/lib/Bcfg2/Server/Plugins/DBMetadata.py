import os
import sys

from django.db import models

import Bcfg2.Server.Lint
import Bcfg2.Server.Plugin
from Bcfg2.Server.Plugins.Metadata import *

class MetadataClientModel(models.Model,
                          Bcfg2.Server.Plugin.PluginDatabaseModel):
    hostname = models.CharField(max_length=255)


class DBMetadata(Metadata, Bcfg2.Server.Plugin.DatabaseBacked):
    __files__ = ["groups.xml"]

    def __init__(self, core, datastore, watch_clients=True):
        Metadata.__init__(self, core, datastore, watch_clients=watch_clients)
        Bcfg2.Server.Plugin.DatabaseBacked.__init__(self)
        if os.path.exists(os.path.join(self.data, "clients.xml")):
            self.logger.warning("DBMetadata: clients.xml found, parsing in "
                                "compatibility mode")
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
        client = MetadataClientModel(hostname=client_name)
        client.save()
        self.clients = self.list_clients()
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
        return [c.hostname for c in MetadataClientModel.objects.all()]

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
            client = MetadataClientModel.objects.get(name=client_name)
        except DoesNotExist:
            logger.warning("Client %s does not exist" % client_name)
            return
        client.delete()
        self.clients = self.list_clients()

    def _set_profile(self, client, profile, addresspair):
        print "_set_profile(%s, %s, %s)" % (client, profile, addresspair)
        if client not in self.clients:
            # adding a new client
            self.add_client(client)
            if client not in self.clientgroups:
                self.clientgroups[client] = [profile]
            # TODO: make this persistent
        else:
            msg = "DBMetadata does not support asserting client profiles"
            self.logger.error(msg)
            raise Bcfg2.Server.Plugin.PluginExecutionError(msg)

    def _handle_clients_xml_event(self, event):
        # clients.xml is parsed and the options specified in it are
        # understood, but it does _not_ assert client existence.
        Metadata._handle_clients_xml_event(self, event)
        self.clients = self.list_clients()


class DBMetadataLint(Bcfg2.Server.Lint.ServerPlugin):
    def Run(self):
        md = self.core.plugins['DBMetadata']
        if md.default:
            self.LintError("dbmetadata-default-group",
                           "Use of default group with DBMetadata hides group "
                           "membership of new clients")

    @classmethod
    def Errors(cls):
        return {"dbmetadata-default-group":"warning"}
