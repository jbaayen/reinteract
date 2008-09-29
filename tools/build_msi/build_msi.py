#!/usr/bin/env python

import ctypes.util
import glob
import logging
from optparse import OptionParser
import os
import re
import shutil
import StringIO
import subprocess
import sys
import tempfile
import uuid

# The upgrade code must never change
UPGRADE_CODE = uuid.UUID('636776fc-e72d-4fe4-af41-d6273b177683')

# The role of the product code is slightly unclear; it doesn't have to
# be changed on every change, but should be changed on 'significant'
# changes. We build it out of a fixed namespace and the version nuber
#
# (There is also a "package code" which is supposed to be different
# for every .msi that is not byte-per-byte identical.)
#
# A different product namespace should be used for a 64-bit installer
#
PRODUCT_NAMESPACE = uuid.UUID('7aff852e-dd4e-4fa0-aa01-13ea8d4b6510')

# Component ID's must be unique to the component, version, and language
#
# We first build a version specific component_namespace from this constant
# value, and then we base component ID's from that.
# 
COMPONENT_NAMESPACE = uuid.UUID('6579e040-85ff-4a20-a709-c9335c70296c')

# A set of patterns defining what files we should extract from the filesystem
# for the 'gtk' libraries that we bundle into the installer. These patterns
# are relative to the root of the GTK+ install tree
GTK_FILES = [
    'bin/intl.dll',
    'bin/jpeg62.dll',
    'bin/libatk-1.0-0.dll',
    'bin/libcairo-2.dll',
    'bin/freetype6.dll',
    'bin/libgdk-win32-2.0-0.dll',
    'bin/libgdk_pixbuf-2.0-0.dll',
    'bin/libglib-2.0-0.dll',
    'bin/libgio-2.0-0.dll',
    'bin/libglib-2.0-0.dll',
    'bin/libgmodule-2.0-0.dll',
    'bin/libgobject-2.0-0.dll',
    'bin/libgthread-2.0-0.dll',
    'bin/libgtk-win32-2.0-0.dll',
    'bin/libpango-1.0-0.dll',
    'bin/libpangocairo-1.0-0.dll',
    'bin/libpangowin32-1.0-0.dll',
    'bin/libpng12-0.dll',
    'bin/libtiff3.dll',
    'bin/zlib1.dll',
    'etc/gtk-2.0/gdk-pixbuf.loaders',
    'etc/gtk-2.0/gtk.immodules',
    'etc/pango/pango.modules',
    'lib/gtk-2.0/2.10.0', # engines, immodules, and pixbuf loaders
    'share/themes',
    'share/doc/cairo-1*',
    'share/doc/glib-2*',
    'share/doc/gtk+-2*',
    'share/doc/pango-1*'
]

TEMPLATE = \
"""
<?xml version='1.0'?><Wix xmlns='http://schemas.microsoft.com/wix/2006/wi'>
   <Product Id='%(product_guid)s' Name='Reinteract' Language='1033'
            Version='%(version)s' Manufacturer='Owen Taylor' UpgradeCode='%(upgrade_code)s'>
      <Package Description='Reinteract'
               Comments='Reinteract Installer for Windows'
               Manufacturer='Owen Taylor' InstallerVersion='200' Compressed='yes' />

      <Upgrade Id='%(upgrade_code)s'>
          <UpgradeVersion Maximum='%(version)s' IncludeMaximum='no' MigrateFeatures='yes' Property='PREVIOUSVERSIONS'/>
      </Upgrade>

      <InstallExecuteSequence>
          <MigrateFeatureStates/>
          <!-- The Windows docs are much too open-ended about the proper placement.
               This is one possible recommended position -->
          <RemoveExistingProducts After="InstallInitialize"/>
      </InstallExecuteSequence>

      <Media Id='1' Cabinet='product.cab' EmbedCab='yes' />

      <!-- The Directory heirarchy is inserted here -->
%(generated)s

      <Icon Id="ReinteractIcon" SourceFile="Reinteract.ico"/>
      <Property Id="ARPPRODUCTICON" Value="ReinteractIcon" />

      <DirectoryRef Id="ProgramMenuFolder">
        <Component Id="ReinteractShortcut" Guid="%(shortcut_component_guid)s">
          <Shortcut Id="ReinteractStartMenuShortcut"
              Name="Reinteract"
              Description="Experiment with Python"
              Target="[%(bindir_id)s]Reinteract.exe"/>
            <RegistryValue Root="HKCU" Key="Software\Reinteract\Reinteract" Name="installed" Type="integer" Value="1" KeyPath="yes"/>
         </Component>
      </DirectoryRef>
      <UIRef Id="ReinteractUI" />
   </Product>
</Wix>
""".strip()

