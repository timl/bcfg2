"""
The local transport.  Stats are pickled and written to
<repo>/store/<hostname>-timestamp

Leans on FileMonitor to detect changes
"""

import os
import os.path
import select
import time
import traceback
from Bcfg2.Reporting.Transport.base import TransportBase, TransportError

import Bcfg2.Server.FileMonitor

class LocalFilesystem(TransportBase):
    def __init__(self, setup):
        super(LocalFilesystem, self).__init__(setup)

        self.work_path = "%s/work" % self.data
        self.logger.debug("LocalFilesystem: work path %s" % self.work_path)
        self.fmon = None

        #setup our local paths or die
        if not os.path.exists(self.work_path):
            try:
                os.makedirs(self.work_path)
            except:
                self.logger.error("%s: Unable to create storage: %s" %
                    (self.__class__.__name__,
                        traceback.format_exc().splitlines()[-1]))
                raise TransportError

    def start_monitor(self, collector):
        """Start the file monitor.  Most of this comes from BaseCore"""
        setup = self.setup
        try:
            fmon = Bcfg2.Server.FileMonitor.available[setup['filemonitor']]
        except KeyError:
            self.logger.error("File monitor driver %s not available; "
                              "forcing to default" % setup['filemonitor'])
            fmon = Bcfg2.Server.FileMonitor.available['default']

        fmdebug = setup.get('debug', False)
        try:
            self.fmon = fmon(debug=fmdebug)
        except IOError:
            msg = "Failed to instantiate file monitor %s" % setup['filemonitor']
            self.logger.error(msg, exc_info=1)
            raise TransportError(msg)
        self.fmon.start()
        self.fmon.AddMonitor(self.work_path, self)

    def store(self, hostname, payload):
        raise NotImplementedError

    def fetch(self):
        """Fetch the next object"""
        event = None
        fmonfd = self.fmon.fileno()
        if self.fmon.pending():
           event = self.fmon.get_event()
        elif fmonfd:
            select.select([fmonfd], [], [], self.timeout)
            if self.fmon.pending():
               event = self.fmon.get_event()
        else:
            # pseudo.. if nothings pending sleep and loop
            time.sleep(self.timeout)

        if not event or event.filename == self.work_path:
            return None

        #deviate from the normal routines here we only want one event
        etype = event.code2str()
        self.logger.debug("Recieved event %s for %s" % (etype, event.filename))
        if etype in ('created', 'exists'):
            self.logger.debug("Handling event %s" % event.filename)
            return os.path.join(self.work_path, event.filename)
        return None

    def shutdown(self):
        """Called at program exit"""
        if self.fmon:
            self.fmon.shutdown()

