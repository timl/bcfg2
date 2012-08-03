import os
import sys
from Bcfg2.Client.POSIX import POSIXTool

class POSIXDirectory(POSIXTool):
    __req__ = ['name', 'perms', 'owner', 'group']

    def fully_specified(self, entry):
        if entry.get('dev_type') in ['block', 'char']:
            # check if major/minor are properly specified
            if (entry.get('major') == None or
                entry.get('minor') == None):
                self.logger.error('Entry %s not completely specified. '
                                  'Try running bcfg2-lint.' %
                                  (entry.get('name')))
                return False
        return True

    def verify(self, entry, modlist):
        ondisk = POSIXTool.verify(self, entry):
        if not ondisk:
            return False
        
        pruneTrue = True
        ex_ents = []
        if entry.get('prune', 'false').lower() == 'true':
            # check for any extra entries when prune='true' attribute is set
            try:
                entries = ['/'.join([entry.get('name'), ent])
                           for ent in os.listdir(entry.get('name'))]
                ex_ents = [e for e in entries if e not in modlist]
                if ex_ents:
                    pruneTrue = False
                    self.logger.info("POSIX: Directory %s contains "
                                     "extra entries:" % entry.get('name'))
                    self.logger.info(ex_ents)
                    nqtext = entry.get('qtext', '') + '\n'
                    nqtext += "Directory %s contains extra entries: " % \
                              entry.get('name')
                    nqtext += ":".join(ex_ents)
                    entry.set('qtext', nqtext)
                    [entry.append(lxml.etree.Element('Prune', path=x))
                     for x in ex_ents]
            except OSError:
                ex_ents = []
                pruneTrue = True

        return pruneTrue

    def install(self, entry):
        """Install device entries."""
        fmode = self._exists(entry)

        if fmode and not stat.S_ISDIR(fmode[stat.ST_MODE]):
            self.logger.info("Found a non-directory entry at %s, removing" %
                              entry.get('name'))
            try:
                os.unlink(entry.get('name'))
                fmode = False
            except OSError:
                err = sys.exc_info()[1]
                self.logger.error("Failed to unlink %s: %s" %
                                 (entry.get('name'), err))
                return False
        else:
            self.logger.debug("Found a pre-existing directory at %s" %
                              entry.get('name'))

        if not fmode:
            # todo: determine which parent directories had to be
            # created and set perms on them
            try:
                os.makedirs(entry.get("name"))
            except OSError:
                err = sys.exc_info()[1]
                self.logger.error('Failed to create directory %s: %s' %
                                  (entry.get('name'), err))
                return False
        if entry.get('prune', 'false') == 'true' and entry.get("qtext"):
            for pent in entry.findall('Prune'):
                pname = pent.get('path')
                ulfailed = False
                try:
                    self.logger.debug("Unlinking file %s" % pname)
                    os.unlink(pname)
                except OSError:
                    err = sys.exc_info()[1]
                    self.logger.error("Failed to unlink %s: %s" % (pname, err))
                    ulfailed = True
            if ulfailed:
                return False
        return POSIXTool.install(self, entry)
