"""All POSIX Type client support for Bcfg2."""

import binascii
from datetime import datetime
import difflib
import errno
import grp
import logging
import os
import pwd
import shutil
import stat
import sys
import time
import lxml.etree

import Bcfg2.Client.Tools
import Bcfg2.Options

log = logging.getLogger(__name__)

try:
    import selinux
    has_selinux = True
except ImportError:
    has_selinux = False

try:
    import posix1e
    has_acls = True
except ImportError:
    has_acls = False


# map between dev_type attribute and stat constants
device_map = {'block': stat.S_IFBLK,
              'char': stat.S_IFCHR,
              'fifo': stat.S_IFIFO}

# map between permissions characters and numeric ACL constants
acl_map = dict(r=posix1e.ACL_READ,
               w=posix1e.ACL_WRITE,
               x=posix1e.ACL_EXECUTE)


class POSIX(Bcfg2.Client.Tools.Tool):
    """POSIX File support code."""
    name = 'POSIX'
    __handles__ = [('Path', 'device'),
                   ('Path', 'directory'),
                   ('Path', 'file'),
                   ('Path', 'hardlink'),
                   ('Path', 'nonexistent'),
                   ('Path', 'permissions'),
                   ('Path', 'symlink')]
    # TODO: __req__

    # grab paranoid options from /etc/bcfg2.conf
    opts = {'ppath': Bcfg2.Options.PARANOID_PATH,
            'max_copies': Bcfg2.Options.PARANOID_MAX_COPIES}
    setup = Bcfg2.Options.OptionParser(opts)
    setup.parse([])
    ppath = setup['ppath']
    max_copies = setup['max_copies']

    def canInstall(self, entry):
        """Check if entry is complete for installation."""
        if Bcfg2.Client.Tools.Tool.canInstall(self, entry):
            if (entry.get('type') == 'file' and
                entry.text is None and
                entry.get('empty', 'false') == 'false'):
                return False
            return True
        else:
            return False

    def gatherCurrentData(self, entry):
        if entry.tag == 'Path' and entry.get('type') == 'file':
            try:
                ondisk = os.stat(entry.get('name'))
            except OSError:
                entry.set('current_exists', 'false')
                self.logger.debug("%s %s does not exist" %
                                  (entry.tag, entry.get('name')))
                return False
            try:
                entry.set('current_owner', str(ondisk[stat.ST_UID]))
                entry.set('current_group', str(ondisk[stat.ST_GID]))
            except (OSError, KeyError):
                pass

            entry.set('perms', str(oct(ondisk[stat.ST_MODE])[-4:]))

            if has_selinux:
                try:
                    entry.set('current_secontext',
                              selinux.getfilecon(entry.get('name'))[1])
                except (OSError, KeyError):
                    pass

            if has_acls:
                for aclkey, perms in self._list_file_acls(entry):
                    atype, scope, qual = aclkey
                    aclentry = lxml.etree.Element("ACL", type=atype,
                                                  perms=perms)
                    if scope == posix1e.ACL_USER:
                        aclentry.set("scope", "user")
                    elif scope == posix1e.ACL_GROUP:
                        aclentry.set("scope", "group")
                    else:
                        self.logger.debug("Unknown ACL scope %s on %s" %
                                          (scope, entry.get("name")))
                        continue
                    aclentry.set(aclentry.get("scope"), qual)
                    entry.append(aclentry)







    def InstallPath(self, entry):
        """Dispatch install to the proper method according to type"""
        ret = getattr(self, 'Install%s' % entry.get('type'))
        return ret(entry)

    def VerifyPath(self, entry, _):
        """Dispatch verify to the proper method according to type"""
        ret = getattr(self, 'Verify%s' % entry.get('type'))(entry, _)
        if entry.get('qtext') and self.setup['interactive']:
            entry.set('qtext',
                      '%s\nInstall %s %s: (y/N) ' %
                      (entry.get('qtext'),
                       entry.get('type'), entry.get('name')))
        return ret

