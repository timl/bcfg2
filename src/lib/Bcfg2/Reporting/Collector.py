import atexit
import daemon
import logging
import traceback
import threading

import Bcfg2.Logger
from Bcfg2.Reporting.Transport import load_transport_from_config, \
    TransportError, TransportImportError

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
        except TransportError:
            self.logger.error("Failed to load transport: %s" %
                traceback.format_exc().splitlines()[-1])
            raise ReportingError

        self.terminate = threading.Event()
        atexit.register(self.shutdown)
        self.context = daemon.DaemonContext()

        if self.setup['daemon']:
            self._daemonize()
            #open(self.setup['daemon'], "w").write("%s\n" % os.getpid())

        self.transport.start_monitor(self)

        while not self.terminate.isSet():
            try:
                xdata = self.transport.fetch()
                if not xdata:
                    continue
                print xdata
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

