"""Django models for Bcfg2 reports."""
import sys

from django.core.exceptions import ImproperlyConfigured
try:
    from django.db import models
except ImproperlyConfigured:
    e = sys.exc_info()[1]
    print("Reports: unable to import django models: %s" % e)
    sys.exit(1)

from django.core.cache import cache
from datetime import datetime, timedelta

try:
    import cPickle as pickle
except:
    import pickle

KIND_CHOICES = (
    #These are the kinds of config elements
    ('Package', 'Package'),
    ('Path', 'directory'),
    ('Path', 'file'),
    ('Path', 'permissions'),
    ('Path', 'symlink'),
    ('Service', 'Service'),
)
TYPE_GOOD = 0
TYPE_BAD = 1
TYPE_MODIFIED = 2
TYPE_EXTRA = 3

TYPE_CHOICES = (
    (TYPE_GOOD, 'Good'),
    (TYPE_BAD, 'Bad'),
    (TYPE_MODIFIED, 'Modified'),
    (TYPE_EXTRA, 'Extra'),
)


def convert_entry_type_to_id(type_name):
    """Convert a entry type to its entry id"""
    for e_id, e_name in TYPE_CHOICES:
        if e_name.lower() == type_name.lower():
            return e_id
    return -1


def hash_entry(entry_dict):
    """
    Build a key for this based on its data

    entry_dict = a dict of all the data identifying this
    """
    dataset = []
    for key in sorted(entry_dict.keys()):
        if key in ('id', 'hash_key') or key.startswith('_'):
           continue
        dataset.append( (key, entry_dict[key]) )
    return hash(pickle.dumps(dataset))


class Client(models.Model):
    """Object representing every client we have seen stats for."""
    creation = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=128,)
    current_interaction = models.ForeignKey('Interaction',
                                            null=True, blank=True,
                                            related_name="parent_client")
    expiration = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.name


class Interaction(models.Model):
    """Models each reconfiguration operation interaction between client and server."""
    client = models.ForeignKey(Client, related_name="interactions")
    timestamp = models.DateTimeField(db_index=True)  # Timestamp for this record
    state = models.CharField(max_length=32)  # good/bad/modified/etc
    repo_rev_code = models.CharField(max_length=64)  # repo revision at time of interaction
    server = models.CharField(max_length=256)  # Name of the server used for the interaction
    good_count = models.IntegerField()  # of good config-items
    total_count = models.IntegerField()  # of total config-items
    bad_count = models.IntegerField(default=0)
    modified_count = models.IntegerField(default=0)
    extra_count = models.IntegerField(default=0)

    actions = models.ManyToManyField("ActionEntry")
    packages = models.ManyToManyField("PackageEntry")
    paths = models.ManyToManyField("PathEntry")
    services = models.ManyToManyField("ServiceEntry")
    failures = models.ManyToManyField("FailureEntry")

    def __str__(self):
        return "With " + self.client.name + " @ " + self.timestamp.isoformat()

    def percentgood(self):
        if not self.totalcount == 0:
            return (self.goodcount / float(self.totalcount)) * 100
        else:
            return 0

    def percentbad(self):
        if not self.totalcount == 0:
            return ((self.totalcount - self.goodcount) / (float(self.totalcount))) * 100
        else:
            return 0

    def isclean(self):
        if (self.bad_entries == 0 and self.goodcount == self.totalcount):
            return True
        else:
            return False

    def isstale(self):
        if (self == self.client.current_interaction):  # Is Mostrecent
            if(datetime.now() - self.timestamp > timedelta(hours=25)):
                return True
            else:
                return False
        else:
            #Search for subsequent Interaction for this client
            #Check if it happened more than 25 hrs ago.
            if (self.client.interactions.filter(timestamp__gt=self.timestamp)
                    .order_by('timestamp')[0].timestamp -
                    self.timestamp > timedelta(hours=25)):
                return True
            else:
                return False

    def save(self):
        super(Interaction, self).save()  # call the real save...
        self.client.current_interaction = self.client.interactions.latest()
        self.client.save()  # save again post update

    def delete(self):
        '''Override the default delete.  Allows us to remove Performance items'''
        pitems = list(self.performance_items.all())
        super(Interaction, self).delete()
        for perf in pitems:
            if perf.interaction.count() == 0:
                perf.delete()

    def badcount(self):
        return self.totalcount - self.goodcount

    def bad(self):
        return []
        #return Entries_interactions.objects.select_related().filter(interaction=self, type=TYPE_BAD)

    def modified(self):
        return []
        #return Entries_interactions.objects.select_related().filter(interaction=self, type=TYPE_MODIFIED)

    def extra(self):
        return []
        #return Entries_interactions.objects.select_related().filter(interaction=self, type=TYPE_EXTRA)

    class Meta:
        get_latest_by = 'timestamp'
        ordering = ['-timestamp']
        unique_together = ("client", "timestamp")


class Performance(models.Model):
    """Object representing performance data for any interaction."""
    interaction = models.ManyToManyField(Interaction, related_name="performance_items")
    metric = models.CharField(max_length=128)
    value = models.DecimalField(max_digits=32, decimal_places=16)

    def __str__(self):
        return self.metric


