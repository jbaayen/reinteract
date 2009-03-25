#!/usr/bin/env python
#
# Copyright 2008-2009 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import ctypes.util
import logging
from optparse import OptionParser
import os
import re
import shutil
import StringIO
import sys
import uuid

script = os.path.abspath(sys.argv[0])
scriptdir = os.path.dirname(script)
toolsdir = os.path.dirname(scriptdir)
topdir = os.path.dirname(toolsdir)

sys.path[0:0] = (toolsdir,)

from common.builder import Builder
from common.utils import check_call

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

      <!-- We allow "upgrading" over the same version to support moving between
           the Python-2.5 and Python-2.6 versions; this triggers a validation
           warning but I'm not sure a better way to handle it -->
      <Upgrade Id='%(upgrade_code)s'>
          <UpgradeVersion Maximum='%(version)s' IncludeMaximum='yes' MigrateFeatures='yes' Property='PREVIOUSVERSIONS'/>
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

class MsiBuilder(Builder):
    def __init__(self, output, topdir):
        Builder.__init__(self, topdir)

        self.output = output
        self.feature_components = {}
        self.directory_ids = {}
        self.generated = None
        self.manifest = []

    def find_gtk_directory(self):
        glib_dll = ctypes.util.find_library('libglib-2.0-0.dll')
        assert glib_dll

        bindir = os.path.dirname(glib_dll)
        assert os.path.basename(bindir) == 'bin'

        return os.path.dirname(bindir)

    def add_gtk_files(self):
        gtkdir = self.find_gtk_directory()

        self.add_matching_files(gtkdir, GTK_FILES, '', feature='gtk')

        gtkrcfile = os.path.join(self.tempdir, "gtkrc")
        f = open(gtkrcfile, "w")

        f.write('gtk-theme-name = "MS-Windows"')
        # doesn't seem to work
        # f.write('gtk-im-module = "ime"')
        f.close()

        self.add_file(gtkrcfile, 'etc/gtk-2.0', feature='gtk')

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
        self.add_file(readme_freetype, 'share/doc/freetype', feature='gtk')
        
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
        return self.get_file_attributes(relative)['feature']

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

    def substitute_pyw(self, version):
        origfile = os.path.join(self.topdir, "bin", "Reinteract.pyw")
        f = open(origfile, "r")
        contents = f.read()
        f.close()

        contents = contents.replace("@VERSION@", version)

        destfile = os.path.join(self.tempdir, "Reinteract.pyw")
        f = open(destfile, "w")
        f.write(contents)
        f.close()

        self.add_file(destfile, 'bin', feature='core')

    def compile_wrapper_python25(self):
        # On Python-2.5 we build with MingW32; this avoids creating
        # a dependency on the Visual Studio runtime.
        #
        python_topdir = os.path.dirname(os.path.dirname(shutil.__file__))
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
        lpython = "-lpython%d%d" % (sys.version_info[0], sys.version_info[1])
        check_call(['gcc', '-mwindows', '-o', wrapper, '-L', python_lib, wrapper_o, wrapper_res_o, lpython])

        self.add_file(wrapper, 'bin', feature='core')

    def compile_wrapper_python26(self):
        # For Python-2.6 we build with Visual Studio; trying to get a
        # MingW32-built .exe to load the extensions we bundle for Python-2.6
        # seems very difficult. We hope that our version of Visual Studio
        # was close enough to the version that Python is built with so
        # that if Python runs, we run.
        #
        # We use some distutils internals to locate the Visual Studio
        # command line tools
        #
        from distutils.msvc9compiler import MSVCCompiler
        compiler = MSVCCompiler()
        # This looks for the tools and then adds them to os.environ['Path']
        compiler.initialize()

        python_topdir = os.path.dirname(os.path.dirname(shutil.__file__))
        python_include = os.path.join(python_topdir, "include")
        python_lib = os.path.join(python_topdir, "libs")

        wrapper_c = os.path.join(self.topdir, "tools", "build_msi", "wrapper.c")

        wrapper_rc = os.path.join(self.tempdir, "wrapper.rc")
        f = open(wrapper_rc, "w")
        f.write("""LANGUAGE 0, 0
100	 ICON	%s
""" % os.path.join(self.treedir, "Reinteract.ico"))
        f.close()

        # We can use distutils to do the basic compilation
        objects = compiler.compile([wrapper_c, wrapper_rc],
                                   output_dir=self.tempdir, include_dirs=[python_include])

        # But have to do the linking a bit more manually since distutils
        # doesn't know how to handle creating .exe files
        wrapper = os.path.join(self.tempdir,  "Reinteract.exe")
        manifest = os.path.join(self.tempdir,  "Reinteract.exe.manifest")
        extra_libs = [
            'user32.lib', # For MessageBox
        ]
        check_call([compiler.linker,
                    "/MANIFEST",
                    "/MANIFESTFILE:" + manifest,
                    "/LIBPATH:" + python_lib,
                    "/OUT:" + wrapper]
                   + objects + extra_libs)

        # Embed the manifest into the executable
        check_call(['mt.exe',
                    '-manifest', manifest,
                    '-outputresource:' + wrapper + ';1'])

        self.add_file(wrapper, 'bin', feature='core')

    def build(self):
        version = self.get_version()
        python_version = "python%d.%d" % (sys.version_info[0], sys.version_info[1])
        full_version = version + "-" + python_version

        output = self.output % { 'version' : full_version }
        _logger.info("Will write output to %s", output)

        self.component_namespace = uuid.uuid5(COMPONENT_NAMESPACE, full_version)
        self.add_files_from_am('', '', feature='core')

        self.substitute_pyw(full_version)

        # This is a XDG icon-specification organized directory with a SVG in it, not useful
        shutil.rmtree(os.path.join(self.treedir, 'icons'))
        self.add_file('data/Reinteract.ico', '', feature='core')
        self.add_feature_component('core', 'ReinteractShortcut')

        if python_version == 'python2.5':
            self.compile_wrapper_python25()
        else:
            self.compile_wrapper_python26()

        self.add_external_module('cairo', 'external', feature='pygtk')
        self.add_external_module('gobject', 'external', feature='pygtk')
        self.add_external_module('atk', 'external', feature='pygtk')
        self.add_external_module('pango', 'external', feature='pygtk')
        self.add_external_module('pangocairo', 'external', feature='pygtk')
        self.add_external_module('gtk', 'external', feature='pygtk')
        self.add_external_module('numpy', 'external', feature='scipy')
        self.add_external_module('matplotlib', 'external', feature='scipy')
        # More matlab stuff
        self.add_external_module('mpl_toolkits', 'external', feature='scipy')
        # Some external deps installed with matplotlib
        self.add_external_module('dateutil', 'external', feature='scipy')
        self.add_external_module('pytz', 'external', feature='scipy')
        # matlab-like toplevel module installed with matplotlib
        self.add_external_module('pylab', 'external', feature='scipy')

        self.add_gtk_files()

        self.compile_python()

        self.generate_components()
        self.generate_feature('core', allow_absent='no', title='Reinteract', description='The Reinteract Application')
        self.generate_feature('gtk', allow_absent='yes', title='GTK+', description='Private copies of GTK+, GLib, Pango, ATK, and Cairo')
        self.generate_feature('pygtk', allow_absent='yes', title='PyGTK ', description='Private copies of the PyGTK and Pycairo language bindings')
        self.generate_feature('scipy', allow_absent='yes', title='SciPy', description='Private copies of the numpy and matplotlib modules')

        wxs = TEMPLATE % {
            'product_guid' : uuid.uuid5(PRODUCT_NAMESPACE, full_version),
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

parser = OptionParser()
parser.add_option("-o", "--output",
                  help="Filename of MSI to create")
parser.add_option("-d", "--debug", action="store_true",
                  help="Enable debugging messages")
parser.add_option("-v", "--verbose", action="store_true",
                  help="Enable verbose messages")

options, args = parser.parse_args()
if args:
    parser.print_usage(sys.stderr)
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

builder = MsiBuilder(output=output, topdir=topdir)
try:
    builder.build()
finally:
    builder.cleanup()
