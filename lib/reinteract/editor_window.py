# Copyright 2008-2009 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import gtk
import pango

import os
import sys

from application import application
from base_window import BaseWindow
from global_settings import global_settings
from notebook import Notebook

class EditorWindow(BaseWindow):
    UI_STRING="""
<ui>
   <menubar name="TopMenu">
      <menu action="file">
         <menuitem action="new-notebook"/>
         <menuitem action="open-notebook"/>
         <separator/>
         <menuitem action="open"/>
         <menuitem action="save"/>
         <menuitem action="save-as"/>
         <separator/>
         <menuitem action="quit"/>
      </menu>
      <menu action="edit">
         <menuitem action="cut"/>
         <menuitem action="copy"/>
         <menuitem action="copy-as-doctests"/>
         <menuitem action="paste"/>
         <menuitem action="delete"/>
         <separator/>
         <menuitem action="calculate"/>
         <menuitem action="break"/>
         <separator/>
         <menuitem action="preferences"/>
      </menu>
	<menu action="help">
        <menuitem action="about"/>
      </menu>
   </menubar>
   <toolbar name="ToolBar">
      <toolitem action="calculate"/>
      <toolitem action="break"/>
   </toolbar>
</ui>
"""

    def __init__(self):
        BaseWindow.__init__(self, Notebook())
        self.path = None

        self.window.set_default_size(700, 800)

        self.main_vbox.show_all()

    #######################################################
    # Overrides
    #######################################################

    def _add_actions(self, action_group):
        BaseWindow._add_actions(self, action_group)

        action_group.add_actions([
            ('save-as', gtk.STOCK_SAVE_AS,   None,         None,              None, self.on_save_as),
        ])

    def _close_current(self):
        self._close_window()

    def _close_window(self):
        if not self.current_editor.confirm_discard():
            return True

        BaseWindow._close_window(self)

    #######################################################
    # Utility
    #######################################################

    def __save_as(self):
        chooser = gtk.FileChooserDialog("Save As...", self.window, gtk.FILE_CHOOSER_ACTION_SAVE,
                                        (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                         gtk.STOCK_SAVE,   gtk.RESPONSE_OK))
        chooser.set_default_response(gtk.RESPONSE_OK)
        response = chooser.run()
        filename = None
        if response == gtk.RESPONSE_OK:
            filename = chooser.get_filename()

        if filename is not None:
            self.current_editor.save(filename)
            self.path = filename
            self.notebook.set_path([os.path.dirname(filename)])

        chooser.destroy()

    def __update_title(self, *args):
        self.window.set_title(self.current_editor.title + " - Reinteract")

    #######################################################
    # Callbacks
    #######################################################

    def on_save(self, action):
        if self.current_editor.filename is None:
            self.__save_as()
        else:
            self.current_editor.save()

    def on_save_as(self, action):
        self.__save_as()

    #######################################################
    # Public API
    #######################################################

    def confirm_discard(self):
        if self.current_editor and not self.current_editor.confirm_discard():
            return False

        return True

    def load(self, filename):
        editor = self._load_editor(filename)
        if not editor:
            return False

        if self.current_editor:
            self.current_editor.destroy()

        self.current_editor = editor

        self.current_editor.connect('notify::modified', lambda *args: self.update_sensitivity())
        self.current_editor.connect('notify::title', self.__update_title)
        self.current_editor.connect('notify::state', lambda *args: self.update_sensitivity())
        self.main_vbox.pack_start(self.current_editor.widget, expand=True, fill=True)

        self.path = filename

        self.update_sensitivity()

        self.current_editor.view.grab_focus()
        self.__update_title()

        return True
