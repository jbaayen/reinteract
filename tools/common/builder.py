import glob
import logging
import os
import shutil
import tempfile

from am_parser import AMParser

_logger = logging.getLogger("Builder")

class Builder(object):
    def __init__(self, topdir):
        self.topdir = topdir
        self.file_attributes = {}
        self.main_am = None

        self.tempdir = tempfile.mkdtemp("", "reinteract_build.")
        self.treedir = os.path.join(self.tempdir, "Reinteract")

        _logger.debug("Top source directory is %s", topdir)
        _logger.info("Temporary directory is %s", self.tempdir)

    def cleanup(self):
        try:
            shutil.rmtree(self.tempdir)
        except:
            pass

    def add_file(self, source, directory, **attributes):
        absdir = os.path.join(self.treedir, directory)
        if os.path.isabs(source):
            abssource = source
        else:
            abssource = os.path.join(self.topdir, source)
        _logger.debug("Copying %s to %s", abssource, directory)
        if not os.path.isdir(absdir):
            os.makedirs(absdir)
        absdest = os.path.join(absdir, os.path.basename(source))
        shutil.copy(abssource, absdest)

        relative = os.path.normpath(os.path.join(directory, os.path.basename(source)))

        self.file_attributes[relative] = attributes

    def add_files_from_directory(self, sourcedir, directory, **attributes):
        for f in os.listdir(sourcedir):
            absf = os.path.join(sourcedir, f)
            if os.path.isdir(absf):
                self.add_files_from_directory(absf, os.path.join(directory, f), **attributes)
            else:
                self.add_file(absf, directory, **attributes)

    def add_matching_files(self, sourcedir, rules, **attributes):
        for f in rules:
            absf = os.path.join(sourcedir, f)
            destdir = os.path.dirname(f)
            if f.find('*') >= 0:
                for ff in glob.iglob(absf):
                    relative = ff[len(sourcedir) + 1:]
                    if os.path.isdir(ff):
                        self.add_files_from_directory(ff, relative, **attributes)
                    else:
                        self.add_file(ff, destdir, **attributes)
            elif os.path.isdir(absf):
                self.add_files_from_directory(absf, f, **attributes)
            else:
                self.add_file(absf, destdir, **attributes)

    def add_external_module(self, module_name, **attributes):
        mod = __import__(module_name)
        f = mod.__file__
        if f.endswith('__init__.pyc') or f.endswith('__init__.pyo') or f.endswith('__init__.py'):
            dir = os.path.dirname(f)
            self.add_files_from_directory(dir, os.path.join('external', os.path.basename(dir)), **attributes)
        else:
            if f.endswith('.pyc') or f.endswith('.pyo'):
                # Don't worry about getting the compiled files, we'll recompile anyways
                f = f[:-3] + "py"
            self.add_file(f, 'external', **attributes)

    def add_files_from_am(self, relative, **attributes):
        am_file = os.path.join(self.topdir, relative, 'Makefile.am')
        am_parser = AMParser(am_file,
           {
                'bindir' : 'bin',
                'docdir' : 'doc',
                'examplesdir' : 'examples',
                'pkgdatadir' : '.',
                'datadir' : '.',
                'pythondir' : 'python',
                'REINTERACT_PACKAGE_DIR' : 'python/reinteract',

                # Some config variables irrelevant for our purposes
                'PYTHON_INCLUDES' : '',
                'WRAPPER_CFLAGS' : ''
           })
        if relative == '':
            self.main_am = am_parser

        for k, v in am_parser.iteritems():
            if k.endswith("_DATA"):
                base = k[:-5]
                dir = am_parser[base + 'dir']
                for x in v.split():
                    self.add_file(os.path.join(relative, x), dir, **attributes)
            elif k.endswith("_PYTHON"):
                base = k[:-7]
                dir = am_parser[base + 'dir']
                for x in v.split():
                    self.add_file(os.path.join(relative, x), dir, **attributes)

        if 'SUBDIRS' in am_parser:
            for subdir in am_parser['SUBDIRS'].split():
                if subdir == '.':
                    continue
                self.add_files_from_am(os.path.join(relative, subdir), **attributes)

    def get_file_attributes(self, relative):
        # .pyc/.pyo are added when we byte-compile the .py files, so they
        # may not be in file_attributes[], so look for the base .py instead
        # to figure out the right feature
        if relative.endswith(".pyc") or relative.endswith(".pyo"):
            relative = relative[:-3] + "py"
            # Handle byte compiled .pyw, though they don't seem to be
            # generated in practice
            if not relative in self.file_attributes:
                relative += "w"

        return self.file_attributes[relative]