# We need unique keys for various things like components, files.
# Generate them sequentially
id_count = 0
def generate_id():
    global id_count
    id_count += 1
    return "Id%04d" % id_count

# wrapper around subprocess.check_call that logs the command
def check_call(args):
    _logger.info("%s", subprocess.list2cmdline(args))
    subprocess.check_call(args)

# Simple class to suck in a AM file and get variables from it with substitution
class AMParser(object):
    # We ignore possibility of \\\n - a literal backslash at the end of a line
    VARIABLE_RE = re.compile(
        r'^([a-zA-Z_][a-zA-Z0-9_]*)[ \t]*=[ \t]*((?:.*\\\n)*.*)',
        re.MULTILINE);
    REFERENCE_RE = re.compile(r'\$\(([a-zA-Z_][a-zA-Z0-9_]*)\)')

    def __init__(self, filename, overrides={}):
        _logger.debug('Scanning %s', filename)

        f = open(filename, "r")
        contents = f.read()
        f.close()

        self.d = {}
        for m in AMParser.VARIABLE_RE.finditer(contents):
            name = m.group(1)
            value = m.group(2).replace('\\\n', '')
            # Canonicalize whitespace for clean debugg output, would break
            # quoted strings but we don't have any
            value = re.sub(r'\s+', ' ', value.strip())
            self.d[name] = value
            # _logger.debug('   %s = %s', name, value)

        self.d.update(overrides)

    def __getitem__(self, key):
        return AMParser.REFERENCE_RE.sub(lambda m: self[m.group(1)], self.d[key])

    def __iter__(self):
        return self.d.iterkeys()

    def __contains__(self, item):
        return item in self.d

    def iterkeys(self):
        return self.d.iterkeys()

    def iteritems(self):
        return ((x, self[x]) for x in self.d.iterkeys())

