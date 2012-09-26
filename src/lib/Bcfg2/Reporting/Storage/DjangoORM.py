"""
The base for the original DjangoORM (DBStats)
"""

import os
import traceback
from lxml import etree

# This will change again
os.environ['DJANGO_SETTINGS_MODULE'] = 'Bcfg2.settings'
import Bcfg2.settings

from Bcfg2.Compat import md5
from Bcfg2.Reporting.Storage.base import StorageBase, StorageError
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.core.cache import cache
from django.db import transaction

#Used by GetCurrentEntry
import difflib
from Bcfg2.Compat import b64decode
from Bcfg2.Server.Reports.reports.models import *

def _entry_get_or_create(cls, act_dict):
    """Helper to quickly lookup an object"""
    cls_name = cls().__class__.__name__
    act_hash = hash_entry(act_dict)

    # TODO - get form cache and validate
    act_key = "%s_%s" % (cls_name, act_hash)
    newact = cache.get(act_key)
    if newact:
        return newact

    acts = cls.objects.filter(hash_key=act_hash)
    if len(acts) > 0:
        for act in acts:
           for key in act_dict:
               if act_dict[key] != getattr(act, key):
                   continue
               #match found
               newact = act
               break

    # worst case, its new
    if not newact:
        newact = cls(**act_dict)
        newact.save(hash_key=act_hash)
               
    cache.set(act_key, newact)
    return newact


