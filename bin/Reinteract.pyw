#!/usr/bin/python

import os
import sys

script_path = os.path.realpath(os.path.abspath(sys.argv[0]))
topdir = os.path.dirname(os.path.dirname(script_path))
libdir = os.path.join(topdir, 'python')
externaldir = os.path.join(topdir, 'external')
builderdir = os.path.join(topdir, 'dialogs')
examplesdir = os.path.join(topdir, 'examples')

sys.path[0:0] = [libdir, externaldir]

import reinteract
from reinteract.global_settings import global_settings

global_settings.dialogs_dir = builderdir
global_settings.examples_dir = examplesdir

import reinteract.main
reinteract.main.main()
