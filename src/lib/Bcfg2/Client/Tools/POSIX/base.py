import os
import sys
import pwd
import grp
import stat
import time
import shutil
from datetime import datetime
import Bcfg2.Client.Tools

try:
    import selinux
    has_selinux = True
except ImportError:
    has_selinux = False

try:
    import posix1e
    has_acls = True
except ImportError:
    has_acls = False

# map between dev_type attribute and stat constants
device_map = dict(block=stat.S_IFBLK,
                  char=stat.S_IFCHR,
                  fifo=stat.S_IFIFO)

# map between permissions characters and numeric ACL constants
acl_map = dict(r=posix1e.ACL_READ,
               w=posix1e.ACL_WRITE,
               x=posix1e.ACL_EXECUTE)

class POSIXTool(Bcfg2.Client.Tools.Tool):
    def fully_specified(self, entry):
        # checking is done by __req__
        return True

    def gather_data(self, entry):
        try:
            ondisk = os.stat(entry.get('name'))
        except OSError:
            entry.set('current_exists', 'false')
            self.logger.debug("POSIX: %s %s does not exist" %
                              (entry.tag, entry.get('name')))
            return False

        try:
            entry.set('current_owner', str(ondisk[stat.ST_UID]))
            entry.set('current_group', str(ondisk[stat.ST_GID]))
        except (OSError, KeyError):
            err = sys.exc_info()[1]
            self.logger.debug("POSIX: Could not get current owner or group of "
                              "%s: %s" % (entry.get("name"), err))

        try:
            entry.set('perms', str(oct(ondisk[stat.ST_MODE])[-4:]))
        except (OSError, KeyError):
            err = sys.exc_info()[1]
            self.logger.debug("POSIX: Could not get current permissions of %s: "
                              "%s" % (entry.get("name"), err))

        if has_selinux:
            try:
                entry.set('current_secontext',
                          selinux.getfilecon(entry.get('name'))[1])
            except (OSError, KeyError):
                err = sys.exc_info()[1]
                self.logger.debug("POSIX: Could not get current SELinux "
                                  "context of %s: %s" % (entry.get("name"),
                                                         err))

        if has_acls:
            for aclkey, perms in self._list_file_acls(entry):
                atype, scope, qual = aclkey
                aclentry = lxml.etree.Element("ACL", type=atype,
                                              perms=perms)
                if scope == posix1e.ACL_USER:
                    aclentry.set("scope", "user")
                elif scope == posix1e.ACL_GROUP:
                    aclentry.set("scope", "group")
                else:
                    self.logger.debug("POSIX: Unknown ACL scope %s on %s" %
                                      (scope, entry.get("name")))
                    continue
                aclentry.set(aclentry.get("scope"), qual)
                entry.append(aclentry)


    def verify(self, entry, modlist):
        try:
            ondisk = os.stat(entry.get('name'))
        except OSError:
            entry.set('current_exists', 'false')
            self.logger.debug("POSIX: %s %s does not exist" %
                              (entry.tag, entry.get("name")))
            return False

        if not self._verify_metadata(entry):
            return False

        if entry.get('recursive', 'false').lower() == 'true':
            # verify ownership information recursively
            for root, dirs, files in os.walk(entry.get('name')):
                for p in dirs + files:
                    if not self._verify_metadata(entry,
                                                 path=os.path.join(root, p)):
                        return False

        return ondisk

    def install(self, entry):
        plist = [entry.get('name')]
        if entry.get('recursive', 'false').lower() == 'true':
            # verify ownership information recursively
            for root, dirs, files in os.walk(entry.get('name')):
                for p in dirs + files:
                    if not self._verify_metadata(entry,
                                                 path=os.path.join(root, p),
                                                 checkonly=True):
                        plist.append(path)
        rv = True
        for path in plist:
            rv &= self._set_perms(entry, path)
        return rv

    def prune_old_backups(self, entry):
        bkupnam = entry.get('name').replace('/', '_')
        # current list of backups for this file
        try:
            bkuplist = [f for f in os.listdir(self.ppath) if
                        f.startswith(bkupnam)]
        except OSError:
            err = sys.exc_info()[1]
            self.logger.error("POSIX: Failed to create backup list in %s: %s" %
                              (self.ppath, err))
        bkuplist.sort()
        while len(bkuplist) >= int(self.max_copies):
            # remove the oldest backup available
            oldest = bkuplist.pop(0)
            self.logger.info("POSIX: Removing old backup %s" % oldest)
            try:
                os.remove(os.path.join(self.ppath, oldest))
            except OSError:
                err = sys.exc_info()[1]
                self.logger.error("POSIX: Failed to remove old backup %s: %s" %
                                  os.path.join(self.ppath, oldest), err)

    def _paranoid_backup(self, entry):
        if (entry.get("paranoid", 'false').lower() == 'true' and
            self.setup.get("paranoid", False) and
            entry.get('current_exists', 'true') != 'false' and
            not os.path.isdir(entry.get("name"))):
            self._prune_old_backups(entry)
            bkupnam = "%s_%s" % (entry.get('name').replace('/', '_'),
                                 datetime.isoformat(datetime.now()))
            bfile = os.path.join(self.ppath, bkupnam)
            try:
                shutil.copy(entry.get('name'), bfile)
                self.logger.info("POSIX: Backup of %s saved to %s" %
                                 (entry.get('name'), bfile))
            except IOError:
                err = sys.exc_info()[1]
                self.logger.error("POSIX: Failed to create backup file for %s: "
                                  "%s" % (entry.get('name'), err))

    def _exists(self, entry, remove=False):
        try:
            # check for existing paths and optionally remove them
            ondisk = os.lstat(entry.get('name'))
            if remove:
                try:
                    os.unlink(entry.get('name'))
                    return False
                except OSError:
                    err = sys.exc_info()[1]
                    self.logger.warning('POSIX: Failed to unlink %s: %s' %
                                        (entry.get('name'), err))
                    return ondisk # probably still exists
            else:
                return ondisk
        except OSError:
            return False

    def _set_perms(self, entry, path=None):
        if path is None:
            path = entry.get("name")

        if (entry.get('perms') == None or
            entry.get('owner') == None or
            entry.get('group') == None):
            self.logger.error('POSIX: Entry %s not completely specified. '
                              'Try running bcfg2-lint.' % entry.get('name'))
            return False

        rv = True
        # split this into multiple try...except blocks so that even if a
        # chown fails, the chmod can succeed -- get as close to the
        # desired state as we can
        try:
            self.logger.debug("POSIX: Setting ownership of %s to %s:%s" %
                              (path,
                               self._norm_entry_uid(entry),
                               self._norm_entry_gid(entry)))
            os.chown(path, self._norm_entry_uid(entry),
                     self._norm_entry_gid(entry))
        except KeyError:
            self.logger.error('POSIX: Failed to change ownership of %s' % path)
            rv = False
            os.chown(path, 0, 0)
        except OSError:
            self.logger.error('POSIX: Failed to change ownership of %s' % path)
            rv = False

        configPerms = int(entry.get('perms'), 8)
        if entry.get('dev_type'):
            configPerms |= device_map[entry.get('dev_type')]
        try:
            self.logger.debug("POSIX: Setting permissions on %s to %s" %
                              (path, oct(configPerms)))
            os.chmod(path, configPerms)
        except (OSError, KeyError):
            self.logger.error('POSIX: Failed to change permissions mode of %s' %
                              path)
            rv = False

        recursive = entry.get("recursive", "false").lower() == "true"
        return (self._set_secontext(entry, path=path, recursive=recursive) and
                self._set_acls(entry, path=path, recursive=recursive) and
                rv)

    def _set_acls(self, entry, path=None, recursive=True):
        """ set POSIX ACLs on the file on disk according to the config """
        if not has_acls:
            if entry.findall("ACL"):
                self.logger.debug("POSIX: ACLs listed for %s but no pylibacl "
                                  "library installed" % entry.get('name'))
            return True

        if path is None:
            path = entry.get("name")

        acl = posix1e.ACL(file=path)
        # clear ACLs out so we start fresh -- way easier than trying
        # to add/remove/modify ACLs
        for aclentry in acl:
            if aclentry.tag_type in [posix1e.ACL_USER, posix1e.ACL_GROUP]:
                acl.delete_entry(aclentry)
        if os.path.isdir(path):
            defacl = posix1e.ACL(filedef=path)
            if not defacl.valid():
                # when a default ACL is queried on a directory that
                # has no default ACL entries at all, you get an empty
                # ACL, which is not valid.  in this circumstance, we
                # just copy the access ACL to get a base valid ACL
                # that we can add things to.
                defacl = posix1e.ACL(acl=acl)
            else:
                for aclentry in defacl:
                    if aclentry.tag_type in [posix1e.ACL_USER,
                                             posix1e.ACL_GROUP]:
                        defacl.delete_entry(aclentry)
        else:
            defacl = None

        for aclkey, perms in self._list_entry_acls(entry).items():
            atype, scope, qualifier = aclkey
            if atype == "default":
                if defacl is None:
                    self.logger.warning("POSIX: Cannot set default ACLs on "
                                        "non-directory %s" % path)
                    continue
                entry = posix1e.Entry(defacl)
            else:
                entry = posix1e.Entry(acl)
            for perm in acl_map.values():
                if perm & perms:
                    entry.permset.add(perm)
            entry.tag_type = scope
            try:
                if scope == posix1e.ACL_USER:
                    scopename = "user"
                    entry.qualifier = self._norm_uid(qualifier)
                elif scope == posix1e.ACL_GROUP:
                    scopename = "group"
                    entry.qualifier = self._norm_gid(qualifier)
            except (OSError, KeyError):
                err = sys.exc_info()[1]
                self.logger.error("POSIX: Could not resolve %s %s: %s" %
                                  (scopename, qualifier, err))
                continue
        acl.calc_mask()

        def _apply_acl(acl, path, atype=posix1e.ACL_TYPE_ACCESS):
            if atype == posix1e.ACL_TYPE_ACCESS:
                atype_str = "access"
            else:
                atype_str = "default"
            if acl.valid():
                self.logger.debug("POSIX: Applying %s ACL to %s:" % (atype_str,
                                                                     path))
                for line in str(acl).splitlines():
                    self.logger.debug("  " + line)
                try:
                    acl.applyto(path, atype)
                    return True
                except:
                    err = sys.exc_info()[1]
                    self.logger.error("POSIX: Failed to set ACLs on %s: %s" %
                                      (path, err))
                    return False
            else:
                self.logger.warning("POSIX: %s ACL created for %s was invalid:"
                                    % (atype_str.title(), path))
                for line in str(acl).splitlines():
                    self.logger.warning("  " + line)
                return False

        rv = _apply_acl(acl, path)
        if defacl:
            defacl.calc_mask()
            rv &= _apply_acl(defacl, path, posix1e.ACL_TYPE_DEFAULT)
        if recursive:
            for root, dirs, files in os.walk(path):
                for p in dirs + files:
                    rv &= _apply_acl(acl, p)
                    if defacl:
                        rv &= _apply_acl(defacl, p, posix1e.ACL_TYPE_DEFAULT)
        return rv

    def _set_secontext(self, entry, path=None, recursive=False):
        """ set the SELinux context of the file on disk according to the
        config"""
        if not has_selinux:
            return True

        if path is None:
            path = entry.get("name")
        context = entry.get("secontext")
        if context is None:
            # no context listed
            return True

        rv = True
        if context == '__default__':
            try:
                selinux.restorecon(path, recursive=recursive)
            except:
                err = sys.exc_info()[1]
                self.logger.error("POSIX: Failed to restore SELinux context "
                                  "for %s: %s" % (path, err))
                rv = False
        else:
            try:
                rv &= selinux.lsetfilecon(path, context) == 0
            except:
                err = sys.exc_info()[1]
                self.logger.error("POSIX: Failed to restore SELinux context "
                                  "for %s: %s" % (path, err))
                rv = False

            if recursive:
                for root, dirs, files in os.walk(path):
                    for p in dirs + files:
                        try:
                            rv &= selinux.lsetfilecon(p, context) == 0
                        except:
                            err = sys.exc_info()[1]
                            self.logger.error("POSIX: Failed to restore "
                                              "SELinux context for %s: %s" %
                                              (path, err))
                            rv = False
        return rv

    def _secontext_matches(self, entry):
        """ determine if the SELinux context of the file on disk matches
        the desired context """
        if not has_selinux:
            # no selinux libraries
            return True

        path = entry.get("path")
        context = entry.get("secontext")
        if context is None:
            # no context listed
            return True

        if context == '__default__':
            if selinux.getfilecon(entry.get('name'))[1] == \
               selinux.matchpathcon(entry.get('name'), 0)[1]:
                return True
            else:
                return False
        elif selinux.getfilecon(entry.get('name'))[1] == context:
            return True
        else:
            return False

    def _norm_gid(self, gid):
        """ This takes a group name or gid and returns the
        corresponding gid. """
        try:
            return int(gid)
        except ValueError:
            return int(grp.getgrnam(gid)[2])

    def _norm_entry_gid(self, entry):
        try:
            return self._norm_gid(entry.get('group'))
        except (OSError, KeyError):
            err = sys.exc_info()[1]
            self.logger.error('POSIX: GID normalization failed for %s on %s: %s'
                              % (entry.get('group'), entry.get('name'), err))
            return 0

    def _norm_uid(self, uid):
        """ This takes a username or uid and returns the
        corresponding uid. """
        try:
            return int(uid)
        except ValueError:
            return int(pwd.getpwnam(uid)[2])

    def _norm_entry_uid(self, entry):
        try:
            return self._norm_uid(entry.get("owner"))
        except (OSError, KeyError):
            err = sys.exc_info()[1]
            self.logger.error('POSIX: UID normalization failed for %s on %s: %s'
                              % (entry.get('owner'), entry.get('name'), err))
            return 0

    def _norm_acl_perms(self, perms):
        """ takes a representation of an ACL permset and returns a digit
        representing the permissions entailed by it.  representations can
        either be a single octal digit, a string of up to three 'r',
        'w', 'x', or '-' characters, or a posix1e.Permset object"""
        if hasattr(perms, 'test'):
            # Permset object
            return sum([p for p in acl_map.values()
                        if perms.test(p)])

        try:
            # single octal digit
            return int(perms)
        except ValueError:
            # couldn't be converted to an int; process as a string
            rv = 0
            for char in perms:
                if char == '-':
                    continue
                elif char not in acl_map:
                    self.logger.error("POSIX: Unknown permissions character in "
                                      "ACL: %s" % char)
                    return 0
                else:
                    rv |= acl_map[char]
            return rv

    def _acl2string(self, aclkey, perms):
        atype, scope, qualifier = aclkey
        acl_str = []
        if atype == 'default':
            acl_str.append(atype)
        if scope == posix1e.ACL_USER:
            acl_str.append("user")
        elif scope == posix1e.ACL_GROUP:
            acl_str.append("group")
        acl_str.append(qualifier)
        acl_str.append(self._acl_perm2string(perms))
        return ":".join(acl_str)

    def _acl_perm2string(self, perm):
        rv = []
        for char in 'rwx':
            if acl_map[char] & perm:
                rv.append(char)
            else:
                rv.append('-')
        return ''.join(rv)

    def _is_string(self, strng, encoding):
        """ Returns true if the string contains no ASCII control
        characters and can be decoded from the specified encoding. """
        for char in strng:
            if ord(char) < 9 or ord(char) > 13 and ord(char) < 32:
                return False
        try:
            strng.decode(encoding)
            return True
        except:
            return False

    def _verify_metadata(self, entry, path=None, checkonly=False):
        """ generic method to verify perms, owner, group, secontext,
        and mtime """

        # allow setting an alternate path for recursive permissions checking
        if path is None:
            path = entry.get('name')
        
        while len(entry.get('perms', '')) < 4:
            entry.set('perms', '0' + entry.get('perms', ''))

        try:
            ondisk = os.stat(path)
        except OSError:
            entry.set('current_exists', 'false')
            self.logger.debug("POSIX: %s %s does not exist" %
                              (entry.tag, path))
            return False

        try:
            owner = str(ondisk[stat.ST_UID])
            group = str(ondisk[stat.ST_GID])
        except (OSError, KeyError):
            self.logger.error('POSIX: User/Group resolution failed for path %s'
                              % path)
            owner = 'root'
            group = '0'

        perms = oct(ondisk[stat.ST_MODE])[-4:]
        if entry.get('mtime', '-1') != '-1':
            mtime = str(ondisk[stat.ST_MTIME])
        else:
            mtime = '-1'

        configOwner = str(self._norm_entry_uid(entry))
        configGroup = str(self._norm_entry_gid(entry))
        configPerms = int(entry.get('perms'), 8)
        if has_selinux:
            if entry.get("secontext") == "__default__":
                try:
                    configContext = selinux.matchpathcon(path, 0)[1]
                except OSError:
                    self.logger.warning("POSIX: Failed to get default SELinux "
                                        "context for %s; missing fcontext rule?"
                                        % path)
                    return False
            else:
                configContext = entry.get("secontext")

        errors = []
        if owner != configOwner:
            if checkonly:
                return False
            entry.set('current_owner', owner)
            errors.append("Owner for path %s is incorrect. "
                          "Current owner is %s but should be %s" %
                          (path, ondisk.st_uid, entry.get('owner')))
                        
        if group != configGroup:
            if checkonly:
                return False
            entry.set('current_group', group)
            errors.append("Group for path %s is incorrect. "
                          "Current group is %s but should be %s" %
                          (path, ondisk.st_gid, entry.get('group')))

        if oct(int(perms, 8)) != oct(configPerms):
            if checkonly:
                return False
            entry.set('current_perms', perms)
            errors.append(" Permissions for path %s are incorrect. "
                          "Current permissions are %s but should be %s" %
                          (path, perms, entry.get('perms')))

        if entry.get('mtime') and mtime != entry.get('mtime', '-1'):
            if checkonly:
                return False
            entry.set('current_mtime', mtime)
            errors.append("mtime for path %s is incorrect. "
                          "Current mtime is %s but should be %s" %
                          (path, mtime, entry.get('mtime')))

        seVerifies = self._verify_secontext(entry)
        aclVerifies = self._verify_acls(entry)

        if errors:
            for error in errors:
                self.logger.debug("POSIX: " + error)
            entry.set('qtext', "\n".join([entry.get('qtext', '')] + errors))
            return False
        else:
            return seVerifies and aclVerifies

    def _list_entry_acls(self, entry):
        wanted = dict()
        for acl in entry.findall("ACL"):
            if acl.get("scope") == "user":
                scope = posix1e.ACL_USER
            elif acl.get("scope") == "group":
                scope = posix1e.ACL_GROUP
            else:
                self.logger.error("POSIX: Unknown ACL scope %s" %
                                  acl.get("scope"))
                continue
            wanted[(acl.get("type"), scope, acl.get(acl.get("scope")))] = \
                self._norm_acl_perms(acl.get('perms'))
        return wanted

    def _list_file_acls(self, entry):
        def _process_acl(acl, atype):
            try:
                if acl.tag_type == posix1e.ACL_USER:
                    qual = pwd.getpwuid(acl.qualifier)[0]
                elif acl.tag_type == posix1e.ACL_GROUP:
                    qual = grp.getgrgid(acl.qualifier)[0]
                else:
                    return
            except (OSError, KeyError):
                err = sys.exc_info()[1]
                self.logger.error("POSIX: Lookup of %s %s failed: %s" %
                                  (scope, acl.qualifier, err))
                qual = acl.qualifier
            existing[(atype, acl.tag_type, qual)] = \
                self._norm_acl_perms(acl.permset)

        existing = dict()
        for acl in posix1e.ACL(file=entry.get("name")):
            _process_acl(acl, "access")
        if os.path.isdir(entry.get("name")):
            for acl in posix1e.ACL(filedef=entry.get("name")):
                _process_acl(acl, "default")
        return existing

    def _verify_acls(self, entry):
        if not has_acls:
            if entry.findall("ACL"):
                self.logger.debug("POSIX: ACLs listed for %s but no pylibacl "
                                  "library installed" % entry.get('name'))
            return True

        # create lists of normalized representations of the ACLs we want
        # and the ACLs we have.  this will make them easier to compare
        # than trying to mine that data out of the ACL objects and XML
        # objects and compare it at the same time.
        wanted = self._list_entry_acls(entry)
        existing = self._list_file_acls(entry)

        missing = []
        extra = []
        wrong = []
        for aclkey, perms in wanted.items():
            acl_str = self._acl2string(aclkey, perms)
            if aclkey not in existing:
                missing.append(acl_str)
            elif existing[aclkey] != perms:
                wrong.append((acl_str,
                              self._acl2string(aclkey, existing[aclkey])))

        for aclkey, perms in existing.items():
            if aclkey not in wanted:
                extra.append(self._acl2string(aclkey, perms))
        
        msg = []
        if missing:
            msg.append("%s ACLs are missing: %s" % (len(missing),
                                                    ", ".join(missing)))
        if wrong:
            msg.append("%s ACLs are wrong: %s" %
                       (len(wrong),
                        "; ".join(["%s should be %s" % (e, w)
                                   for w, e in wrong])))
        if extra:
            msg.append("%s extra ACLs: %s" % (len(extra), ", ".join(extra)))

        if msg:
            msg.insert(0,
                       "POSIX ACLs for path %s are incorrect." %
                       entry.get("name"))
            self.logger.debug(msg[0])
            for line in msg[1:]:
                self.logger.debug("  " + line)
            entry.set('qtext', "\n".join([entry.get("qtext", '')] + msg))
            return False
        return True

    def _verify_secontext(self, entry):
        if not self._secontext_matches(entry):
            path = entry.get("name")
            if entry.get("secontext") == "__default__":
                configContext = selinux.matchpathcon(path, 0)[1]
            else:
                configContext = entry.get("secontext")
            pcontext = selinux.getfilecon(path)[1]
            entry.set('current_secontext', pcontext)
            msg = ("SELinux context for path %s is incorrect. "
                   "Current context is %s but should be %s" %
                   (path, pcontext, configContext))
            self.logger.debug("POSIX: " + msg)
            entry.set('qtext', "\n".join([entry.get("qtext", ''), msg]))
            return False
        return True
            
    def _diff(self, content1, content2, difffunc, filename=None):
        rv = []
        start = time.time()
        longtime = False
        for diffline in difffunc(content1.split('\n'),
                                 content2.split('\n')):
            now = time.time()
            rv.append(diffline)
            if now - start > 5 and not longtime:
                if filename:
                    self.logger.info("POSIX: Diff of %s taking a long time" %
                                     filename)
                else:
                    self.logger.info("POSIX: Diff taking a long time")
                longtime = True
            elif now - start > 30:
                if filename:
                    self.logger.error("POSIX: Diff of %s took too long; giving "
                                      "up" % filename)
                else:
                    self.logger.error("POSIX: Diff took too long; giving up")
                return False
        return rv
