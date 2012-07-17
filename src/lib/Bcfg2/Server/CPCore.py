""" the core of the CherryPy-powered server """

import atexit
import inspect
import cherrypy
import Bcfg2.Options
from Bcfg2.Bcfg2Py3k import urlparse
from Bcfg2.Server.Core import BaseCore
from cherrypy._cptools import XMLRPCController
from cherrypy._cpdispatch import XMLRPCDispatcher

cherrypy.config.update({'environment': 'embedded'})

if cherrypy.engine.state == 0:
    cherrypy.engine.start(blocking=False)
    atexit.register(cherrypy.engine.stop)

class Core(XMLRPCController, BaseCore):
    def critical_error(self, operation):
        self.logger.error(operation, exc_info=1)
        raise cherrypy._cperror.CherryPyException(operation)


def application(environ, start_response):
    optinfo = dict()
    optinfo.update(Bcfg2.Options.CLI_COMMON_OPTIONS)
    optinfo.update(Bcfg2.Options.SERVER_COMMON_OPTIONS)
    optinfo.update(Bcfg2.Options.DAEMON_COMMON_OPTIONS)
    setup = Bcfg2.Options.OptionParser(optinfo)
    setup.parse(['-C', environ['config']])

    root = Core(setup['repo'], setup['plugins'],
                setup['password'], setup['encoding'],
                ca=setup['ca'],
                filemonitor=setup['filemonitor'],
                start_fam_thread=True,
                setup=setup)
    config = {'global': {'tools.xmlrpc.allow_none': 1}}
    cherrypy.tree.mount(root, config=config)
    return cherrypy.tree(environ, start_response)
