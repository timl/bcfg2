""" the core of the CherryPy-powered server """

import inspect
import cherrypy
from Bcfg2.Server.Core import BaseCore
from cherrypy._cptools import XMLRPCController
from cherrypy._cpdispatch import XMLRPCDispatcher

class Core(XMLRPCController, BaseCore):
    def __init__(self, *args, **kwargs):
        XMLRPCController.__init__(self)
        BaseCore.__init__(self, *args, **kwargs)
        
        for name, func in inspect.getmembers(self, callable):
            if getattr(func, "exposed", False):
                setattr(self, name, cherrypy.expose(func))

    def critical_error(self, operation):
        self.logger.error(operation, exc_info=1)
        raise cherrypy._cperror.CherryPyException(operation)

    def run(self):
        cherrypy.quickstart(self,
                            config={'/': {'request.dispatch': XMLRPCDispatcher()}})
