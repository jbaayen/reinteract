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

class GlobalSettings(gobject.GObject):
    dialogs_dir = gobject.property(type=str)
    examples_dir = gobject.property(type=str)
    mini_mode = gobject.property(type=bool, default=False)
    main_menu_mode = gobject.property(type=bool, default=False)

global_settings = GlobalSettings()
