""" the core of the CherryPy-powered server """

import sys
import base64
import atexit
import cherrypy
import Bcfg2.Options
from Bcfg2.Bcfg2Py3k import urlparse, xmlrpclib
from Bcfg2.Server.Core import BaseCore
from cherrypy.lib import xmlrpcutil
from cherrypy._cptools import ErrorTool

if cherrypy.engine.state == 0:
    cherrypy.engine.start(blocking=False)
    atexit.register(cherrypy.engine.stop)

# define our own error handler that handles xmlrpclib.Fault objects
# and so allows for the possibility of returning proper error
# codes. this obviates the need to use the builtin CherryPy xmlrpc
# tool
def on_error(*args, **kwargs):
    err = sys.exc_info()[1]
    if not isinstance(err, xmlrpclib.Fault):
        err = xmlrpclib.Fault(xmlrpclib.INTERNAL_ERROR, str(err))
    xmlrpcutil._set_response(xmlrpclib.dumps(err))
cherrypy.tools.xmlrpc_error = ErrorTool(on_error)


class Core(BaseCore):
    _cp_config = {'tools.xmlrpc_error.on': True,
                  'tools.bcfg2_authn.on': True}

    def __init__(self, *args, **kwargs):
        BaseCore.__init__(self, *args, **kwargs)

        cherrypy.tools.bcfg2_authn = cherrypy.Tool('on_start_resource',
                                                   self.do_authn)

        self.rmi = dict()
        if self.plugins:
            for pname, pinst in list(self.plugins.items()):
                for mname in pinst.__rmi__:
                    self.rmi["%s.%s" % (pname, mname)] = getattr(pinst, mname)

    def do_authn(self):
        try:
            header = cherrypy.request.headers['Authorization']
        except KeyError:
            self.critical_error("No authentication data presented")
        auth_type, auth_content = header.split()
        try:
            # py3k compatibility
            auth_content = base64.standard_b64decode(auth_content)
        except TypeError:
            auth_content = \
                base64.standard_b64decode(bytes(auth_content.encode('ascii')))
        try:
            # py3k compatibility
            try:
                username, password = auth_content.split(":")
            except TypeError:
                username, pw = auth_content.split(bytes(":", encoding='utf-8'))
                password = pw.decode('utf-8')
        except ValueError:
            username = auth_content
            password = ""

        # FIXME: Get client cert
        #cert = self.request.getpeercert()
        cert = None
        address = (cherrypy.request.remote.ip, cherrypy.request.remote.name)
        return self.authenticate(cert, username, password, address)

    @cherrypy.expose
    def default(self, *vpath, **params):
        # needed to make enough changes to the stock XMLRPCController
        # to support plugin.__rmi__ and prepending client address that
        # we just rewrote.  it clearly wasn't written with inheritance
        # in mind :(
        rpcparams, rpcmethod = xmlrpcutil.process_body()
        if "." not in rpcmethod:
            address = (cherrypy.request.remote.ip, cherrypy.request.remote.name)
            rpcparams = (address, ) + rpcparams

            subhandler = self
            for attr in str(rpcmethod).split('.'):
                subhandler = getattr(subhandler, attr, None)
                
            if subhandler and getattr(subhandler, "exposed", False):
                handler = subhandler
            else:
                raise Exception('method "%s" is not supported' % attr)
        else:
            try:
                handler = self.rmi[rpcmethod]
            except:
                raise Exception('method "%s" is not supported' % rpcmethod)

        body = subhandler(*rpcparams, **params)
        
        xmlrpcutil.respond(body, 'utf-8', True)
        return cherrypy.serving.response.body


def parse_opts(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    optinfo = dict()
    optinfo.update(Bcfg2.Options.CLI_COMMON_OPTIONS)
    optinfo.update(Bcfg2.Options.SERVER_COMMON_OPTIONS)
    optinfo.update(Bcfg2.Options.DAEMON_COMMON_OPTIONS)
    setup = Bcfg2.Options.OptionParser(optinfo, argv=argv)
    setup.parse(argv)
    return setup

def application(environ, start_response):
    """ running behind Apache as a WSGI app is not currently
    supported, but I'm keeping this code here because I hope for it to
    be supported some day.  we'll need to set up an AMQP task queue
    and related magic for that to happen, though. """
    cherrypy.config.update({'environment': 'embedded'})

    setup = parse_opts(argv=['-C', environ['config']])
    root = Core(setup, start_fam_thread=True)
    cherrypy.tree.mount(root)
    return cherrypy.tree(environ, start_response)

if __name__ == "__main__":
    setup = parse_opts()

    root = Core(setup, start_fam_thread=True)
    config = {'global': {'engine.autoreload.on': False,
                         'log.screen': True}}

    cherrypy.quickstart(root, config=config)

