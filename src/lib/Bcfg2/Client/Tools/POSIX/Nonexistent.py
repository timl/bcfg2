import os
import sys
import shutil
from Bcfg2.Client.POSIX import POSIXTool

class POSIXNonexistent(POSIXTool):
    __req__ = ['name']

    def verify(self, entry, _):
        return not os.path.lexists(entry.get('name'))
        
    def install(self, entry):
        self._paranoid_backup(entry)
        ename = entry.get('name')
        if entry.get('recursive').lower() == 'true':
            # ensure that configuration spec is consistent first
            if [e for e in self.buildModlist() \
                if e.startswith(ename) and e != ename]:
                self.logger.error('Not installing %s. One or more files '
                                  'in this directory are specified in '
                                  'your configuration.' % ename)
                return False
            rm = shutil.rmtree
        elif os.path.isdir(ename):
            rm = os.rmdir
        else:
            rm = os.remove
        try:
            rm(ename)
            return True
        except OSError:
            err = sys.exc_info()[1]
            self.logger.error('Failed to remove %s: %s' % (ename, err))
            return False
