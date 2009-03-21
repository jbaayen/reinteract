#!/usr/bin/env python
#
# Copyright 2007 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import os
import re
import subprocess
import sys

script_path = os.path.realpath(os.path.abspath(sys.argv[0]))
topdir = os.path.dirname(os.path.dirname(script_path))
libdir = os.path.join(topdir, 'lib')
builderdir = os.path.join(topdir, 'dialogs')
examplesdir = os.path.join(topdir, 'examples')

try:
    # Get the git description of the current commit, e.g.
    # REINTERACT_0_4_8-3-gac3e15d
    version = subprocess.Popen(["git", "describe"],
                               env={'GIT_DIR': os.path.join(topdir, ".git")},
                               stdout=subprocess.PIPE).communicate()[0]
    # Transform REINTERACT_0_4_8 into 0.4.8
    version = re.sub("^REINTERACT_", "", version)
    version = re.sub("_", ".", version)
except OSError:
    version = None

sys.path[0:0] = [libdir]

import reinteract
from reinteract.global_settings import global_settings

global_settings.dialogs_dir = builderdir
global_settings.examples_dir = examplesdir
global_settings.version = version

import reinteract.main
reinteract.main.main()
