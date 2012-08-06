import os
import sys
import stat
import Bcfg2.Client.XML
from base import POSIXTool

class POSIXDirectory(POSIXTool):
    __req__ = ['name', 'perms', 'owner', 'group']

    def verify(self, entry, modlist):
        ondisk = POSIXTool.verify(self, entry, modlist)
        if not ondisk:
            return False

        if not stat.S_ISDIR(ondisk[stat.ST_MODE]):
            self.logger.info("POSIX: %s is not a directory" % entry.get('name'))
            return False
        
        pruneTrue = True
        if entry.get('prune', 'false').lower() == 'true':
            # check for any extra entries when prune='true' attribute is set
            try:
                entries = [os.path.join(entry.get('name'), ent)
                           for ent in os.listdir(entry.get('name'))]
                extras = [e for e in entries if e not in modlist]
                if extras:
                    pruneTrue = False
                    msg = "Directory %s contains extra entries: %s" % \
                        (entry.get('name'), "; ".join(extras))
                    self.logger.info("POSIX: " + msg)
                    entry.set('qtext', entry.get('qtext', '') + '\n' + msg)
                    for extra in extras:
                        XML.SubElement('Prune', path=extra)
            except OSError:
                pruneTrue = True

        return pruneTrue

    def install(self, entry):
        """Install device entries."""
        fmode = self._exists(entry)

        if fmode and not stat.S_ISDIR(fmode[stat.ST_MODE]):
            self._paranoid_backup(entry)
            self.logger.info("POSIX: Found a non-directory entry at %s, "
                             "removing" % entry.get('name'))
            try:
                os.unlink(entry.get('name'))
                fmode = False
            except OSError:
                err = sys.exc_info()[1]
                self.logger.error("POSIX: Failed to unlink %s: %s" %
                                  (entry.get('name'), err))
                return False
        else:
            self.logger.debug("POSIX: Found a pre-existing directory at %s" %
                              entry.get('name'))

        if not fmode:
            # todo: determine which parent directories had to be
            # created and set perms on them
            try:
                os.makedirs(entry.get("name"))
            except OSError:
                err = sys.exc_info()[1]
                self.logger.error('POSIX: Failed to create directory %s: %s' %
                                  (entry.get('name'), err))
                return False
        if entry.get('prune', 'false') == 'true' and entry.get("qtext"):
            for pent in entry.findall('Prune'):
                pname = pent.get('path')
                ulfailed = False
                try:
                    self.logger.debug("POSIX: Unlinking file %s" % pname)
                    os.unlink(pname)
                except OSError:
                    err = sys.exc_info()[1]
                    self.logger.error("POSIX: Failed to unlink %s: %s" %
                                      (pname, err))
                    ulfailed = True
            if ulfailed:
                return False
        return POSIXTool.install(self, entry)
