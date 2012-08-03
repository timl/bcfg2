import os
import sys
import tempfile
from Bcfg2.Client.POSIX import POSIXTool

# py3k compatibility
if sys.hexversion >= 0x03000000:
    unicode = str

class POSIXFile(POSIXTool):
    __req__ = ['name', 'perms', 'owner', 'group']

    def fully_specified(self, entry):
        if entry.text == None and entry.get('empty', 'false') == 'false':
            return False
        return True

    def verify(self, entry, _):
        ondisk = POSIXTool.verify(self, entry)

        tbin = False
        if entry.get('encoding', 'ascii') == 'base64':
            tempdata = binascii.a2b_base64(entry.text)
            tbin = True
        elif entry.get('empty', 'false') == 'true':
            tempdata = ''
        else:
            tempdata = entry.text
            if isinstance(tempdata, unicode):
                try:
                    tempdata = tempdata.encode(self.setup['encoding'])
                except UnicodeEncodeError:
                    err = sys.exc_info()[1]
                    self.logger.error("Error encoding file %s: %s" %
                                      (entry.get('name'), err))

        different = False
        content = None
        if not ondisk:
            # first, see if the target file exists at all; if not,
            # they're clearly different
            different = True
            content = ""
        else:
            # next, see if the size of the target file is different
            # from the size of the desired content
            if len(tempdata) != ondisk[stat.ST_SIZE]:
                different = True
            else:
                # finally, read in the target file and compare them
                # directly. comparison could be done with a checksum,
                # which might be faster for big binary files, but
                # slower for everything else
                try:
                    content = open(entry.get('name')).read()
                except IOError:
                    err = sys.exc_info()[1]
                    self.logger.error("Failed to read %s: %s" %
                                      (err.filename, err))
                    return False
                different = content != tempdata

        if different:
            if self.setup['interactive']:
                prompt = [entry.get('qtext', '')]
                if not tbin and content is None:
                    # it's possible that we figured out the files are
                    # different without reading in the local file.  if
                    # the supplied version of the file is not binary,
                    # we now have to read in the local file to figure
                    # out if _it_ is binary, and either include that
                    # fact or the diff in our prompts for -I
                    try:
                        content = open(entry.get('name')).read()
                    except IOError:
                        err = sys.exc_info()[1]
                        self.logger.error("Failed to read %s: %s" %
                                          (err.filename, err))
                        return False
                if tbin or not self._is_string(content, self.setup['encoding']):
                    # don't compute diffs if the file is binary
                    prompt.append('Binary file, no printable diff')
                else:
                    diff = self._diff(content, tempdata,
                                      difflib.unified_diff,
                                      filename=entry.get("name"))
                    if diff:
                        udiff = '\n'.join(diff)
                        try:
                            prompt.append(udiff.decode(self.setup['encoding']))
                        except UnicodeDecodeError:
                            prompt.append("Binary file, no printable diff")
                    else:
                        prompt.append("Diff took too long to compute, no "
                                      "printable diff")
                entry.set("qtext", "\n".join(prompt))

            if entry.get('sensitive', 'false').lower() != 'true':
                if content is None:
                    # it's possible that we figured out the files are
                    # different without reading in the local file.  we
                    # now have to read in the local file to figure out
                    # if _it_ is binary, and either include the whole
                    # file or the diff for reports
                    try:
                        content = open(entry.get('name')).read()
                    except IOError:
                        err = sys.exc_info()[1]
                        self.logger.error("Failed to read %s: %s" %
                                          (err.filename, err))
                        return False

                if tbin or not self._is_string(content, self.setup['encoding']):
                    # don't compute diffs if the file is binary
                    entry.set('current_bfile', binascii.b2a_base64(content))
                else:
                    diff = self._diff(content, tempdata, difflib.ndiff,
                                      filename=entry.get("name"))
                    if diff:
                        entry.set("current_bdiff",
                                  binascii.b2a_base64("\n".join(diff)))
                    elif not tbin and self._is_string(content,
                                                      self.setup['encoding']):
                        entry.set('current_bfile', binascii.b2a_base64(content))

        return ondisk and not different

    def install(self, entry):
        """Install device entries."""
        if not os.path.exists(os.path.dirname(entry.get('name'))):
            try:
                os.makedirs(os.path.dirname(entry.get('name')))
            except OSError:
                err = sys.exc_info()[1]
                self.logger.error('Failed to create directory %s for %s: %s' %
                                  (os.path.dirname(entry.get('name')),
                                   entry.get('name'), err))
                return False

        self._paranoid_backup(entry)
        if entry.get('encoding', 'ascii') == 'base64':
            filedata = binascii.a2b_base64(entry.text)
        elif entry.get('empty', 'false') == 'true':
            filedata = ''
        elif isinstance(entry.text, unicode):
            filedata = entry.text.encode(self.setup['encoding'])
        else:
            filedata = entry.text
        # get a temp file to write to that is in the same directory as
        # the existing file in order to preserve any permissions
        # protections on that directory, and also to avoid issues with
        # /tmp set nosetuid while creating files that are supposed to
        # be setuid
        try:
            newfile = \
                tempfile.mkstemp(prefix=os.path.basename(entry.get("name")),
                                 dir=os.path.dirname(entry.get("name")))
        except OSError:
            err = sys.exc_info()[1]
            self.logger.error("Failed to create temp file in %s: %s" %
                              (os.path.dirname(entry.get('name')), err))
            return False
        rv = self._set_perms(entry, path=newfile)
        try:
            open(newfile, 'w').write(filedata)
        except (OSError, IOError):
            err = sys.exc_info()[1]
            self.logger.error("Failed to open temp file %s for writing %s: %s" %
                              (newfile, entry.get("name"), err))
            return False

        try:
            os.rename(newfile, entry.get('name'))
        except OSError:
            err = sys.exc_info()[1]
            self.logger.error("Failed to rename temp file %s to %s: %s" %
                              (newfile, entry.get('name'), err))
            return False

        rv = True
        if entry.get('mtime'):
            try:
                os.utime(entry.get('name'), (int(entry.get('mtime')),
                                             int(entry.get('mtime'))))
            except OSError:
                self.logger.error("Failed to set mtime of %s" % path)
                rv = False

        return POSIXTool.install(self, entry) and rv