class Group(models.Model):
    """
    Groups extracted from interactions

    name - The group name

    TODO - Most of this is for future use
    TODO - set a default group
    """

    name = models.CharField(max_length=255, unique=True)
    profile = models.BooleanField(default=False)
    public = models.BooleanField(default=False)
    category = models.CharField(max_length=1024, blank=True)
    comment = models.TextField(blank=True)

    groups = models.ManyToManyField("self", symmetrical=False)
    bundles = models.ManyToManyField("Bundle")

    def __unicode__(self):
        return self.name


class Bundle(models.Model):
    """
    Bundles extracted from interactions

    name - The bundle name
    """

    name = models.CharField(max_length=255, unique=True)

    def __unicode__(self):
        return self.name


class InteractionMetadata(models.Model):
    """
    InteractionMetadata

    Hold extra data associated with the client and interaction
    """

    interaction = models.OneToOneField(Interaction, primary_key=True, related_name='metadata')
    profile = models.ForeignKey(Group, related_name="+")
    groups = models.ManyToManyField(Group)
    bundles = models.ManyToManyField(Bundle)


# new interaction models
class FilePerms(models.Model):
    owner = models.CharField(max_length=128)
    group = models.CharField(max_length=128)
    perms = models.CharField(max_length=128)

    class Meta:
        unique_together = ('owner', 'group', 'perms')


class FileAcl(models.Model):
    """Placeholder"""
    name = models.CharField(max_length=128, db_index=True)


class BaseEntry(models.Model):
    """ Abstract base for all entry types """
    name = models.CharField(max_length=128, db_index=True)
    hash_key = models.IntegerField(editable=False, db_index=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if 'hash_key' in kwargs:
            self.hash_key = kwargs['hash_key']
            del kwargs['hash_key']
        else:
            self.hash_key = hash_entry(self.__dict__)
        super(BaseEntry, self).save(*args, **kwargs)


    def short_list(self):
        """todo"""
        return []


    @classmethod
    def entry_get_or_create(cls, act_dict):
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


class SuccessEntry(BaseEntry):
    """Base for successful entries"""
    state = models.IntegerField(choices=TYPE_CHOICES)
    exists = models.BooleanField(default=True)

    class Meta:
        abstract = True


class FailureEntry(BaseEntry):
    """Represents objects that failed to bind"""
    entry_type = models.CharField(max_length=128, db_index=True)
    message = models.TextField()


class ActionEntry(SuccessEntry):
    """ The new model for package information """
    status = models.CharField(max_length=128, default="check")
    output = models.IntegerField(default=0)

    #TODO - prune


class PackageEntry(SuccessEntry):
    """ The new model for package information """

    # if this is an extra entry trget_version will be empty
    target_version = models.CharField(max_length=1024, default='')
    current_version = models.CharField(max_length=1024)
    verification_details = models.TextField(default="")

    #TODO - prune


class PathEntry(SuccessEntry):
    """reason why modified or bad entry did not verify, or changed."""

    PATH_TYPES = (
        ("device", "Device"),
        ("directory", "Directory"),
        ("hardlink", "Hard Link"),
        ("nonexistent", "Non Existent"),
        ("permissions", "Permissions"),
        ("symlink", "Symlink"),
    )

    DETAIL_UNUSED = 0
    DETAIL_DIFF = 1
    DETAIL_BINARY = 2
    DETAIL_SENSITIVE = 3
    DETAIL_SIZE_LIMIT = 4
    DETAIL_VCS = 5
    DETAIL_PRUNED = 6

    DETAIL_CHOICES = (
        (DETAIL_UNUSED, 'Unused'),
        (DETAIL_DIFF, 'Diff'),
        (DETAIL_BINARY, 'Binary'),
        (DETAIL_SENSITIVE, 'Sensitive'),
        (DETAIL_SIZE_LIMIT, 'Size limit exceeded'),
        (DETAIL_VCS, 'VCS output'),
        (DETAIL_PRUNED, 'Pruned paths'),
    )

    path_type = models.CharField(max_length=128, choices=PATH_TYPES)

    target_perms = models.ForeignKey(FilePerms, related_name="+")
    current_perms = models.ForeignKey(FilePerms, related_name="+")

    acls = models.ManyToManyField(FileAcl)

    detail_type = models.IntegerField(default=0,
        choices=DETAIL_CHOICES)
    details = models.TextField(default='')


class LinkEntry(PathEntry):
    """Sym/Hard Link types"""
    target_path = models.CharField(max_length=1024, blank=True)
    current_path = models.CharField(max_length=1024, blank=True)


class DeviceEntry(PathEntry):
    """Device types.  Best I can tell the client driver needs work here"""
    DEVICE_TYPES = (
        ("block", "Block"),
        ("char", "Char"),
        ("fifo", "Fifo"),
    )

    device_type = models.CharField(max_length=16, choices=DEVICE_TYPES)

    target_major = models.IntegerField()
    target_minor = models.IntegerField()
    current_major = models.IntegerField()
    current_minor = models.IntegerField()


class ServiceEntry(SuccessEntry):
    """ The new model for package information """
    target_status = models.CharField(max_length=128, default='')
    current_status = models.CharField(max_length=128, default='')

    #TODO - prune


class Performance(models.Model):
    """Object representing performance data for any interaction."""
    interaction = models.ForeignKey(Interaction, related_name='performance_items')

    metric = models.CharField(max_length=128)
    value = models.DecimalField(max_digits=32, decimal_places=16)

    def __str__(self):
        return self.metric

