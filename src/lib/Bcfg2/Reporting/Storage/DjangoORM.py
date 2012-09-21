"""
The base for the original DjangoORM (DBStats)
"""

import os
import traceback
from lxml import etree
from Bcfg2.Reporting.Storage.base import StorageBase, StorageError
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned

#Used by GetCurrentEntry
import difflib
from Bcfg2.Compat import b64decode
from Bcfg2.Server.Reports.reports.models import Client

# This will change again
import Bcfg2.settings
os.environ['DJANGO_SETTINGS_MODULE'] = 'Bcfg2.settings'

class DjangoORM(StorageBase):
    def __init__(self, setup):
        super(DjangoORM, self).__init__(setup)
        self._load_stat = None
        self._ClientMetadata = None

    @classmethod
    def initialize(cls, setup):
        """Initialzize the Storage"""
        raise NotImplementedError

    def import_interaction(self, interaction):
        """Import the data into the backend"""

        # for now... stick with the old methods
        hostname = interaction['hostname']
        stats = etree.fromstring(interaction['stats'])
        metadata = interaction['metadata']
        server = metadata['server']

        for key in ('groups', 'bundles', 'aliases', 'addresses', 'categories'):
            if key not in metadata:
                metadata[key] = []
        for key in ('profile', 'uuid', 'password', 'version'):
            if key not in metadata:
                metadata[key] = ""

        cmetadata = self._ClientMetadata(hostname, metadata['profile'], 
                 metadata['groups'], metadata['bundles'], metadata['aliases'],
                 metadata['addresses'], metadata['categories'],
                 metadata['uuid'], metadata['password'], metadata['version'],
                 None)

        self._load_stat(cmetadata, stats, self.encoding, 0, self.logger, False,
            server)

    def validate(self):
        """Validate backend storage.  Should be called once when loaded"""

        Bcfg2.settings.read_config(repo=self.setup['repo'])

        # verify our database schema
        try:
            from Bcfg2.Server.SchemaUpdater import update_database, UpdaterError
            try:
                update_database()
            except UpdaterError:
                self.logger.error("Failed to update database schema: %s" % \
                    traceback.format_exc().splitlines()[-1])
                raise StorageError
        except StorageError:
            raise
        except Exception:
            self.logger.error("Failed to update database schema: %s" % \
                traceback.format_exc().splitlines()[-1])
            raise StorageError

        #Ensure our setup happens before these are imported
        from Bcfg2.Server.Reports.importscript import load_stat
        from Bcfg2.Server.Plugins.Metadata import ClientMetadata
        self._load_stat = load_stat
        self._ClientMetadata = ClientMetadata

    def GetExtra(self, client):
        """Fetch extra entries for a client"""
        try:
            c_inst = Client.objects.get(name=client)
            return [(a.entry.kind, a.entry.name) for a in
                    c_inst.current_interaction.extra()]
        except ObjectDoesNotExist:
            return []
        except MultipleObjectsReturned:
            self.logger.error("%s Inconsistency: Multiple entries for %s." %
                (self.__class__.__name__, client))
            return []

    def GetCurrentEntry(self, client, e_type, e_name):
        """"GetCurrentEntry: Used by PullSource"""
        try:
            c_inst = Client.objects.get(name=client)
        except ObjectDoesNotExist:
            self.logger.error("Unknown client: %s" % client)
            raise Bcfg2.Server.Plugin.PluginExecutionError
        except MultipleObjectsReturned:
            self.logger.error("%s Inconsistency: Multiple entries for %s." %
                (self.__class__.__name__, client))
            raise Bcfg2.Server.Plugin.PluginExecutionError
        result = c_inst.current_interaction.bad().filter(entry__kind=e_type,
                                                         entry__name=e_name)
        if not result:
            raise Bcfg2.Server.Plugin.PluginExecutionError
        entry = result[0]
        ret = []
        data = ('owner', 'group', 'perms')
        for t in data:
            if getattr(entry.reason, "current_%s" % t) == '':
                ret.append(getattr(entry.reason, t))
            else:
                ret.append(getattr(entry.reason, "current_%s" % t))
        if entry.reason.is_sensitive:
            raise Bcfg2.Server.Plugin.PluginExecutionError
        elif len(entry.reason.unpruned) != 0:
            ret.append('\n'.join(entry.reason.unpruned))
        elif entry.reason.current_diff != '':
            if entry.reason.is_binary:
                ret.append(b64decode(entry.reason.current_diff))
            else:
                ret.append('\n'.join(difflib.restore(\
                    entry.reason.current_diff.split('\n'), 1)))
        elif entry.reason.is_binary:
            # If len is zero the object was too large to store
            raise Bcfg2.Server.Plugin.PluginExecutionError
        else:
            ret.append(None)
        return ret

