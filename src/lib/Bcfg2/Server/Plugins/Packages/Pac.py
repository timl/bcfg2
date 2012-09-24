import gzip
import tarfile
from Bcfg2.Compat import cPickle
from Bcfg2.Server.Plugins.Packages.Collection import _Collection
from Bcfg2.Server.Plugins.Packages.Source import Source


class PacCollection(_Collection):
    pass


class PacSource(Source):
    basegroups = ['arch', 'parabola']
    ptype = 'pacman'

    def __init__(self, basepath, xsource, config):
        Source.__init__(self, basepath, xsource, config)
        self.pkgnames = set()

    def save_state(self):
        cache = open(self.cachefile, 'wb')
        cPickle.dump((self.pkgnames, self.deps, self.provides),
                     cache, 2)
        cache.close()

    def load_state(self):
        data = open(self.cachefile)
        self.pkgnames, self.deps, self.provides = cPickle.load(data)

    def filter_unknown(self, unknown):
        filtered = set([u for u in unknown if u.startswith('choice')])
        unknown.difference_update(filtered)

    def get_urls(self):
        if not self.rawurl:
            rv = []
            for part in self.components:
                for arch in self.arches:
                    rv.append("%s%s/os/%s/%s.db.tar.gz" %
                              (self.url, part, arch, part))
            return rv
        else:
            raise Exception("PacSource : RAWUrl not supported (yet)")
    urls = property(get_urls)

    def read_files(self):
        bdeps = dict()
        bprov = dict()

        depfnames = ['Depends', 'Pre-Depends']
        if self.recommended:
            depfnames.append('Recommends')

        for fname in self.files:
            if not self.rawurl:
                barch = [x for x in fname.split('@') if x in self.arches][0]
            else:
                # RawURL entries assume that they only have one <Arch></Arch>
                # element and that it is the architecture of the source.
                barch = self.arches[0]

            if barch not in bdeps:
                bdeps[barch] = dict()
                bprov[barch] = dict()
            try:
                self.debug_log("Packages: try to read %s" % fname)
                tar = tarfile.open(fname, "r")
                reader = gzip.GzipFile(fname)
            except:
                self.logger.error("Packages: Failed to read file %s" % fname)
                raise

            for tarinfo in tar:
                if tarinfo.isdir():
                    self.pkgnames.add(tarinfo.name.rsplit("-", 2)[0])
                    self.debug_log("Packages: added %s" %
                                   tarinfo.name.rsplit("-", 2)[0])
            tar.close()

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