class Builder(object):
    def __init__(self, output, topdir, tempdir):
        self.output = output
        self.topdir = topdir
        self.tempdir = tempdir
        self.treedir = os.path.join(self.tempdir, "Reinteract")
        self.file_features = {}
        self.feature_components = {}
        self.directory_ids = {}
        self.generated = None
        self.manifest = []
        self.main_am = None

    def add_file(self, source, directory, feature):
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

        self.file_features[relative] = feature

    def add_files_from_am(self, relative):
        am_file = os.path.join(self.topdir, relative, 'Makefile.am')
        am_parser = AMParser(am_file,
           {
                'bindir' : 'bin',
                'docdir' : 'doc',
                'examplesdir' : 'examples',
                'pkgdatadir' : '.',
                'datadir' : '.',
                'pythondir' : 'python',
                'REINTERACT_PACKAGE_DIR' : 'python/reinteract'
           })
        if relative == '':
            self.main_am = am_parser

        for k, v in am_parser.iteritems():
            if k.endswith("_DATA"):
                base = k[:-5]
                dir = am_parser[base + 'dir']
                for x in v.split():
                    self.add_file(os.path.join(relative, x), dir, 'core')
            elif k.endswith("_PYTHON"):
                base = k[:-7]
                dir = am_parser[base + 'dir']
                for x in v.split():
                    self.add_file(os.path.join(relative, x), dir, 'core')

        if 'SUBDIRS' in am_parser:
            for subdir in am_parser['SUBDIRS'].split():
                if subdir == '.':
                    continue
                self.add_files_from_am(os.path.join(relative, subdir))

    def add_files_from_directory(self, sourcedir, directory, feature):
        for f in os.listdir(sourcedir):
            absf = os.path.join(sourcedir, f)
            if os.path.isdir(absf):
                self.add_files_from_directory(absf, os.path.join(directory, f), feature)
            else:
                self.add_file(absf, directory, feature)

    def add_external_module(self, module_name, feature):
        mod = __import__(module_name)
        f = mod.__file__
        if f.endswith('__init__.pyc') or f.endswith('__init__.pyo') or f.endswith('__init__.py'):
            dir = os.path.dirname(f)
            self.add_files_from_directory(dir, os.path.join('external', os.path.basename(dir)), feature)
        else:
            if f.endswith('.pyc') or f.endswith('.pyo'):
                # Don't worry about getting the compiled files, we'll recompile anyways
                f = f[:-3] + "py"
            self.add_file(f, 'external', feature)

    def find_gtk_directory(self):
        glib_dll = ctypes.util.find_library('libglib-2.0-0.dll')
        assert glib_dll

        bindir = os.path.dirname(glib_dll)
        assert os.path.basename(bindir) == 'bin'

        return os.path.dirname(bindir)

    def add_gtk_files(self):
        gtkdir = self.find_gtk_directory()

        for f in GTK_FILES:
            absf = os.path.join(gtkdir, f)
            destdir = os.path.dirname(f)
            if f.find('*') >= 0:
                for ff in glob.iglob(absf):
                    relative = ff[len(gtkdir) + 1:]
                    if os.path.isdir(ff):
                        self.add_files_from_directory(ff, relative, 'gtk')
                    else:
                        self.add_file(ff, destdir, 'gtk')
            elif os.path.isdir(absf):
                self.add_files_from_directory(absf, f, 'gtk')
            else:
                self.add_file(absf, destdir, 'gtk')

        gtkrcfile = os.path.join(self.tempdir, "gtkrc")
        f = open(gtkrcfile, "w")

        f.write('gtk-theme-name = "MS-Windows"')
        # doesn't seem to work
        # f.write('gtk-im-module = "ime"')
        f.close()

        self.add_file(gtkrcfile, 'etc/gtk-2.0', 'gtk')

        # To redistribute FreeType, you must include an advertising
        # notice for FreeType" in your documentation". I believe adding
        # file with the rest of our licenses in the share/doc subdirectory
        # should be compliant, though a little more obscure than might
        # be considered polite. 
        # 
        # long-term: first evaluate whether FreeType is necessary to
        # the functioning of matplotlib we care about?. If so, maybe
        # special-case the About dialog on Windows to include a notice
        # about FreeType?
        #
        readme_freetype = os.path.join(self.tempdir, "README.FreeType")
        f = open(readme_freetype, "w")
        f.write("""The Reinteract distribution contains contains FreeType.

FreeType is copyright 2008 The FreeType Project (www.freetype.org)
All rights reserved.
""")
        f.close()
        self.add_file(readme_freetype, 'share/doc/freetype', 'gtk')
        
    def generate(self, s):
        if self.generated == None:
            self.generated = StringIO.StringIO()
            self.generated.write(s)
        else:
            self.generated.write('\n')
            self.generated.write(s)

    def add_feature_component(self, feature, component_id):
        if feature in self.feature_components:
            self.feature_components[feature].add(component_id)
        else:
            self.feature_components[feature] = set([component_id])

    def get_file_feature(self, relative):
        # .pyc/.pyo are added when we byte-compile the .py files, so they
        # may not be in file_features[], so look for the base .py instead
        # to figure out the right feature
        if relative.endswith(".pyc") or relative.endswith(".pyo"):
            relative = relative[:-3] + "py"
            # Handle byte compiled .pyw, though they don't seem to be
            # generated in practice
            if not relative in self.file_features:
                relative += "w"
                
        return self.file_features[relative]

    # Extra is something unique to the component
    def generate_component_guid(self, extra):
        return uuid.uuid5(self.component_namespace, extra)
                
    def walk_component_directory(self, directory, indent):
        if directory != '':
            id = generate_id()
            self.generate("%s<Directory Id='%s' Name='%s'>" % (indent, id, os.path.basename(directory)))
            self.directory_ids[directory] = id
        absdir = os.path.join(self.treedir, directory)
        features = {}
        for f in os.listdir(absdir):
            absf = os.path.join(absdir, f)
            relf = os.path.join(directory, f)

            if os.path.isdir(absf):
                continue

            feature = self.get_file_feature(relf)
            if feature in features:
                features[feature].add(relf)
            else:
                features[feature] = set([relf])

        for feature, files in sorted(features.iteritems()):
            id = generate_id()
            guid = self.generate_component_guid("[%s]%s" % (feature, directory))
            self.generate("%s  <Component Id='%s' Guid='%s'>" % (indent, id, guid))
            for file in files:
                # Special case so we can launch out of a custom action later
                if os.path.basename(file) == "Reinteract.exe":
                    file_id = "ReinteractExe"
                else:
                    file_id = generate_id()
                self.manifest.append(file)
                # The problem here is that matplotlib has TTF files that shouldn't be installed
                # on the system and that confuses things because fonts are unique in having a
                # version but no LanguageId embedded in the font. Using DefaultLanguage='0'
                # generates a warning from WiX but avoids the validation warning ICE60. I'm
                # not sure if it actually fixes the problem that ICE60 is warning about.
                if file.endswith(".ttf"):
                    default_language = " DefaultLanguage='0'"
                else:
                    default_language = ""
                self.generate("%s    <File Id='%s' Name='%s' Source='%s'%s/>" % (indent, file_id, os.path.basename(file), file, default_language))
            self.generate("%s  </Component>" % (indent,))

            self.add_feature_component(feature, id)

        for f in os.listdir(absdir):
            absf = os.path.join(absdir, f)
            relf = os.path.join(directory, f)

            features = {}
            absf = os.path.join(absdir, f)
            if not os.path.isdir(absf):
                continue

            self.walk_component_directory(relf, indent + '  ')

        if directory != '':
            self.generate("%s</Directory>" % (indent,))

    def generate_components(self):
        self.generate("<Directory Id='TARGETDIR' Name='SourceDir'>")
        self.generate("  <Directory Id='ProgramFilesFolder'>")
        self.generate("    <Directory Id='APPLICATIONFOLDER' Name='Reinteract'>")
        self.walk_component_directory('', '    ')
        self.generate("    </Directory>")
        self.generate("  </Directory>")
        self.generate("  <Directory Id='ProgramMenuFolder'/>")
        self.generate("</Directory>")

    def generate_feature(self, id, allow_absent, title, description):
        self.generate("<Feature Id='%s' Absent='%s' Title='%s' Description='%s' Level='1'>" % (
            id,
            'allow' if allow_absent else 'disallow',
            title,
            description))
        if id in self.feature_components:
            for component_id in sorted(self.feature_components[id]):
                self.generate("  <ComponentRef Id='%s'/>" % (component_id,))
        self.generate("</Feature>")

    def get_version(self):
        ac_file = os.path.join(self.topdir, 'configure.ac')
        f = open(ac_file, "r")
        contents = f.read()
        f.close()
        m = re.search(r'^\s*AC_INIT\s*\(\s*[A-Za-z0-9_.-]+\s*,\s*([0-9.]+)\s*\)\s*$', contents, re.MULTILINE)
        assert m
        return m.group(1)

    def compile_wrapper(self):
        python_topdir = os.path.dirname(os.path.dirname(glob.__file__))
        python_include = os.path.join(python_topdir, "include")
        python_lib = os.path.join(python_topdir, "libs")
        
        wrapper_c = os.path.join(self.topdir, "tools", "build_msi", "wrapper.c")
        wrapper_o = os.path.join(self.tempdir, "wrapper.o")
        check_call(['gcc', '-o', wrapper_o, '-c', '-O2', '-Wall', '-I', python_include, wrapper_c])
                                 
        wrapper_rc = os.path.join(self.tempdir, "wrapper.rc")
        wrapper_res_o = os.path.join(self.tempdir, "wrapper.res.o")
        f = open(wrapper_rc, "w")
        f.write("""LANGUAGE 0, 0
100	 ICON	%s
""" % os.path.join(self.treedir, "Reinteract.ico"))
        f.close()
        check_call(['windres', '-O', 'COFF', '-o', wrapper_res_o, wrapper_rc])
                   
        wrapper = os.path.join(self.tempdir,  "Reinteract.exe")
        check_call(['gcc', '-mwindows', '-o', wrapper, '-L', python_lib, wrapper_o, wrapper_res_o, '-lpython25'])

        self.add_file(wrapper, 'bin', 'core')

    def build(self):
        version = self.get_version()
        output = self.output % { 'version' : version }
        _logger.info("Will write output to %s", output)

        self.component_namespace = uuid.uuid5(COMPONENT_NAMESPACE, version)
        self.add_files_from_am('')

        self.add_file('bin/Reinteract.pyw', 'bin', 'core')
        # This is a XDG icon-specification organized directory with a SVG in it, not useful
        shutil.rmtree(os.path.join(self.treedir, 'icons'))
        self.add_file('data/Reinteract.ico', '', 'core')
        self.add_feature_component('core', 'ReinteractShortcut')

        self.compile_wrapper()
        
        self.add_external_module('cairo', 'pygtk')
        self.add_external_module('gobject', 'pygtk')
        self.add_external_module('atk', 'pygtk')
        self.add_external_module('pango', 'pygtk')
        self.add_external_module('pangocairo', 'pygtk')
        self.add_external_module('gtk', 'pygtk')
        self.add_external_module('numpy', 'scipy')
        self.add_external_module('matplotlib', 'scipy')
        # More matlab stuff
        self.add_external_module('mpl_toolkits', 'scipy')
        # Some external deps installed with matplotlib
        self.add_external_module('configobj', 'scipy')
        self.add_external_module('dateutil', 'scipy')
        self.add_external_module('pytz', 'scipy')
        # matlab-like toplevel module installed with matplotlib
        self.add_external_module('pylab', 'scipy')

        self.add_gtk_files()

        # Byte-compile all the Python files. We run it twice to generate both .pyc and .pyo
        # I'm not really sure that there is a point in having the .pyc files in the .MSI,
        # but it matches what distutils and Fedora RPM packaging do.
        check_call(['python', os.path.join(self.topdir, 'tools', 'compiledir.py'), self.treedir])
        check_call(['python', "-O", os.path.join(self.topdir, 'tools', 'compiledir.py'), self.treedir])

        self.generate_components()
        self.generate_feature('core', allow_absent='no', title='Reinteract', description='The Reinteract Application')
        self.generate_feature('gtk', allow_absent='yes', title='GTK+', description='Private copies of GTK+, GLib, Pango, ATK, and Cairo')
        self.generate_feature('pygtk', allow_absent='yes', title='PyGTK ', description='Private copies of the PyGTK and Pycairo language bindings')
        self.generate_feature('scipy', allow_absent='yes', title='SciPy', description='Private copies of the numpy and matplotlib modules')

        wxs = TEMPLATE % {
            'product_guid' : uuid.uuid5(PRODUCT_NAMESPACE, version),
            'version' : version,
            'upgrade_code' : UPGRADE_CODE,
            'shortcut_component_guid' : self.generate_component_guid("{shortcut}"),
            'bindir_id' : self.directory_ids['bin'],
            'generated' : self.generated.getvalue(),
            }

        wxsfile = os.path.join(self.tempdir, 'Reinteract.wxs')

        f = open(wxsfile, "w")
        f.write(wxs)
        f.close()

        wxsfiles = [wxsfile]

        localization_file = None
        for w in self.main_am['WIX_FILES'].split():
            absw = os.path.join(self.topdir, w)
            if w.endswith(".wxs"):
                wxsfiles.append(absw)
            elif w.endswith(".wxl"):
                localization_file = absw
            else:
                shutil.copy(absw, self.treedir)

        wixobjfiles = []
        for w in wxsfiles:
            wixobjfile = os.path.join(self.tempdir, os.path.basename(w))
            wixobjfile = re.sub(".wxs$", ".wixobj", wixobjfile)
            check_call(['candle', '-o', wixobjfile, w])
            wixobjfiles.append(wixobjfile)

        # WixUtilExtension is used for WixShellExec
        # WixUIExtension is used for the ErrorDlg, FilesInUse, MsiRMFilesInUse dialogs
        light_cmd = ['light', '-ext', 'WixUtilExtension', '-ext', 'WixUIExtension']
        # Where to look for source files
        light_cmd.extend(['-b', self.treedir])
        # File holding localization strings that we used to override some strings in
        # the WixUI dialogs
        if localization_file != None:
            light_cmd.extend(['-loc', localization_file])
        # Where to write the output
        light_cmd.extend(['-o', output])
        # Object files to build into the result
        light_cmd.extend(wixobjfiles)

        check_call(light_cmd)

        manifestfile = output + ".manifest"
        f = open(manifestfile, "w")
        for x in sorted(self.manifest):
            print >>f, x
        f.close()

