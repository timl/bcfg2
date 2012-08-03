import os
import sys
from Bcfg2.Client.POSIX import POSIXTool

class POSIXHardlink(POSIXTool):
    __req__ = ['name', 'to']

    def fully_specified(self, entry):
        if not entry.get("to"):
            return False
        return True

    def verify(self, entry, _):
        rv = True

        try:
            if not os.path.samefile(entry.get('name'), entry.get('to')):
                msg = "Hardlink %s is incorrect" % entry.get('name')
                self.logger.debug(msg)
                entry.set('qtext', "\n".join([entry.get('qtext', ''), msg]))
                rv = False
        except OSError:
            entry.set('current_exists', 'false')
            return False

        rv &= self._verify_secontext(entry)
        return rv
    
    def install(self, entry):
        self._paranoid_backup(entry)
        ondisk = self._exists(entry, remove=True)
        if ondisk:
            self.logger.info("Hardlink %s cleanup failed" %
                             entry.get('name'))
        try:
            os.link(entry.get('to'), entry.get('name'))
            return True
        except OSError:
            err = sys.exc_info()[1]
            self.logger.error("Failed to create hardlink %s to %s: %s" %
                              (entry.get('name'), entry.get('to'), err))
            return False

