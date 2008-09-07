import gobject
import gtk
import logging
from optparse import OptionParser
import os
import stdout_capture
import sys

from notebook import Notebook

from global_settings import global_settings

stdout_capture.init()

usage = "usage: %prog [options]"
op = OptionParser(usage=usage)
op.add_option("-u", "--ui", type="choice", choices=("standard", "hildon", "mini"),
              default="standard",  help=("which user interface to use (standard, "
					 "hildon, or mini), default=%default"))
op.add_option("-d", "--debug", action="store_true",
              help=("enable internal debug messages"))

options, args = op.parse_args()

if options.debug:
    logging.basicConfig(level=logging.DEBUG)

global_settings.mini_mode = options.ui == "hildon" or options.ui == "mini"

if options.ui == "hildon":
    try:
        import hildon
        global_settings.use_hildon = True
    except ImportError, e:
        print >>sys.stderr, "Error importing hildon. Falling back to mini ui."
        options.ui = "mini"

user_ext_path = os.path.expanduser(os.path.join('~', '.reinteract', 'modules'))
if os.path.exists(user_ext_path):
    sys.path[0:0] = [user_ext_path]

gtk.window_set_default_icon_name("reinteract")
gobject.set_application_name("Reinteract")

from application import application

if len(args) > 0:
    if options.ui == "standard":
        for arg in args:
            application.open_path(os.path.abspath(arg))
    else: # mini-mode, can specify one notebook
        if len(args) > 1:
            print >>sys.stderr, "Ignoring extra command line arguments."

        absolute = os.path.abspath(args[0])

        # We look to see if we can find the specified notebook so that we can
        # produce a good error message instead of opening a worksheet window
        notebook_path, relative = application.find_notebook_path(absolute)
        if not notebook_path:
            if os.path.isdir(absolute):
                error_message = "'%s' is not a Reinteract notebook" % args[0]
            else:
                error_message = "'%s' is not inside a Reinteract notebook" % args[0]

            dialog = gtk.MessageDialog(buttons=gtk.BUTTONS_OK,
                                       type=gtk.MESSAGE_ERROR,
                                       message_format=error_message)
            dialog.run()
            sys.exit(1)

        application.open_path(absolute)
else:
    recent_notebooks = application.state.get_recent_notebooks(max_count=1)
    if len(recent_notebooks) > 0:
        notebook_dir = recent_notebooks[0].path
        window = application.open_notebook(notebook_dir)
    else:
        notebook_dir = os.path.expanduser(os.path.join(application.get_notebooks_folder(), "Main"))
        if not os.path.exists(notebook_dir):
            window = application.create_notebook(notebook_dir,
                                                 description="Notebook for scratch work.\nCreate worksheets here if they are not part of a larger project, or for quick experiments.")
        else:
            window = application.open_notebook(notebook_dir)

    # This really should be a more general check for "is writeable"
    if notebook_dir != global_settings.examples_dir:
        window.add_initial_worksheet()

gtk.main()
