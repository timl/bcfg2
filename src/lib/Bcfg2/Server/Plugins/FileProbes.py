""" This module allows you to probe a client for a file, which is then
added to the specification.  On subsequent runs, the file will be
replaced on the client if it is missing; if it has changed on the
client, it can either be updated in the specification or replaced on
the client """

import os
import sys
import errno
import lxml.etree
import Bcfg2.Options
import Bcfg2.Server
import Bcfg2.Server.Plugin
from Bcfg2.Compat import b64decode

PROBECODE = """#!/usr/bin/env python

import os
import pwd
import grp
import Bcfg2.Client.XML
from Bcfg2.Compat import b64encode

path = "%s"

if not os.path.exists(path):
    print("%%s does not exist" %% path)
    raise SystemExit(1)

stat = os.stat(path)
data = Bcfg2.Client.XML.Element("ProbedFileData",
                                name=path,
                                owner=pwd.getpwuid(stat[4])[0],
                                group=grp.getgrgid(stat[5])[0],
                                perms=oct(stat[0] & 07777))
data.text = b64encode(open(path).read())
print(Bcfg2.Client.XML.tostring(data, xml_declaration=False).decode('UTF-8'))
"""


class FileProbes(Bcfg2.Server.Plugin.Plugin,
                 Bcfg2.Server.Plugin.Probing):
    """ This module allows you to probe a client for a file, which is then
    added to the specification.  On subsequent runs, the file will be
    replaced on the client if it is missing; if it has changed on the
    client, it can either be updated in the specification or replaced on
    the client """

    name = 'FileProbes'
    __author__ = 'chris.a.st.pierre@gmail.com'

    def __init__(self, core, datastore):
        Bcfg2.Server.Plugin.Plugin.__init__(self, core, datastore)
        Bcfg2.Server.Plugin.Probing.__init__(self)
        self.config = Bcfg2.Server.Plugin.StructFile(os.path.join(self.data,
                                                                  'config.xml'),
                                                     fam=core.fam,
                                                     should_monitor=True)
        self.entries = dict()
        self.probes = dict()

    def GetProbes(self, metadata):
        """Return a set of probes for execution on client."""
        if metadata.hostname not in self.probes:
            cfg = self.core.plugins['Cfg']
            self.entries[metadata.hostname] = dict()
            self.probes[metadata.hostname] = []
            for entry in self.config.Match(metadata):
                path = entry.get("name")
                # do not probe for files that are already in Cfg and
                # for which update is false; we can't possibly do
                # anything with the data we get from such a probe
                if (entry.get('update', 'false').lower() == "false" and
                    not cfg.has_generator(entry, metadata)):
                    continue
                self.entries[metadata.hostname][path] = entry
                probe = lxml.etree.Element('probe', name=path,
                                           source=self.name,
                                           interpreter="/usr/bin/env python")
                probe.text = PROBECODE % path
                self.probes[metadata.hostname].append(probe)
                self.debug_log("Adding file probe for %s to %s" %
                               (path, metadata.hostname))
        return self.probes[metadata.hostname]

    def ReceiveData(self, metadata, datalist):
        """Receive data from probe."""
        self.debug_log("Receiving file probe data from %s" % metadata.hostname)

        for data in datalist:
            if data.text is None:
                self.logger.error("Got null response to %s file probe from %s" %
                                  (data.get('name'), metadata.hostname))
            else:
                try:
                    self.write_data(
                        lxml.etree.XML(data.text,
                                       parser=Bcfg2.Server.XMLParser),
                        metadata)
                except lxml.etree.XMLSyntaxError:
                    # if we didn't get XML back from the probe, assume
                    # it's an error message
                    self.logger.error(data.text)

    def write_data(self, data, metadata):
        """Write the probed file data to the bcfg2 specification."""
        filename = data.get("name")
        contents = b64decode(data.text)
        entry = self.entries[metadata.hostname][filename]
        cfg = self.core.plugins['Cfg']
        specific = "%s.H_%s" % (os.path.basename(filename), metadata.hostname)
        # we can't use os.path.join() for this because specific
        # already has a leading /, which confuses os.path.join()
        fileloc = os.path.join(cfg.data,
                               os.path.join(filename, specific).lstrip("/"))

        create = False
        try:
            cfg.entries[filename].bind_entry(entry, metadata)
        except (KeyError, Bcfg2.Server.Plugin.PluginExecutionError):
            create = True

        # get current entry data
        if entry.text and entry.get("encoding") == "base64":
            entrydata = b64decode(entry.text)
        else:
            entrydata = entry.text

        if create:
            self.logger.info("Writing new probed file %s" % fileloc)
            self.write_file(fileloc, contents)
            self.verify_file(filename, contents, metadata)
            infoxml = os.path.join(cfg.data, filename.lstrip("/"), "info.xml")
            self.write_infoxml(infoxml, entry, data)
        elif entrydata == contents:
            self.debug_log("Existing %s contents match probed contents" %
                           filename)
            return
        elif (entry.get('update', 'false').lower() == "true"):
            self.logger.info("Writing updated probed file %s" % fileloc)
            self.write_file(fileloc, contents)
            self.verify_file(filename, contents, metadata)
        else:
            self.logger.info("Skipping updated probed file %s" % fileloc)
            return

    def write_file(self, fileloc, contents):
        try:
            os.makedirs(os.path.dirname(fileloc))
        except OSError:
            err = sys.exc_info()[1]
            if err.errno == errno.EEXIST:
                pass
            else:
                self.logger.error("Could not create parent directories for %s: "
                                  "%s" % (fileloc, err))
                return

        try:
            open(fileloc, 'wb').write(contents)
        except IOError:
            err = sys.exc_info()[1]
            self.logger.error("Could not write %s: %s" % (fileloc, err))
            return

    def verify_file(self, filename, contents, metadata):
        # Service the FAM events queued up by the key generation so
        # the data structure entries will be available for binding.
        #
        # NOTE: We wait for up to ten seconds. There is some potential
        # for race condition, because if the file monitor doesn't get
        # notified about the new key files in time, those entries
        # won't be available for binding. In practice, this seems
        # "good enough".
        entry = self.entries[metadata.hostname][filename]
        cfg = self.core.plugins['Cfg']
        tries = 0
        updated = False
        while not updated:
            if tries >= 10:
                self.logger.error("%s still not registered" % filename)
                return
            self.core.fam.handle_events_in_interval(1)
            try:
                cfg.entries[filename].bind_entry(entry, metadata)
            except Bcfg2.Server.Plugin.PluginExecutionError:
                tries += 1
                continue

            # get current entry data
            if entry.get("encoding") == "base64":
                entrydata = b64decode(entry.text)
            else:
                entrydata = entry.text
            if entrydata == contents:
                updated = True
            tries += 1

    def write_infoxml(self, infoxml, entry, data):
        """ write an info.xml for the file """
        if os.path.exists(infoxml):
            return

        self.logger.info("Writing %s for %s" % (infoxml, data.get("name")))
        info = \
            lxml.etree.Element("Info",
                               owner=data.get("owner",
                                              Bcfg2.Options.MDATA_OWNER.value),
                               group=data.get("group",
                                              Bcfg2.Options.MDATA_GROUP.value),
                               perms=data.get("perms",
                                              Bcfg2.Options.MDATA_PERMS.value),
                               encoding=entry.get("encoding",
                                                  Bcfg2.Options.ENCODING.value))

        root = lxml.etree.Element("FileInfo")
        root.append(info)
        try:
            open(infoxml,
                 "w").write(
                lxml.etree.tostring(root,
                                    xml_declaration=False,
                                    pretty_print=True).decode('UTF-8'))
        except IOError:
            err = sys.exc_info()[1]
            self.logger.error("Could not write %s: %s" % (infoxml, err))
            return
