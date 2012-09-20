import os
import time
import platform
import traceback
from lxml import etree

try:
    import cPickle as pickle
except:
    import pickle

from Bcfg2.Server.Plugin import Statistics, PullSource, \
    PluginExecutionError, PluginInitError

class StatsLocal(Statistics, PullSource):
    name = 'StatsLocal'

    CLIENT_METADATA_FILEDS = ('profile', 'bundles', 'aliases', 'addresses',
        'groups', 'categories', 'uuid', 'version')

    def __init__(self, core, datastore):
        Statistics.__init__(self, core, datastore)
        PullSource.__init__(self)
        self.core = core
        self.experimental = True

        self.whoami = platform.node()

        self.work_path = "%s/work" % self.data
        #self.cmd_queue = "%s/cmd_queue" % self.data

        if not os.path.exists(self.work_path):
            try:
                os.makedirs(self.work_path)
            except:
                self.logger.error("%s: Unable to create storage: %s" % 
                    (self.__class__.__name__,
                        traceback.format_exc().splitlines()[-1]))
                raise PluginInitError

    def store_stat(self, hostname, interaction):
        save_file = "%s/%s-%s" % (self.work_path, hostname, time.time())
        if os.path.exists(save_file):
            self.logger.error("%s: Oops.. duplicate statistic in directory." %
                self.__class__.__name__)
            raise PluginExecutionError

        # Intentionally letting exceptions go
        saved = open(save_file, 'w')
        try:
            saved.write(interaction)
        finally:
            saved.close()
        

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
                self.store_stat(client.hostname, interaction_data)
                self.logger.debug("%s: Queued statistics data for %s" %
                    (self.__class__.__name__, client.hostname))
                return
            except PluginExecutionError:
                continue
            except:
                self.logger.error("%s: Attempt %s: Failed to add statistic %s" %
                    (self.__class__.__name__, i,
                        traceback.format_exc().splitlines()[-1]))
        self.logger.error("%s: Retry limit reached for %s" %
                    (self.__class__.__name__, client.hostname))

    def GetExtra(self, client):
        self.logger.error("StatsLocal: GetExtra is not implemented yet")
        return []

    def GetCurrentEntry(self, client, e_type, e_name):
        self.logger.error("StatsLocal: GetCurrentEntry is not implemented yet")
        return []
