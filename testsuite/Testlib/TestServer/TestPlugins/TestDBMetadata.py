import os
import sys
import lxml.etree
from mock import Mock, patch
from django.core.management import setup_environ

os.environ['DJANGO_SETTINGS_MODULE'] = "Bcfg2.settings"

import Bcfg2.settings
Bcfg2.settings.DATABASE_NAME = \
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "test.sqlite")
Bcfg2.settings.DATABASES['default']['NAME'] = Bcfg2.settings.DATABASE_NAME

import Bcfg2.Server.Plugin
from Bcfg2.Server.Plugins.DBMetadata import *

from TestMetadata import datastore, groups_test_tree, clients_test_tree, \
    TestMetadata as _TestMetadata

for client in clients_test_tree.findall("Client"):
    newclient = lxml.etree.SubElement(groups_test_tree.getroot(),
                                      "Client", name=client.get("name"))
    lxml.etree.SubElement(newclient, "Group", name=client.get("profile"))

def test_syncdb():
    # create the test database
    setup_environ(Bcfg2.settings)
    from django.core.management.commands import syncdb
    cmd = syncdb.Command()
    rv = cmd.handle_noargs(interactive=False)
    assert os.path.exists(Bcfg2.settings.DATABASE_NAME)

class TestDBMetadata(_TestMetadata):
    def load_clients_data(self, metadata=None, xdata=None):
        if metadata is None:
            metadata = get_metadata_object()
        return metadata

    def get_metadata_object(self, core=None, watch_clients=False):
        if core is None:
            core = Mock()
        metadata = DBMetadata(core, datastore, watch_clients=watch_clients)
        return metadata

    @patch('os.path.exists')
    def test__init(self, mock_exists):
        core = Mock()
        core.fam = Mock()
        mock_exists.return_value = False
        metadata = self.get_metadata_object(core=core, watch_clients=True)
        self.assertIsInstance(metadata, Bcfg2.Server.Plugin.DatabaseBacked)
        core.fam.AddMonitor.assert_called_once_with(os.path.join(metadata.data,
                                                                 "groups.xml"),
                                                    metadata)
        
        mock_exists.return_value = True
        core.fam.reset_mock()
        metadata = self.get_metadata_object(core=core, watch_clients=True)
        core.fam.AddMonitor.assert_any_call(os.path.join(metadata.data,
                                                         "groups.xml"),
                                            metadata)
        core.fam.AddMonitor.assert_any_call(os.path.join(metadata.data,
                                                         "clients.xml"),
                                            metadata)
    
    @patch("Bcfg2.Server.Plugins.Metadata.XMLMetadataConfig.load_xml")
    @patch("Bcfg2.Server.Plugins.Metadata.Metadata._handle_clients_xml_event")
    @patch("Bcfg2.Server.Plugins.DBMetadata.DBMetadata.list_clients")
    def test_clients_xml_event(self, mock_list_clients, mock_handle_event,
                               mock_load_xml):
        metadata = self.get_metadata_object()
        metadata.profiles = ["group1", "group2"]
        evt = Mock()
        evt.filename = os.path.join(datastore, "DBMetadata", "clients.xml")
        evt.code2str = Mock(return_value="changed")
        metadata.HandleEvent(evt)
        self.assertFalse(mock_handle_event.called)
        self.assertFalse(mock_load_xml.called)

        mock_load_xml.reset_mock()
        mock_handle_event.reset_mock()
        mock_list_clients.reset_mock()
        metadata._handle_file("clients.xml")
        metadata.HandleEvent(evt)
        mock_handle_event.assert_called_with(metadata, evt)
        mock_list_clients.assert_any_call()
        mock_load_xml.assert_any_call()

    def test_add_group(self):
        pass

    def test_add_bundle(self):
        pass

    def test_add_client(self):
        # todo
        pass

    def test_update_group(self):
        pass

    def test_update_bundle(self):
        pass

    def test_update_client(self):
        pass

    def test_list_clients(self):
        # todo
        pass

    def test_remove_group(self):
        pass

    def test_remove_bundle(self):
        pass

    def test_remove_client(self):
        # todo
        pass

    def test__set_profile(self):
        # todo
        pass
