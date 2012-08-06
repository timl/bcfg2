"""All POSIX Type client support for Bcfg2."""

import os
import sys
import pkgutil
import Bcfg2.Client.Tools
from base import POSIXTool

class POSIX(Bcfg2.Client.Tools.Tool):
    """POSIX File support code."""
    name = 'POSIX'

    def __init__(self, logger, setup, config):
        Bcfg2.Client.Tools.Tool.__init__(self, logger, setup, config)
        self.ppath = setup['ppath']
        self.max_copies = setup['max_copies']
        self._handlers = self._load_handlers()
        self.logger.debug("POSIX: Handlers loaded: %s" %
                          (", ".join(self._handlers.keys())))
        self.__req__ = dict(Path=dict())
        for etype, hdlr in self._handlers.items():
            self.__req__['Path'][etype] = hdlr.__req__
            self.__handles__.append(('Path', etype))
        # Tool.__init__() sets up the list of handled entries, but we
        # need to do it again after __handles__ has been populated. we
        # can't populate __handles__ when the class is created because
        # _load_handlers() _must_ be called at run-time, not at
        # compile-time.
        for struct in config:
            self.handled = [e for e in struct if self.handlesEntry(e)]

    def _load_handlers(self):
        # this must be called at run-time, not at compile-time, or we
        # get wierd circular import issues.
        rv = dict()
        if hasattr(pkgutil, 'walk_packages'):
            submodules = pkgutil.walk_packages(path=__path__)
        else:
            # python 2.4
            import glob
            submodules = []
            for path in __path__:
                for submodule in glob.glob(os.path.join(path, "*.py")):
                    mod = os.path.splitext(os.path.basename(submodule))[0]
                    if mod not in ['__init__']:
                        submodules.append((None, mod, True))

        for submodule in submodules:
            if submodule[1] == 'base':
                continue
            module = getattr(__import__("%s.%s" %
                                        (__name__,
                                         submodule[1])).Client.Tools.POSIX,
                             submodule[1])
            hdlr = getattr(module, "POSIX" + submodule[1])
            if POSIXTool in hdlr.__mro__:
                # figure out what entry type this handler handles
                etype = hdlr.__name__[5:].lower()
                rv[etype] = hdlr(self.logger, self.setup, self.config)
        return rv

    def canVerify(self, entry):
        if not Bcfg2.Client.Tools.Tool.canVerify(self, entry):
            return False
        if not self.fully_specified(entry):
            self.logger.error('POSIX: Cannot verify incomplete entry %s. '
                              'Try running bcfg2-lint.' %
                              entry.get('name'))
            return False
        return True

    def canInstall(self, entry):
        """Check if entry is complete for installation."""
        if not Bcfg2.Client.Tools.Tool.canInstall(self, entry):
            return False
        if not self.fully_specified(entry):
            self.logger.error('POSIX: Cannot install incomplete entry %s. '
                              'Try running bcfg2-lint.' %
                              entry.get('name'))
            return False
        return True

    def gatherCurrentData(self, entry):
        return self._handlers[entry.get("type")].gather_data(entry)

    def InstallPath(self, entry):
        """Dispatch install to the proper method according to type"""
        self.logger.debug("POSIX: Installing entry %s:%s:%s" %
                          (entry.tag, entry.get("type"), entry.get("name")))
        return self._handlers[entry.get("type")].install(entry)

    def VerifyPath(self, entry, modlist):
        """Dispatch verify to the proper method according to type"""
        self.logger.debug("POSIX: Verifying entry %s:%s:%s" %
                          (entry.tag, entry.get("type"), entry.get("name")))
        ret =  self._handlers[entry.get("type")].verify(entry, modlist)
        if entry.get('qtext') and self.setup['interactive']:
            entry.set('qtext',
                      '%s\nInstall %s %s: (y/N) ' %
                      (entry.get('qtext'),
                       entry.get('type'), entry.get('name')))
        return ret

