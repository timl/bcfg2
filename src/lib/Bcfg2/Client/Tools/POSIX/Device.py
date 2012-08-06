import os
import sys
from base import POSIXTool

class POSIXDevice(POSIXTool):
    __req__ = ['name', 'dev_type', 'perms', 'owner', 'group']

    def fully_specified(self, entry):
        if entry.get('dev_type') in ['block', 'char']:
            # check if major/minor are properly specified
            if (entry.get('major') == None or
                entry.get('minor') == None):
                return False
        return True

    def verify(self, entry, _):
        """Verify device entry."""
        ondisk = POSIXTool.verify(self, entry)
        if not ondisk:
            return False
        
        # attempt to verify device properties as specified in config
        dev_type = entry.get('dev_type')
        if dev_type in ['block', 'char']:
            major = int(entry.get('major'))
            minor = int(entry.get('minor'))
            if major != os.major(ondisk.st_rdev):
                entry.set('current_mtime', mtime)
                msg = ("Major number for device %s is incorrect. "
                       "Current major is %s but should be %s" %
                       (path, os.major(ondisk.st_rdev), major))
                self.logger.debug(msg)
                entry.set('qtext', entry.get('qtext') + "\n" + msg)
                rv = False

            if minor != os.minor(ondisk.st_rdev):
                entry.set('current_mtime', mtime)
                msg = ("Minor number for device %s is incorrect. "
                       "Current minor is %s but should be %s" %
                       (path, os.minor(ondisk.st_rdev), minor))
                self.logger.debug(msg)
                entry.set('qtext', entry.get('qtext') + "\n" + msg)
                rv = False

        return rv

    def install(self, entry):
        # todo: paranoid backup
        if not self._exists(entry, remove=True):
            try:
                dev_type = entry.get('dev_type')
                mode = device_map[dev_type] | int(entry.get('mode', '0600'), 8)
                if dev_type in ['block', 'char']:
                    # check if major/minor are properly specified
                    if (entry.get('major') == None or
                        entry.get('minor') == None):
                        self.logger.error('Entry %s not completely specified. '
                                          'Try running bcfg2-lint.' %
                                          entry.get('name'))
                        return False
                    major = int(entry.get('major'))
                    minor = int(entry.get('minor'))
                    device = os.makedev(major, minor)
                    os.mknod(entry.get('name'), mode, device)
                else:
                    os.mknod(entry.get('name'), mode)
            except (KeyError, OSError):
                err = sys.exc_info()[1]
                self.logger.error('Failed to install %s: %s' %
                                  (entry.get('name'), err))
                return False
        return POSIXTool.install(self, entry)
