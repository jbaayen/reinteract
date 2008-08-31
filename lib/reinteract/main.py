import gobject
import gtk
import logging
from optparse import OptionParser
import os
import stdout_capture
import sys

from notebook import Notebook

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

gobject.set_application_name("Reinteract")

from application import application

if len(args) > 0:
    for arg in args:
        application.open_path(os.path.abspath(arg))
else:
    notebook_dir = os.path.expanduser(os.path.join(application.get_notebooks_folder(), "Main"))
    if not os.path.exists(notebook_dir):
        application.create_notebook(notebook_dir,
                                    description="Notebook for scratch work.\nCreate worksheets here if they are not part of a larger project, or for quick experiments.")
    else:
        application.open_notebook(notebook_dir)

gtk.main()
