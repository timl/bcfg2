"""
The base for the original DjangoORM (DBStats)
"""

import os
import traceback
from lxml import etree
from Bcfg2.Reporting.Storage.base import StorageBase, StorageError

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


    def shutdown(self):
        """Called at program exit"""
        pass