class DjangoORM(StorageBase):
    def __init__(self, setup):
        super(DjangoORM, self).__init__(setup)
        self._load_stat = None
        self._ClientMetadata = None
        self.size_limit = setup.get('reporting_size_limit')

    @transaction.commit_on_success
    def _import_interaction(self, interaction):
        """Real import function"""
        hostname = interaction['hostname']
        stats = etree.fromstring(interaction['stats'])
        metadata = interaction['metadata']
        server = metadata['server']

        client = cache.get(hostname)
        if not client:
            client, created = Client.objects.get_or_create(name=hostname)
            if created:
                self.logger.debug("Client %s added to the db" % hostname)
            cache.set(hostname, client)

        timestamp = datetime(*strptime(stats.get('time'))[0:6])
        if len(Interaction.objects.filter(client=client, timestamp=timestamp)) > 0:
            self.logger.warn("Interaction for %s at %s already exists" %
                    (hostname, timestamp))
            return

        inter = Interaction(client=client,
                             timestamp=timestamp,
                             state=stats.get('state', default="unknown"),
                             repo_rev_code=stats.get('revision',
                                                          default="unknown"),
                             goodcount=stats.get('good', default="0"),
                             totalcount=stats.get('total', default="0"),
                             server=server)
        inter.save()
        self.logger.debug("Interaction for %s at %s with INSERTED in to db" % 
                (client.id, timestamp))

        imeta = InteractionMetadata(interaction=inter)
        profile, created = Group.objects.get_or_create(name=metadata['profile'])
        imeta.profile = profile
        imeta.save() # save here for m2m

        #FIXME - this should be more efficient
        for group_name in metadata['groups']:
            group = cache.get("GROUP_" + group_name)
            if not group:
                group, created = Group.objects.get_or_create(name=group_name)
                if created:
                    self.logger.debug("Added group %s" % group)
                cache.set("GROUP_" + group_name, group)
                
            imeta.groups.add(group)
        for bundle_name in metadata['bundles']:
            bundle = cache.get("BUNDLE_" + bundle_name)
            if not bundle:
                bundle, created = Bundle.objects.get_or_create(name=bundle_name)
                if created:
                    self.logger.debug("Added bundle %s" % bundle)
                cache.set("BUNDLE_" + bundle_name, bundle)
            imeta.bundles.add(bundle)
        imeta.save()

        counter_fields = {TYPE_BAD: 0,
                          TYPE_MODIFIED: 0,
                          TYPE_EXTRA: 0}
        pattern = [('Bad/*', TYPE_BAD),
                   ('Extra/*', TYPE_EXTRA),
                   ('Modified/*', TYPE_MODIFIED)]
        for (xpath, state) in pattern:
            for entry in stats.findall(xpath):
                counter_fields[state] = counter_fields[state] + 1

                entry_type = entry.tag
                name = entry.get('name')
                exists = entry.get('current_exists', default="true").lower() == "true"
    
                # handle server failures differently
                failure = entry.get('failure', '')
                if failure:
                    act_dict = dict(name=name, entry_type=entry_type,
                        message=failure)
                    newact = _entry_get_or_create(FailureEntry, act_dict)
                    inter.failures.add(newact)
                    continue

                act_dict = dict(name=name, state=state, exists=exists)

                if entry_type == 'Action':
                    act_dict['status'] = entry.get('status', default="check")
                    act_dict['output'] = entry.get('rc', default=-1)
                    self.logger.debug("Adding action %s" % name)
                    self.actions(_entry_get_or_create(ActionEntry, act_dict))
                elif entry_type == 'Package':
                    act_dict['target_version'] = entry.get('version', default='')
                    act_dict['current_version'] = entry.get('current_version', default='')

                    pkgs = []
                    # extra entries are a bit different.  They can have Instance objects
                    if not act_dict['target_version']:
                        for instance in entry.findall("Instance"):
                            #TODO - this probably only works for rpms
                            release = instance.get('release', '')
                            arch = instance.get('arch', '')
                            act_dict['current_version'] = instance.get('version')
                            if release:
                                act_dict['current_version'] += "-" + release
                            if arch:
                                act_dict['current_version'] += "." + arch
                            self.logger.debug("Adding package %s %s" % (name, act_dict['current_version']))
                            pkgs.append(_entry_get_or_create(PackageEntry, act_dict))
                    else:

                        self.logger.debug("Adding package %s %s" % (name, act_dict['target_version']))

                        # not implemented yet
                        act_dict['verification_details'] = entry.get('verification_details', '')
                        pkgs.append(_entry_get_or_create(PackageEntry, act_dict))
                    for pkg in pkgs:
                        inter.packages.add(pkg)

                elif entry_type == 'Path':
                    path_type = entry.get("type").lower()
                    act_dict['path_type'] = path_type
    
                    target_dict = dict(
                        owner=entry.get('owner', default="root"),
                        group=entry.get('group', default="root"),
                        perms=entry.get('perms', default=""),
                    )
                    fperm, created = FilePerms.objects.get_or_create(**target_dict)
                    act_dict['target_perms'] = fperm

                    current_dict = dict(
                        owner=entry.get('current_owner', default=""),
                        group=entry.get('current_group', default=""),
                        perms=entry.get('current_perms', default=""),
                    )
                    fperm, created = FilePerms.objects.get_or_create(**current_dict)
                    act_dict['current_perms'] = fperm

                    if path_type in ('symlink', 'hardlink'):
                        act_dict['target_path'] = entry.get('to', default="")
                        act_dict['current_path'] = entry.get('current_to', default="")
                        self.logger.debug("Adding link %s" % name)
                        inter.paths.add(_entry_get_or_create(LinkEntry, act_dict))
                        continue
                    elif path_type == 'device':
                        #TODO devices
                        self.logger.warn("device path types are not supported yet")
                        continue

                    # TODO - vcs output
                    act_dict['detail_type'] = PathEntry.DETAIL_UNUSED
                    if path_type == 'directory' and entry.get('prune', 'false') == 'true':
                        unpruned_elist = [e.get('path') for e in entry.findall('Prune')]
                        if unpruned_elist:
                            act_dict['detail_type'] = PathEntry.DETAIL_PRUNED
                            act_dict['details'] = "\n".join(unpruned_elist)
                    elif entry.get('sensitive', 'false').lower() == 'true':
                        act_dict['detail_type'] = PathEntry.DETAIL_SENSITIVE
                    else:
                        cdata = None
                        if entry.get('current_bfile', None):
                            act_dict['detail_type'] = PathEntry.DETAIL_BINARY
                            cdata = entry.get('current_bfile')
                        elif entry.get('current_bdiff', None):
                            act_dict['detail_type'] = PathEntry.DETAIL_DIFF
                            cdata = b64decode(entry.get('current_bdiff'))
                        elif entry.get('current_diff', None):
                            act_dict['detail_type'] = PathEntry.DETAIL_DIFF
                            cdata = entry.get('current_bdiff')
                        if cdata:
                            if len(cdata) > self.size_limit:
                                act_dict['detail_type'] = PathEntry.DETAIL_SIZE_LIMIT
                                act_dict['details'] = md5(cdata).hexdigest()
                            else:
                                act_dict['details'] = cdata
                    self.logger.debug("Adding path %s" % name)
                    inter.paths.add(_entry_get_or_create(PathEntry, act_dict))


                    #TODO - secontext
                    #TODO - acls
    
                elif entry_type == 'Service':
                    act_dict['target_status'] = entry.get('status', default='')
                    act_dict['current_status'] = entry.get('current_status', default='')
                    self.logger.debug("Adding service %s" % name)
                    inter.services.add(_entry_get_or_create(ServiceEntry, act_dict))
                elif entry_type == 'SELinux':
                    self.logger.info("SELinux not implemented yet")
                else:
                    self.logger.error("Unknown type %s not handled by reporting yet" % entry_type)

            
    def import_interaction(self, interaction):
        """Import the data into the backend"""

        try:
            self._import_interaction(interaction)
        except:
            self.logger.error("Failed to import interaction: %s" %
                    traceback.format_exc().splitlines()[-1])


    def validate(self):
        """Validate backend storage.  Should be called once when loaded"""

        Bcfg2.settings.read_config(repo=self.setup['repo'])

        # verify our database schema
        try:
            from Bcfg2.Server.SchemaUpdater import update_database, UpdaterError
            try:
                update_database()
            except UpdaterError:
                self.logger.error("Failed to update database schema: %s" % \
                    traceback.format_exc().splitlines()[-1])
                raise StorageError
        except StorageError:
            raise
        except Exception:
            self.logger.error("Failed to update database schema: %s" % \
                traceback.format_exc().splitlines()[-1])
            raise StorageError

        #Ensure our setup happens before these are imported
        from Bcfg2.Server.Reports.importscript import load_stat
        from Bcfg2.Server.Plugins.Metadata import ClientMetadata
        self._load_stat = load_stat
        self._ClientMetadata = ClientMetadata

    def GetExtra(self, client):
        """Fetch extra entries for a client"""
        try:
            c_inst = Client.objects.get(name=client)
            return [(a.entry.kind, a.entry.name) for a in
                    c_inst.current_interaction.extra()]
        except ObjectDoesNotExist:
            return []
        except MultipleObjectsReturned:
            self.logger.error("%s Inconsistency: Multiple entries for %s." %
                (self.__class__.__name__, client))
            return []

    def GetCurrentEntry(self, client, e_type, e_name):
        """"GetCurrentEntry: Used by PullSource"""
        try:
            c_inst = Client.objects.get(name=client)
        except ObjectDoesNotExist:
            self.logger.error("Unknown client: %s" % client)
            raise Bcfg2.Server.Plugin.PluginExecutionError
        except MultipleObjectsReturned:
            self.logger.error("%s Inconsistency: Multiple entries for %s." %
                (self.__class__.__name__, client))
            raise Bcfg2.Server.Plugin.PluginExecutionError
        result = c_inst.current_interaction.bad().filter(entry__kind=e_type,
                                                         entry__name=e_name)
        if not result:
            raise Bcfg2.Server.Plugin.PluginExecutionError
        entry = result[0]
        ret = []
        data = ('owner', 'group', 'perms')
        for t in data:
            if getattr(entry.reason, "current_%s" % t) == '':
                ret.append(getattr(entry.reason, t))
            else:
                ret.append(getattr(entry.reason, "current_%s" % t))
        if entry.reason.is_sensitive:
            raise Bcfg2.Server.Plugin.PluginExecutionError
        elif len(entry.reason.unpruned) != 0:
            ret.append('\n'.join(entry.reason.unpruned))
        elif entry.reason.current_diff != '':
            if entry.reason.is_binary:
                ret.append(b64decode(entry.reason.current_diff))
            else:
                ret.append('\n'.join(difflib.restore(\
                    entry.reason.current_diff.split('\n'), 1)))
        elif entry.reason.is_binary:
            # If len is zero the object was too large to store
            raise Bcfg2.Server.Plugin.PluginExecutionError
        else:
            ret.append(None)
        return ret

