#!/usr/bin/python

import os
import sys

script_path = os.path.realpath(os.path.abspath(sys.argv[0]))
topdir = os.path.dirname(os.path.dirname(script_path))
libdir = os.path.join(topdir, 'lib')
builderdir = os.path.join(topdir, 'dialogs')

sys.path[0:0] = [libdir]

import reinteract
from reinteract.global_settings import global_settings

global_settings.dialogs_dir = builderdir

import reinteract.main