############################################################

usage = "usage: %prog [options]"

op = OptionParser(usage=usage)
op.add_option("-o", "--output",
              help=("Filename of MSI to create"))
op.add_option("-d", "--debug", action="store_true",
              help=("Enable debugging messages"))
op.add_option("-v", "--verbose", action="store_true",
              help=("Enable verbose messages"))

options, args = op.parse_args()
if args:
    op.print_usage(sys.stderr)
    sys.exit(1)

if options.debug:
    logging.basicConfig(level=logging.DEBUG)
elif options.verbose:
    logging.basicConfig(level=logging.INFO)

_logger = logging.getLogger("build_msi")

output = options.output
if output == None:
    output = os.path.join(os.getcwd(), "Reinteract-%(version)s.msi")

script = os.path.abspath(sys.argv[0])
scriptdir = os.path.dirname(script)
toolsdir = os.path.dirname(scriptdir)
topdir = os.path.dirname(toolsdir)

_logger.debug("Top source directory is %s", topdir)

tempdir = tempfile.mkdtemp("", "reinteract_build_msi.")
_logger.info("Temporary directory is %s", tempdir)

def cleanup():
    try:
        shutil.rmtree(tempdir)
    except:
        pass

try:
    builder = Builder(output=output, topdir=topdir, tempdir=tempdir)
    builder.build()
finally:
    cleanup()
