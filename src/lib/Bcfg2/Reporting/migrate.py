import logging
import Bcfg2.Logger
from django.db import transaction

from Bcfg2.Server.Reports.reports.models import Interaction, \
    FilePerms, ActionEntry, PackageEntry, PathEntry, LinkEntry, \
    DeviceEntry, ServiceEntry
from Bcfg2.Server.Reports.reports.models_legacy import Reason, \
    Entries, Entries_interactions

logger = logging.getLogger(__name__)

@transaction.commit_on_success
def _migrate_transaction(inter, entries):
    """helper"""

    logger.debug("Migrating interaction %s for %s" % 
        (inter.id, inter.client.name))

    updates = dict(paths=[], packages=[], actions=[], services=[])
    for ei in Entries_interactions.objects.select_related('reason')\
            .filter(interaction=inter):
        ent = entries[ei.entry_id]
        name = ent.name
        act_dict = dict(name=name, exists=ei.reason.current_exists,
            state=ei.type)

        if ent.kind == 'Action':
            act_dict['status'] = ei.reason.status
            if not act_dict['status']:
                act_dict['status'] = "check"
            act_dict['output'] = -1
            logger.debug("Adding action %s" % name)
            updates['actions'].append(ActionEntry.entry_get_or_create(act_dict))

        elif ent.kind == 'Package':
            act_dict['target_version'] = ei.reason.version
            act_dict['current_version'] = ei.reason.current_version
            logger.debug("Adding package %s %s" % 
                (name, act_dict['target_version']))
            updates['packages'].append(PackageEntry.entry_get_or_create(act_dict))
        elif ent.kind == 'Path':
            # these might be hard.. they aren't one to one with the old model
            act_dict['path_type'] = 'file'

            target_dict = dict(
                owner=ei.reason.owner,
                group=ei.reason.group,
                perms=ei.reason.perms
            )
            fperm, created = FilePerms.objects.get_or_create(**target_dict)
            act_dict['target_perms'] = fperm

            current_dict = dict(
                owner=ei.reason.current_owner,
                group=ei.reason.current_group,
                perms=ei.reason.current_perms
            )
            fperm, created = FilePerms.objects.get_or_create(**current_dict)
            act_dict['current_perms'] = fperm

            if ei.reason.to:
                act_dict['path_type'] = 'symlink'
                act_dict['target_path'] = ei.reason.to
                act_dict['current_path'] = ei.reason.current_to
                logger.debug("Adding link %s" % name)
                updates['paths'].append(LinkEntry.entry_get_or_create(act_dict))
                continue

            act_dict['detail_type'] = PathEntry.DETAIL_UNUSED
            if ei.reason.unpruned:
                # this is the only other case we know what the type really is
                act_dict['path_type'] = 'directory'
                act_dict['detail_type'] = PathEntry.DETAIL_PRUNED
                act_dict['details'] = ei.reason.unpruned

            
            if ei.reason.is_sensitive:
                act_dict['detail_type'] = PathEntry.DETAIL_SENSITIVE
            elif ei.reason.is_binary:
                act_dict['detail_type'] = PathEntry.DETAIL_BINARY
                act_dict['details'] = ei.reason.current_diff
            elif ei.reason.current_diff:
                act_dict['detail_type'] = PathEntry.DETAIL_DIFF
                act_dict['details'] = ei.reason.current_diff
            logger.debug("Adding path %s" % name)
            updates['paths'].append(PathEntry.entry_get_or_create(act_dict))

        elif ent.kind == 'Service':
            act_dict['target_status'] = ei.reason.status
            act_dict['current_status'] = ei.reason.current_status
            logger.debug("Adding service %s" % name)
            updates['services'].append(ServiceEntry.entry_get_or_create(act_dict))
        else:
            logger.warn("Skipping type %s" % ent.kind)

    for entry_type in updates.keys():
        getattr(inter, entry_type).add(*updates[entry_type])

def _restructure():
    """major restructure of reporting data"""

    try:
        entries = {}
        for ent in Entries.objects.all():
            entries[ent.id] = ent
    except:
        logger.error("Failed to populate entries dict", exc_info=1)
        return False

    failures = []
    for inter in Interaction.objects.all():
        try:
            _migrate_transaction(inter, entries)
        except:
            logger.error("Failed to migrate interaction %s for %s" %
                (inter.id, inter.client.name), exc_info=1)
            failures.append(inter.id)
    if not failures:
        logger.info("Successfully restructured reason data")
        return True


if __name__ == '__main__':
    Bcfg2.Logger.setup_logging('bcfg2-report-collector',
                                   to_console=logging.INFO,
                                   level=logging.INFO)
    _restructure()

