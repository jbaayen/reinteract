# Copyright 2008 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################
#
# This module holds preferences and options that are global to the entire program.

import gobject
import os
import sys

class GlobalSettings(gobject.GObject):
    dialogs_dir = gobject.property(type=str)
    examples_dir = gobject.property(type=str)
    config_dir = gobject.property(type=str)
    notebooks_dir = gobject.property(type=str)
    mini_mode = gobject.property(type=bool, default=False)
    main_menu_mode = gobject.property(type=bool, default=False)

    def __init__(self):
        gobject.GObject.__init__(self)

        if sys.platform == 'win32':
            self.config_dir = os.path.join(os.getenv('APPDATA'), 'Reinteract')
        else:
            self.config_dir =  os.path.expanduser("~/.reinteract")

        # In a shocking example of cross-platform convergence, ~/Documents
        # is the documents directory on OS X, Windows, and Linux
        self.notebooks_dir = os.path.expanduser("~/Documents/Reinteract")

global_settings = GlobalSettings()
