import re
import gzip
from Bcfg2.Server.Plugins.Packages.Collection import _Collection
from Bcfg2.Server.Plugins.Packages.Source import Source
from Bcfg2.Compat import cPickle


class AptCollection(_Collection):
    def get_config(self):
        lines = ["# This config was generated automatically by the Bcfg2 " \
                     "Packages plugin", '']

        for source in self:
            if source.rawurl:
                self.logger.info("Packages: Skipping rawurl %s" % source.rawurl)
            else:
                lines.append("deb %s %s %s" % (source.url, source.version,
                                               " ".join(source.components)))
                lines.append("")

        return "\n".join(lines)


class AptSource(Source):
    basegroups = ['apt', 'debian', 'ubuntu', 'nexenta']
    ptype = 'deb'

    def __init__(self, basepath, xsource, config):
        Source.__init__(self, basepath, xsource, config)
        self.pkgnames = set()

    def save_state(self):
        cache = open(self.cachefile, 'wb')
        cPickle.dump((self.pkgnames, self.deps, self.provides,
                      self.essentialpkgs), cache, 2)
        cache.close()

    def load_state(self):
        data = open(self.cachefile)
        (self.pkgnames, self.deps, self.provides,
         self.essentialpkgs) = cPickle.load(data)

    def filter_unknown(self, unknown):
        filtered = set([u for u in unknown if u.startswith('choice')])
        unknown.difference_update(filtered)

    def get_urls(self):
        if not self.rawurl:
            rv = []
            for part in self.components:
                for arch in self.arches:
                    rv.append("%sdists/%s/%s/binary-%s/Packages.gz" %
                              (self.url, self.version, part, arch))
            return rv
        else:
            return ["%sPackages.gz" % self.rawurl]
    urls = property(get_urls)

    def read_files(self):
        bdeps = dict()
        bprov = dict()
        depfnames = ['Depends', 'Pre-Depends']
        if self.recommended:
            depfnames.append('Recommends')
        for fname in self.files:
            if not self.rawurl:
                barch = [x
                         for x in fname.split('@')
                         if x.startswith('binary-')][0][7:]
            else:
                # RawURL entries assume that they only have one <Arch></Arch>
                # element and that it is the architecture of the source.
                barch = self.arches[0]
            if barch not in bdeps:
                bdeps[barch] = dict()
                bprov[barch] = dict()
            try:
                reader = gzip.GzipFile(fname)
            except:
                self.logger.error("Packages: Failed to read file %s" % fname)
                raise
            for line in reader.readlines():
                words = str(line.strip()).split(':', 1)
                if words[0] == 'Package':
                    pkgname = words[1].strip().rstrip()
                    self.pkgnames.add(pkgname)
                    bdeps[barch][pkgname] = []
                elif words[0] == 'Essential' and self.essential:
                    self.essentialpkgs.add(pkgname)
                elif words[0] in depfnames:
                    vindex = 0
                    for dep in words[1].split(','):
                        if '|' in dep:
                            cdeps = [re.sub('\s+', '',
                                            re.sub('\(.*\)', '', cdep))
                                     for cdep in dep.split('|')]
                            dyn_dname = "choice-%s-%s-%s" % (pkgname,
                                                             barch,
                                                             vindex)
                            vindex += 1
                            bdeps[barch][pkgname].append(dyn_dname)
                            bprov[barch][dyn_dname] = set(cdeps)
                        else:
                            raw_dep = re.sub('\(.*\)', '', dep)
                            raw_dep = raw_dep.rstrip().strip()
                            bdeps[barch][pkgname].append(raw_dep)
                elif words[0] == 'Provides':
                    for pkg in words[1].split(','):
                        dname = pkg.rstrip().strip()
                        if dname not in bprov[barch]:
                            bprov[barch][dname] = set()
                        bprov[barch][dname].add(pkgname)

        self.deps['global'] = dict()
        self.provides['global'] = dict()
        for barch in bdeps:
            self.deps[barch] = dict()
            self.provides[barch] = dict()
        for pkgname in self.pkgnames:
            pset = set()
            for barch in bdeps:
                if pkgname not in bdeps[barch]:
                    bdeps[barch][pkgname] = []
                pset.add(tuple(bdeps[barch][pkgname]))
            if len(pset) == 1:
                self.deps['global'][pkgname] = pset.pop()
            else:
                for barch in bdeps:
                    self.deps[barch][pkgname] = bdeps[barch][pkgname]
        provided = set()
        for bprovided in list(bprov.values()):
            provided.update(set(bprovided))
        for prov in provided:
            prset = set()
            for barch in bprov:
                if prov not in bprov[barch]:
                    continue
                prset.add(tuple(bprov[barch].get(prov, ())))
            if len(prset) == 1:
                self.provides['global'][prov] = prset.pop()
            else:
                for barch in bprov:
                    self.provides[barch][prov] = bprov[barch].get(prov, ())
        self.save_state()

    def is_package(self, _, pkg):
        return (pkg in self.pkgnames and
                pkg not in self.blacklist and
                (len(self.whitelist) == 0 or pkg in self.whitelist))
