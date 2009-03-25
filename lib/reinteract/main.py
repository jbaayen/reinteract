# Copyright 2007-2009 Owen Taylor
# Copyright 2008 Kai Willadsen
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import gobject
import gtk
import logging
from optparse import OptionParser
import os
import stdout_capture
import sys

gobject.threads_init()
stdout_capture.init()

from global_settings import global_settings
from application import application

def main():
    if sys.version_info < (2, 5, 0):
        message = "Reinteract requires Python 2.5 or newer"
        print >>sys.stderr, message
        try:
            dialog = gtk.MessageDialog(buttons=gtk.BUTTONS_OK,
                                       type=gtk.MESSAGE_ERROR,
                                       message_format=message)
            dialog.run()
        finally:
            sys.exit(1)

    # When launched from the finder on OS X, the command line will have a
    # -psx (process serial number) argument. Strip that out.
    sys.argv = filter(lambda x: not x.startswith("-psn"), sys.argv)

    parser = OptionParser()
    parser.add_option("-u", "--ui", choices=("standard", "mini"), default="standard",
                      help="the user interface mode (standard or mini)")
    parser.add_option("-d", "--debug", action="store_true",
                      help="enable internal debug messages")

    options, args = parser.parse_args()

    if options.debug:
        logging.basicConfig(level=logging.DEBUG)

    global_settings.mini_mode = options.ui == "mini"

    user_ext_path = os.path.expanduser(os.path.join('~', '.reinteract', 'modules'))
    if os.path.exists(user_ext_path):
        sys.path[0:0] = [user_ext_path]

    gtk.window_set_default_icon_name("reinteract")
    gobject.set_application_name("Reinteract")

    if len(args) > 0:
        if options.ui == "standard":
            for arg in args:
                application.open_path(os.path.abspath(arg))
            if len(application.windows) == 0: # nothing opened successfully
                sys.exit(1)
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

            if not application.open_path(absolute):
                sys.exit(1)
    else:
        recent_notebooks = application.state.get_recent_notebooks(max_count=1)
        if len(recent_notebooks) > 0:
            notebook_dir = recent_notebooks[0].path
            window = application.open_notebook(notebook_dir)
        else:
            notebook_dir = os.path.expanduser(os.path.join(global_settings.notebooks_dir, "Main"))
            if not os.path.exists(notebook_dir):
                window = application.create_notebook(notebook_dir,
                                                     description="Notebook for scratch work.\nCreate worksheets here if they are not part of a larger project, or for quick experiments.")
            else:
                window = application.open_notebook(notebook_dir)

        # This really should be a more general check for "is writeable"
        if notebook_dir != global_settings.examples_dir:
            window.add_initial_worksheet()

    gtk.main()
