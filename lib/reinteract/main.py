import gtk

import logging
from optparse import OptionParser
import os
import stdout_capture
import sys

from global_settings import global_settings
from worksheet_window import WorksheetWindow

stdout_capture.init()

usage = "usage: %prog [options]"
op = OptionParser(usage=usage)
op.add_option("-u", "--ui", type="choice", choices=("standard", "hildon"),
              default="standard",  help=("which user interface to use (standard or "
					 "hildon), default=%default"))
op.add_option("-d", "--debug", action="store_true",
              help=("enable internal debug messages"))

options, args = op.parse_args()

if options.debug:
    logging.basicConfig(level=logging.DEBUG)

if options.ui == "hildon":
    try:
        import hildon
        global_settings.use_hildon = True
    except ImportError, e:
        print >>sys.stderr, "Error importing hildon. Falling back to standard ui."

w = WorksheetWindow()

if len(args) > 0:
    w.load(args[0])
else:
    # If you run reinteract from the command line, you'd expect to be able to
    # create a worksheet, test it, then save it in the current directory, and
    # have that act the same as loading the worksheet to start with. This is
    # less obviously right when run from a menu item.
    w.notebook.set_path([os.getcwd()])

w.show()

gtk.main()
