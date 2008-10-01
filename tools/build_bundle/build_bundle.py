#!/usr/bin/env python

import ctypes.util
import logging
from optparse import OptionParser
import os
import re
import shutil
import StringIO
import subprocess
import sys
import uuid

# Useful abbreviations
join = os.path.join
dirname = os.path.dirname
basename = os.path.basename

script = os.path.abspath(sys.argv[0])
scriptdir = dirname(script)
toolsdir = dirname(scriptdir)
topdir = dirname(toolsdir)

sys.path[0:0] = (toolsdir,)

from common.builder import Builder

# A set of patterns defining what files we should extract from the filesystem
# for the dependencies libraries that we bundle into the installer. These patterns
# are relative to the root of the install tree. This list is manually maintained
# to keep extra files from accidentally creaping into the installer
DEP_LIBRARY_FILES = [
    'lib/libatk-1.0.*.dylib',
    'lib/libcairo.*.dylib',
    'lib/libgdk-quartz-2.0.*.dylib',
    'lib/libgdk_pixbuf-2.0.*.dylib',
    'lib/libgio-2.0.*.dylib',
    'lib/libglib-2.0.*.dylib',
    'lib/libgmodule-2.0.*.dylib',
    'lib/libgobject-2.0.*.dylib',
    'lib/libgthread-2.0.*.dylib',
    'lib/libgtk-quartz-2.0.*.dylib',
    'lib/libintl.*.dylib',
    'lib/libjpeg.*.dylib',
    'lib/libpango-1.0.*.dylib',
    'lib/libpangocairo-1.0.*.dylib',
    'lib/libpixman-1.*.dylib',
    'lib/libpng12.*.dylib',
    'lib/libpyglib-2.0.*.dylib',
    'lib/libtiff.3.dylib',
    'lib/pango/1.6.0/modules/pango-*.so',
    'lib/gtk-2.0/2.10.0/*/*.so', # engines, immodules, and pixbuf loaders
    'share/themes'
]

# We include readme files and license information for all the dependencies
# we bundle.
DEP_LIBRARY_SOURCE_FILES = [
    'atk*/README',
    'atk*/COPYING',
    'cairo*/README',
    'cairo*/COPYING*',
    'gettext*/README',
    'gettext*/COPYING',
    'glib*/README',
    'glib*/COPYING',
    'gtk+*/README',
    'gtk+*/COPYING',
    'gtk-quartz-engine-*/README',
    'gtk-quartz-engine-*/COPYING',
    'jpeg*/README',
    'libpng*/README',
    'libpng*/LICENSE',
    'matplotlib*/README.txt',
    'matplotlib*/license/*',
    'numpy*/README.txt',
    'numpy*/LICENSE.txt'
    'pango*/README',
    'pango*/COPYING',
    'pixman*/README',
    'pixman*/COPYING',
    'pycairo*/README',
    'pycairo*/COPYING',
    'pygobject*/README',
    'pygobject*/COPYING',
    'pygtk*/README',
    'pygtk*/COPYING',
]

# wrapper around subprocess.check_call that logs the command
def check_call(args):
    _logger.info("%s", subprocess.list2cmdline(args))
    subprocess.check_call(args)

