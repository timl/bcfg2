""" the core of the CherryPy-powered server """

import inspect
import cherrypy
from Bcfg2.Bcfg2Py3k import urlparse
from Bcfg2.Server.Core import BaseCore
from cherrypy._cptools import XMLRPCController
from cherrypy._cpdispatch import XMLRPCDispatcher

class Core(XMLRPCController, BaseCore):
    def critical_error(self, operation):
        self.logger.error(operation, exc_info=1)
        raise cherrypy._cperror.CherryPyException(operation)

    def run(self):
        if self.setup['daemon']:
            self._daemonize()
        
        hostname, port = urlparse(self.setup['location'])[1].split(':')
        if self.setup['listen_all']:
            hostname = '0.0.0.0'
        if hostname == "localhost":
            # CherryPy warns that 'localhost' isn't a good idea, since
            # it can be either IPv4 or IPv6.  if someone's actually
            # using localhost, just assume they mean IPv4.
            hostname = '127.0.0.1'
        try:
            from cherrypy.wsgiserver.ssl_pyopenssl import pyOpenSSLAdapter \
                as SSLAdapter
        except ImportError:
            from cherrypy.wsgiserver.ssl_builtin import BuiltinSSLAdapter \
                as SSLAdapter

        config = {'global': 
                  {'server.socket_port': int(port),
                   'server.socket_host': hostname,
                   'server.ssl_certificate_chain': self.setup['ca'],
                   'server.ssl_private_key': self.setup['key'],
                   'server.ssl_certificate': self.setup['cert'],
                   'server.ssl_adapter': SSLAdapter(self.setup['cert'],
                                                    self.setup['key']),
                   'tools.xmlrpc.allow_none': 1}}
        # the CherryPy XMLRPCDispatcher handles /RPC2 urls, but does
        # so with 301 redirects, which the bcfg2 client doesn't
        # currently handle, so we just make /RPC2 an alias for /
        self.RPC2 = self
        cherrypy.quickstart(self, config=config)
