#!/usr/bin/python

import compileall
import sys

# Because we don't pass force=True, byte-compiled existing in the directories
# we build from will be used unmodified; perhaps it would be better to recompile?
compileall.compile_dir(sys.argv[1], quiet=True)