class BundleBuilder(Builder):
    def __init__(self, output, topdir, output_type, arches):
        Builder.__init__(self, topdir, treesubdir='Reinteract.app')

        self.output = output
        self.output_type = output_type
        self.manifest = []

        self.arches = arches

        self.jhbuild_source_dir = os.path.normpath(os.environ['JHBUILD_SOURCE'])
        self.jhbuild_install_dir = os.path.normpath(os.environ['JHBUILD_PREFIX'])

    def repoint_libraries(self, binary, install_dir):
        # Rewrite paths to shared libaries inside binary to be relative to
        # the executable instead of pointing to absolute paths in install_dir

        otool = subprocess.Popen(args=['otool', '-L', binary], stdout=subprocess.PIPE)
        first = True
        for line in otool.stdout:
            # First line is the identification name of the library, subsequent lines are indented
            if not line.startswith('\t'):
                continue
            path = line.strip().split()[0]

            if not path.startswith(install_dir):
                continue

            relative_path = path[len(install_dir) + 1:]
            check_call(['install_name_tool',
                        '-change', path, '@executable_path/../Resources/' + relative_path,
                        binary])

        otool.wait()

    def add_file(self, source, directory, **attributes):
        # We override to add special handling for binary files

        if ((source.endswith(".so") or source.endswith(".dylib")) and
            source.startswith(self.jhbuild_install_dir)):

            relative_path = source[len(self.jhbuild_install_dir) + 1:]

            # We find a correspoding binary for each arch and join them
            # together with the lipo command

            fat_tmp = join(self.tempdir, basename(source))
            lipo_command = ['lipo', '-create', '-output', fat_tmp]

            for arch, install_dir in self.arches.iteritems():
                arch_source = join(install_dir, relative_path)
                arch_tmp = join(self.tempdir, arch + '-' + basename(source))
                shutil.copy(arch_source, arch_tmp)

                # Before running lipo on the library, rewrite dependency
                # paths in it to be relative to the executable
                self.repoint_libraries(arch_tmp, install_dir)

                lipo_command.extend(('-arch', arch, arch_tmp))

            check_call(lipo_command)

            Builder.add_file(self, fat_tmp, directory, **attributes)
        else:
            Builder.add_file(self, source, directory, **attributes)

    def rewrite_modules_file(self, file):
        # Rewrite paths in a module list file to by executable relative
        # (these files are used for different types of dynamically loaded
        # modules within GTK+ to avoid having to load and query a list of
        # shared objects on startup)

        source = join(self.jhbuild_install_dir, file)
        tmp = join(self.tempdir, basename(file))

        infile = open(source, "r")
        outfile = open(tmp, "w")
        for line in infile:
            line = line.replace(self.jhbuild_install_dir, '@executable_path/../Resources')
            outfile.write(line)
        infile.close()
        outfile.close()

        self.add_file(tmp, join('Contents/Resources', dirname(file)))

    def add_dep_library_files(self):
        self.add_matching_files(self.jhbuild_install_dir, DEP_LIBRARY_FILES, 'Contents/Resources')
        self.add_matching_files(self.jhbuild_source_dir, DEP_LIBRARY_SOURCE_FILES, 'Contents/Resources/doc')

        gtkrcfile = join(self.tempdir, "gtkrc")
        f = open(gtkrcfile, "w")

        self.rewrite_modules_file('etc/gtk-2.0/gdk-pixbuf.loaders')
        self.rewrite_modules_file('etc/gtk-2.0/gtk.immodules')
        self.rewrite_modules_file('etc/pango/pango.modules')

        f.write('gtk-theme-name = "Quartz"')
        f.close()

        self.add_file(gtkrcfile, 'Contents/Resources/etc/gtk-2.0')

    def add_external_modules(self):
        externaldir = 'Contents/Resources/external'

        self.add_external_module('cairo', externaldir)
        self.add_external_module('glib', externaldir)
        self.add_external_module('gio', externaldir)
        self.add_external_module('gobject', externaldir)
        self.add_external_module('atk', externaldir)
        self.add_external_module('pango', externaldir)
        self.add_external_module('pangocairo', externaldir)
        self.add_external_module('gtk', externaldir)
        self.add_external_module('numpy', externaldir)
        self.add_external_module('matplotlib', externaldir)
        # More matlab stuff
        self.add_external_module('mpl_toolkits', externaldir)
        # Some external deps installed with matplotlib
        self.add_external_module('configobj', externaldir)
        self.add_external_module('dateutil', externaldir)
        self.add_external_module('pytz', externaldir)
        # matlab-like toplevel module installed with matplotlib
        self.add_external_module('pylab', externaldir)

    def build_manifest(self, dir):
        absdir = join(self.treedir, dir)
        for f in os.listdir(absdir):
            absf = join(absdir, f)
            relative = join(dir, f)
            if os.path.isdir(absf):
                self.build_manifest(relative)
            else:
                self.manifest.append(relative)

    def write_app(self, output):
        shutil.rmtree(output)
        shutil.move(self.treedir, output)

    def write_dmg(self, output):
        # pkg-dmg expects a folder corresponding to the top of the image, so
        # we need to move our Reinteract.app folder down a level
        sourcefolder = join(self.tempdir, "Reinteract-tmp")
        os.makedirs(sourcefolder)
        shutil.move(self.treedir, join(sourcefolder, "Reinteract.app"))

        command = ['pkg-dmg']
        command.extend(('--source', sourcefolder))
        command.extend(('--target', output))
        # This exact Volume Name is important, since the .DS_Store file contains
        # a reference to /Volumes/Reinteract/.background/reinteract-background.png
        # I don't know if a relative path is possible.
        command.extend(('--volname', 'Reinteract'))
        command.extend(('--mkdir', '.background'))
        command.extend(('--copy', join(self.topdir, 'tools/build_bundle/reinteract-dmg-background.png') + ':' + ".background/reinteract-background.png"))
        command.extend(('--copy', join(self.topdir, 'tools/build_bundle/reinteract.dsstore') + ':' + ".DS_Store"))
        command.extend(('--symlink', '/Applications:Applications'))

        check_call(command)

    def build(self):
        version = self.get_version()
        output = self.output % { 'version' : version }
        _logger.info("Will write output to %s", output)

        self.add_files_from_am('', 'Contents/Resources')
        # This is a XDG icon-specification organized directory with a SVG in it, not useful
        shutil.rmtree(join(self.treedir, 'Contents/Resources/icons'))
        # Desktop files for the Linux desktop
        shutil.rmtree(join(self.treedir, 'Contents/Resources/applications'))

        self.add_dep_library_files()
        self.add_external_modules()

        self.add_file('data/Info.plist', 'Contents')
        self.add_file('data/Reinteract.icns', 'Contents/Resources')
        self.add_files_from_directory('data/MainMenu.nib', 'Contents/Resources/MainMenu.nib')

        shutil.copy(join(self.topdir, 'ReinteractWrapper'),
                    join(self.tempdir, 'Reinteract'))
        self.add_file(join(self.tempdir, 'Reinteract'), 'Contents/MacOS')

        self.build_manifest('')

        manifestfile = output + ".manifest"
        f = open(manifestfile, "w")
        for x in sorted(self.manifest):
            print >>f, x
        f.close()

        if self.output_type == "app":
            self.write_app(output)
        else:
            self.write_dmg(output)

