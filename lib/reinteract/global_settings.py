# Copyright 2008-2009 Owen Taylor
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

from config_file import ConfigFile

def _bool_property(name, default):
    def getter(self):
        return self.config.get_bool('Reinteract', name, default)

    def setter(self, value):
        self.config.set_bool('Reinteract', name, value)

    return gobject.property(getter=getter, setter=setter, type=bool, default=default)

def _string_property(name, default=None):
    def getter(self):
        return self.config.get_string('Reinteract', name, default)

    def setter(self, value):
        self.config.set_string('Reinteract', name, value)

    return gobject.property(getter=getter, setter=setter, type=str, default=default)

class GlobalSettings(gobject.GObject):
    dialogs_dir = gobject.property(type=str)
    examples_dir = gobject.property(type=str)
    config_dir = gobject.property(type=str)
    icon_file = gobject.property(type=str)
    notebooks_dir = gobject.property(type=str)
    mini_mode = gobject.property(type=bool, default=False)
    main_menu_mode = gobject.property(type=bool, default=False)
    version = gobject.property(type=str)

    editor_font_is_custom = _bool_property('editor_font_is_custom', default=False)
    editor_font_name = _string_property('editor_font_name', default="Monospace 12")

    doc_tooltip_font_is_custom = _bool_property('doc_tooltip_font_is_custom', default=False)
    doc_tooltip_font_name = _string_property('doc_tooltip_font_name', default="Sans 11")

    autocomplete = _bool_property('autocomplete', default=True)

    def __init__(self):
        gobject.GObject.__init__(self)

        if sys.platform == 'win32':
            self.config_dir = os.path.join(os.getenv('APPDATA'), 'Reinteract')
        else:
            self.config_dir =  os.path.expanduser("~/.reinteract")

        # In a shocking example of cross-platform convergence, ~/Documents
        # is the documents directory on OS X, Windows, and Linux
        self.notebooks_dir = os.path.expanduser("~/Documents/Reinteract")

        config_location = os.path.join(self.config_dir, 'reinteract.conf')
        self.config = ConfigFile(config_location)

global_settings = GlobalSettings()
