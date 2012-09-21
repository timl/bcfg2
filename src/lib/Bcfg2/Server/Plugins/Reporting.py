import time
import platform
import traceback
from lxml import etree

from Bcfg2.Reporting.Transport import load_transport_from_config, \
    TransportError, TransportImportError

try:
    import cPickle as pickle
except:
    import pickle

from Bcfg2.Server.Plugin import Statistics, PullSource, PluginInitError

class Reporting(Statistics, PullSource):

    CLIENT_METADATA_FILEDS = ('profile', 'bundles', 'aliases', 'addresses',
        'groups', 'categories', 'uuid', 'version')

    def __init__(self, core, datastore):
        Statistics.__init__(self, core, datastore)
        PullSource.__init__(self)
        self.core = core
        self.experimental = True

        self.whoami = platform.node()
        self.transport = None

        try:
            self.transport = load_transport_from_config(core.setup)
        except TransportError:
            self.logger.error("%s: Failed to load transport: %s" %
                (self.name, traceback.format_exc().splitlines()[-1]))
            raise PluginInitError


    def process_statistics(self, client, xdata):
        stats = xdata.find("Statistics")
        stats.set('time', time.asctime(time.localtime()))

        cdata = { 'server': self.whoami }
        for field in self.CLIENT_METADATA_FILEDS:
            try:
                value = getattr(client, field)
            except KeyError:
                continue
            if value:
                if isinstance(value, set):
                    value = [v for v in value]
                cdata[field] = value

        try:
            interaction_data = pickle.dumps({ 'hostname': client.hostname,
                'metadata': cdata, 'stats':
                etree.tostring(stats, xml_declaration=False).decode('UTF-8') })
        except:
            self.logger.error("%s: Failed to build interaction object: %s" %
                (self.__class__.__name__,
                    traceback.format_exc().splitlines()[-1]))

        # try 3 times to store the data
        for i in [1, 2, 3]:
            try:
                self.transport.store(client.hostname, interaction_data)
                self.logger.debug("%s: Queued statistics data for %s" %
                    (self.__class__.__name__, client.hostname))
                return
            except TransportError:
                continue
            except:
                self.logger.error("%s: Attempt %s: Failed to add statistic %s" %
                    (self.__class__.__name__, i,
                        traceback.format_exc().splitlines()[-1]))
        self.logger.error("%s: Retry limit reached for %s" %
                    (self.__class__.__name__, client.hostname))

    def GetExtra(self, client):
        """Only called by Bcfg2.Admin modes"""
        self.logger.error("Reporting: GetExtra is not implemented yet")
        return []

    def GetCurrentEntry(self, client, e_type, e_name):
        self.logger.error("Reporting: GetCurrentEntry is not implemented yet")
        return []

    def shutdown(self):
        super(Reporting, self).shutdown()
        if self.transport:
            self.transport.shutdown()