############################################################

usage = "usage: %prog [options]"

op = OptionParser(usage=usage)
op.add_option("-o", "--output",
              help=("Filename of output to create"))
op.add_option("-d", "--debug", action="store_true",
              help=("Enable debugging messages"))
op.add_option("-v", "--verbose", action="store_true",
              help=("Enable verbose messages"))
op.add_option("", "--add-arch", action="append",
              help=("Specify a path to an alternate architecture jhbuild install tree"))
op.add_option("", "--dmg", action="store_true",
              help=("Create a .dmg file (default)"))
op.add_option("", "--app", action="store_true",
              help=("Create a .app directory"))

options, args = op.parse_args()
if args:
    op.print_usage(sys.stderr)
    sys.exit(1)

if options.debug:
    logging.basicConfig(level=logging.DEBUG)
elif options.verbose:
    logging.basicConfig(level=logging.INFO)

if options.dmg and options.app:
    print >>sys.stderr, "Only one of --dmg and --app can be specified"
    sys.exit(1)

output_type = "app" if options.app else "dmg"

_logger = logging.getLogger("build_bundle")

output = options.output
if output == None:
    if output_type == "app":
        output = join(os.getcwd(), "Reinteract.app")
    else:
        output = join(os.getcwd(), "Reinteract-%(version)s.dmg")

install_dirs = [os.environ['JHBUILD_PREFIX']]
if options.add_arch:
    install_dirs.extend(options.add_arch)

arches = {}
for install_dir in install_dirs:
    m = re.match('.*/(devel|release)-([^/]*)/.*', install_dir)
    if not m:
        print >>sys.stderr, "Can't extract architecture from --add-arch option"
        sys.exit(1)
    arches[m.group(2)] = os.path.normpath(install_dir)

builder = BundleBuilder(output=output, topdir=topdir, output_type=output_type, arches=arches)
try:
    builder.build()
finally:
    builder.cleanup()
