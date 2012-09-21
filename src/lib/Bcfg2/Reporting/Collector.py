import atexit
import daemon
import logging
import time
import traceback
import threading

import Bcfg2.Logger
from Bcfg2.Reporting.Transport import load_transport_from_config, \
    TransportError, TransportImportError
from Bcfg2.Reporting.Storage import load_storage_from_config, \
    StorageError, StorageImportError

class ReportingError(Exception):
    """Generic reporting exception"""
    pass

class ReportingCollector(object):
    """The collecting process for reports"""

    def __init__(self, setup):
        self.setup = setup
        self.datastore = setup['repo']
        self.encoding = setup['encoding']

        level = logging.DEBUG

        Bcfg2.Logger.setup_logging('bcfg2-report-collector',
                                   to_console=logging.INFO,
                                   to_syslog=setup['syslog'],
                                   to_file=setup['logging'],
                                   level=level)
        self.logger = logging.getLogger('bcfg2-report-collector')

        try:
            self.transport = load_transport_from_config(setup)
            self.storage = load_storage_from_config(setup)
        except TransportError:
            self.logger.error("Failed to load transport: %s" %
                traceback.format_exc().splitlines()[-1])
            raise ReportingError
        except StorageError:
            self.logger.error("Failed to load storage: %s" %
                traceback.format_exc().splitlines()[-1])
            raise ReportingError

        try:
            self.logger.debug("Validating storage %s" % 
                self.storage.__class__.__name__)
            self.storage.validate()
        except:
            self.logger.error("Storage backed %s failed to validate: %s" %
                (self.storage.__class__.__name__, 
                    traceback.format_exc().splitlines()[-1]))

        self.terminate = threading.Event()
        atexit.register(self.shutdown)
        self.context = daemon.DaemonContext()

        if self.setup['daemon']:
            self._daemonize()
            #open(self.setup['daemon'], "w").write("%s\n" % os.getpid())

        self.transport.start_monitor(self)

        while not self.terminate.isSet():
            try:
                interaction = self.transport.fetch()
                if not interaction:
                    continue
                try:
                    start = time.time()
                    self.storage.import_interaction(interaction)
                    self.logger.info("Imported interaction for %s in %ss" %
                        (interaction.get('hostname', '<unknown>'),
                            time.time() - start))
                except:
                    #TODO requeue?
                    raise
            except KeyboardInterrupt:
                self.shutdown()
            except:
                self.logger.error("Unhandled exception in main loop %s" %
                    traceback.format_exc().splitlines()[-1])

    def _daemonize(self):
        raise ReportingError("Not there yet")

    def shutdown(self):
        """Cleanup and go"""
        self.terminate.set()
        if self.transport:
            self.transport.shutdown()
        if self.storage:
            self.storage.shutdown()

