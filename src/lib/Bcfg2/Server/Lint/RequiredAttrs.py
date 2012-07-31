import os
import re
import lxml.etree
import Bcfg2.Server.Lint
import Bcfg2.Client.Tools.POSIX
import Bcfg2.Client.Tools.VCS
from Bcfg2.Server.Plugins.Packages import Apt, Yum
from Bcfg2.Server.Plugins.Bundler import have_genshi
if have_genshi:
    from Bcfg2.Server.Plugins.SGenshi import SGenshiTemplateFile

# format verifying functions
def is_filename(val):
    return val.startswith("/") and len(val) > 1

def is_selinux_type(val):
    return re.match(r'^[a-z_]+_t', val)

def is_selinux_user(val):
    return re.match(r'^[a-z_]+_u', val)

def is_octal_mode(val):
    return re.match(r'[0-7]{3,4}', val)

def is_username(val):
    return re.match(r'^([a-z]\w{0,30}|\d+)$', val)

def is_device_mode(val):
    try:
        # checking upper bound seems like a good way to discover some
        # obscure OS with >8-bit device numbers
        return int(val) > 0
    except:
        return False

class RequiredAttrs(Bcfg2.Server.Lint.ServerPlugin):
    """ verify attributes for configuration entries (as defined in
    doc/server/configurationentries) """
    def __init__(self, *args, **kwargs):
        Bcfg2.Server.Lint.ServerPlugin.__init__(self, *args, **kwargs)
        self.required_attrs = dict(
            Path=dict(
                device=dict(name=is_filename, owner=is_username,
                            group=is_username,
                            dev_type=lambda v: \
                                v in Bcfg2.Client.Tools.POSIX.device_map),
                directory=dict(name=is_filename, owner=is_username,
                               group=is_username, perms=is_octal_mode),
                file=dict(name=is_filename, owner=is_username,
                          group=is_username, perms=is_octal_mode,
                          __text__=None),
                hardlink=dict(name=is_filename, to=is_filename),
                symlink=dict(name=is_filename, to=is_filename),
                ignore=dict(name=is_filename),
                nonexistent=dict(name=is_filename),
                permissions=dict(name=is_filename, owner=is_username,
                                 group=is_username, perms=is_octal_mode),
                vcs=dict(vcstype=lambda v: (v != 'Path' and
                                            hasattr(Bcfg2.Client.Tools.VCS,
                                                    "Install%s" % v)),
                         revision=None, sourceurl=None)),
            Service={
                "chkconfig": dict(name=None),
                "deb": dict(name=None),
                "rc-update": dict(name=None),
                "smf": dict(name=None, FMRI=None),
                "upstart": dict(name=None)},
            Action={None: dict(name=None,
                               timing=lambda v: v in ['pre', 'post', 'both'],
                               when=lambda v: v in ['modified', 'always'],
                               status=lambda v: v in ['ignore', 'check'],
                               command=None)},
            ACL=dict(
                default=dict(scope=lambda v: v in ['user', 'group'],
                             perms=lambda v: re.match('^([0-7]|[rwx\-]{0,3}',
                                                      v)),
                access=dict(scope=lambda v: v in ['user', 'group'],
                            perms=lambda v: re.match('^([0-7]|[rwx\-]{0,3}',
                                                     v)),
                mask=dict(perms=lambda v: re.match('^([0-7]|[rwx\-]{0,3}', v))),
            Package={None: dict(name=None)},
            SELinux=dict(
                boolean=dict(name=None,
                             value=lambda v: v in ['on', 'off']),
                module=dict(name=None, __text__=None),
                port=dict(name=lambda v: re.match(r'^\d+(-\d+)?/(tcp|udp)', v),
                          selinuxtype=is_selinux_type),
                fcontext=dict(name=None, selinuxtype=is_selinux_type),
                node=dict(name=lambda v: "/" in v,
                          selinuxtype=is_selinux_type,
                          proto=lambda v: v in ['ipv6', 'ipv4']),
                login=dict(name=is_username,
                           selinuxuser=is_selinux_user),
                user=dict(name=is_selinux_user,
                          roles=lambda v: all(is_selinux_user(u)
                                              for u in " ".split(v)),
                          prefix=None),
                interface=dict(name=None, selinuxtype=is_selinux_type),
                permissive=dict(name=is_selinux_type))
            )

    def Run(self):
        self.check_packages()
        if "Defaults" in self.core.plugins:
            self.logger.info("Defaults plugin enabled; skipping required "
                             "attribute checks")
        else:
            self.check_rules()
            self.check_bundles()

    @classmethod
    def Errors(cls):
        return {"unknown-entry-type":"error",
                "unknown-entry-tag":"error",
                "required-attrs-missing":"error",
                "required-attr-format":"error",
                "extra-attrs":"warning"}

    def check_packages(self):
        """ check package sources for Source entries with missing attrs """
        if 'Packages' in self.core.plugins:
            for source in self.core.plugins['Packages'].sources:
                if isinstance(source, Yum.YumSource):
                    if (not source.pulp_id and not source.url and
                        not source.rawurl):
                        self.LintError("required-attrs-missing",
                                       "A %s source must have either a url, "
                                       "rawurl, or pulp_id attribute: %s" %
                                       (source.ptype,
                                        self.RenderXML(source.xsource)))
                elif not source.url and not source.rawurl:
                    self.LintError("required-attrs-missing",
                                   "A %s source must have either a url or "
                                   "rawurl attribute: %s" %
                                   (source.ptype,
                                    self.RenderXML(source.xsource)))

                if (not isinstance(source, Apt.AptSource) and
                    source.recommended):
                    self.LintError("extra-attrs",
                                   "The recommended attribute is not "
                                   "supported on %s sources: %s" %
                                   (source.ptype,
                                    self.RenderXML(source.xsource)))

    def check_rules(self):
        """ check Rules for Path entries with missing attrs """
        if 'Rules' in self.core.plugins:
            for rules in self.core.plugins['Rules'].entries.values():
                xdata = rules.pnode.data
                for path in xdata.xpath("//Path"):
                    self.check_entry(path, os.path.join(self.config['repo'],
                                                        rules.name))

    def check_bundles(self):
        """ check bundles for BoundPath entries with missing attrs """
        if 'Bundler' in self.core.plugins:
            for bundle in self.core.plugins['Bundler'].entries.values():
                if (self.HandlesFile(bundle.name) and
                    (not have_genshi or
                     not isinstance(bundle, SGenshiTemplateFile))):
                    try:
                        xdata = lxml.etree.XML(bundle.data)
                    except (lxml.etree.XMLSyntaxError, AttributeError):
                        xdata = \
                            lxml.etree.parse(bundle.template.filepath).getroot()

                    for path in xdata.xpath("//*[substring(name(), 1, 5) = 'Bound']"):
                        self.check_entry(path, bundle.name)

    def check_entry(self, entry, filename):
        """ generic entry check """
        if self.HandlesFile(filename):
            name = entry.get('name')
            tag = entry.tag
            if tag.startswith("Bound"):
                tag = tag[5:]
            if tag not in self.required_attrs:
                self.LintError("unknown-entry-tag",
                               "Unknown entry tag '%s': %s" %
                               (tag, self.RenderXML(entry)))

            if isinstance(self.required_attrs[tag], dict):
                etype = entry.get('type')
                if etype in self.required_attrs[tag]:
                    required_attrs = self.required_attrs[tag][etype] 
                else:
                    self.LintError("unknown-entry-type",
                                   "Unknown %s type %s: %s" %
                                   (tag, etype, self.RenderXML(entry)))
                    return
            else:
                required_attrs = self.required_attrs[tag]
            attrs = set(entry.attrib.keys())

            if 'dev_type' in required_attrs:
                dev_type = entry.get('dev_type')
                if dev_type in ['block', 'char']:
                    # check if major/minor are specified
                    required_attrs['major'] = is_device_mode
                    required_attrs['minor'] = is_device_mode

            if tag == 'ACL' and 'scope' in required_attrs:
                required_attrs[entry.get('scope')] = is_username

            if '__text__' in required_attrs:
                del required_attrs['__text__']
                if (not entry.text and
                    not entry.get('empty', 'false').lower() == 'true'):
                    self.LintError("required-attrs-missing",
                                   "Text missing for %s %s in %s: %s" %
                                   (tag, name, filename,
                                    self.RenderXML(entry)))

            if not attrs.issuperset(required_attrs.keys()):
                self.LintError("required-attrs-missing",
                               "The following required attribute(s) are "
                               "missing for %s %s in %s: %s\n%s" %
                               (tag, name, filename,
                                ", ".join([attr
                                           for attr in
                                           set(required_attrs.keys()).difference(attrs)]),
                                self.RenderXML(entry)))

            for attr, fmt in required_attrs.items():
                if fmt and attr in attrs and not fmt(entry.attrib[attr]):
                    self.LintError("required-attr-format",
                                   "The %s attribute of %s %s in %s is "
                                   "malformed\n%s" %
                                   (attr, tag, name, filename,
                                    self.RenderXML(entry)))
                    
