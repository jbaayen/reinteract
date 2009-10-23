# Copyright 2008-2009 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import os
import re
import sys

import gtk

from application import application
from file_list import FileList
from format_escaped import format_escaped
from global_settings import global_settings
from library_editor import LibraryEditor
from notebook import Notebook, NotebookFile
from worksheet_editor import WorksheetEditor
from preferences_dialog import show_preferences
import reunicode

if global_settings.main_menu_mode:
    from main_menu import main_menu

class BaseWindow:
    def __init__(self, notebook):
        self.notebook = notebook
        self.path = None
        self.current_editor = None

        self.ui_manager = gtk.UIManager()

        self.action_group = gtk.ActionGroup("main")
        self._add_actions(self.action_group)

        self.ui_manager.insert_action_group(self.action_group, 0)

        self.ui_manager.add_ui_from_string(self.UI_STRING)
        self.ui_manager.ensure_update()

        menu = self.ui_manager.get_widget("/TopMenu")
        toolbar = self.ui_manager.get_widget("/ToolBar")

        self._create_window(menu, toolbar)

        # We want each toplevel to have separate modality
        window_group = gtk.WindowGroup()
        window_group.add_window(self.window)

        self.window.add_accel_group(self.ui_manager.get_accel_group())

        self.main_vbox.show_all()
        self.window.connect('key-press-event', self.on_key_press_event)
        self.window.connect('delete-event', self.on_delete_event)
        self.window.connect('notify::is-active', self.on_notify_is_active)

    #######################################################
    # Implemented by subclasses
    #######################################################

    def _create_window(self, menu, toolbar):
        self.window = gtk.Window()

        self.main_vbox = gtk.VBox()
        self.window.add(self.main_vbox)

        if not global_settings.main_menu_mode:
            self.main_vbox.pack_start(menu, expand=False, fill=False)
        self.main_vbox.pack_start(toolbar, expand=False, fill=False)

    def _add_actions(self, action_group):
        action_group.add_actions([
            ('file',    None,                "_File"),
            ('edit',    None,                "_Edit"),
            ('help',   	None,                "_Help"),

            ('new-notebook',        gtk.STOCK_NEW,        "New Note_book...",     "<control><shift>n", None, self.on_new_notebook),
            ('open-notebook',       gtk.STOCK_OPEN,       "_Open Notebook...",    "<control><shift>o", None, self.on_open_notebook),

            ('open',          gtk.STOCK_OPEN,  None,             None,         None, self.on_open),
            ('save',          gtk.STOCK_SAVE,  None,             None,         None, self.on_save),
            ('rename',        None,            "_Rename...",     None,         None, self.on_rename),
            ('print',         gtk.STOCK_PRINT, "_Print...",      "<control>p", None, self.on_print),
            ('close',         gtk.STOCK_CLOSE, None,             "<control>w", None, self.on_close),

            ('quit',          gtk.STOCK_QUIT, None,                None,         None, self.on_quit),

            ('cut',     gtk.STOCK_CUT,       None,         None,              None, self.on_cut),
            ('copy',    gtk.STOCK_COPY,      None,         None,              None, self.on_copy),

            ('copy-as-doctests', gtk.STOCK_COPY, "Copy as Doc_tests", "<control><shift>c", None, self.on_copy_as_doctests),

            ('paste',   gtk.STOCK_PASTE,     None,         None,              None,  self.on_paste),
            ('delete',  gtk.STOCK_DELETE,    None,         None,              None,  self.on_delete),
            ('about',   gtk.STOCK_ABOUT,     None,         None,              None, self.on_about),
            ('calculate', gtk.STOCK_REFRESH, "Ca_lculate", '<control>Return', None,  self.on_calculate),
            ('break',   gtk.STOCK_CANCEL,    "_Break",     '<control>Break',  None,  self.on_break),
            ('preferences', gtk.STOCK_PREFERENCES, "Prefere_nces",     None,  None,  self.on_preferences),
        ])

    def _close_current(self):
        raise NotImplementedError()

    def _close_window(self):
        if global_settings.main_menu_mode and self.window.is_active():
            main_menu.window_deactivated(self)

        application.window_closed(self)
        self.window.destroy()

    #######################################################
    # Utility
    #######################################################

    def _set_action_sensitive(self, action_name, sensitive):
        action = self.action_group.get_action(action_name)
        action.set_sensitive(sensitive)

        if global_settings.main_menu_mode:
            if sensitive:
                main_menu.enable_action(action_name)
            else:
                main_menu.disable_action(action_name)

    def _load_editor(self, filename):
        if filename.endswith(".rws") or filename.endswith(".RWS"):
            editor = WorksheetEditor(self.notebook)
        elif filename.endswith(".py") or filename.endswith(".PY"):
            editor = LibraryEditor(self.notebook)
        else:
            dialog = gtk.MessageDialog(buttons=gtk.BUTTONS_OK,
                                       type=gtk.MESSAGE_ERROR)
            dialog.set_markup(format_escaped("<big><b>Don't know how to open '%s'</b></big>", os.path.basename(filename)))
            dialog.format_secondary_text("'%s' does not have a recognized file extension" % filename)
            dialog.run()
            dialog.destroy()
            return None

        try:
            try:
                editor.load(filename, escape=False)
            except reunicode.ConversionError, e:
                dialog = gtk.MessageDialog(buttons=gtk.BUTTONS_NONE,
                                           type=gtk.MESSAGE_QUESTION)
                dialog.set_markup(format_escaped("<big><b>Convert conversion errors to escapes?</b></big>"))
                dialog.format_secondary_text(
"Conversion error opening '%s': %s. Do you want to convert to escapes? The file on disk will not be changed until you save."
                                              % (os.path.basename(filename), e.message))

                dialog.add_buttons("gtk-cancel", gtk.RESPONSE_CANCEL,
                                   "Convert", gtk.RESPONSE_OK)
                response = dialog.run()
                dialog.destroy()
                if response != gtk.RESPONSE_OK:
                    return None
                editor.load(filename, escape=True)
        except IOError, e:
            dialog = gtk.MessageDialog(buttons=gtk.BUTTONS_OK,
                                       type=gtk.MESSAGE_ERROR)
            dialog.set_markup(format_escaped("<big><b>Cannot open '%s'</b></big>", os.path.basename(filename)))
            dialog.format_secondary_text("Error opening '%s': %s" %(filename, e.strerror))
            dialog.run()
            dialog.destroy()
            return None

        return editor

    #######################################################
    # Callbacks
    #######################################################

    def on_new_notebook(self, action):
        application.create_notebook_dialog(parent=self.window)

    def on_open_notebook(self, action):
        application.open_notebook_dialog(parent=self.window)

    def on_open(self, action):
        chooser = gtk.FileChooserDialog("Open File...", self.window, gtk.FILE_CHOOSER_ACTION_OPEN,
                                        (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                         gtk.STOCK_OPEN,   gtk.RESPONSE_OK))
        chooser.set_default_response(gtk.RESPONSE_OK)
        response = chooser.run()
        filename = None
        if response == gtk.RESPONSE_OK:
            filename = chooser.get_filename()

        if filename is not None:
            application.open_path(filename)

        chooser.destroy()

    def on_save(self, action):
        if self.current_editor:
            self.current_editor.save()

    def on_rename(self, action):
        if self.current_editor:
            self.current_editor.rename()

    def on_print(self, action):
        if self.current_editor:
            self.current_editor.print_contents()

    def on_close(self, action):
        self._close_current()

    def on_quit(self, action):
        application.quit()

    def on_undo(self, action):
        if self.current_editor:
            self.current_editor.undo()

    def on_redo(self, action):
        if self.current_editor:
            self.current_editor.redo()

    def on_cut(self, action):
        if self.current_editor:
            self.current_editor.view.emit('cut-clipboard')

    def on_copy(self, action):
        if self.current_editor:
            self.current_editor.view.emit('copy-clipboard')

    def on_copy_as_doctests(self, action):
        if self.current_editor:
            self.current_editor.view.copy_as_doctests()

    def on_paste(self, action):
        if self.current_editor:
            self.current_editor.view.emit('paste-clipboard')

    def on_delete(self, action):
        if self.current_editor:
            self.current_editor.view.delete_selection(True, self.view.get_editable())

    def on_calculate(self, action):
        if self.current_editor and self.current_editor.needs_calculate:
            self.current_editor.calculate()

    def on_break(self, action):
        if self.current_editor:
            self.current_editor.buf.worksheet.interrupt()

    def on_preferences(self, action):
        show_preferences(parent=self.window)

    def on_about(self, action):
        application.show_about_dialog(self.window)

    def on_key_press_event(self, window, event):
        if global_settings.main_menu_mode:
            if main_menu.handle_key_press(event):
                return True

        # We have a <Control>Return accelerator, but this hooks up <Control>KP_Enter as well;
        # maybe someone wants that
        if ((event.keyval == gtk.keysyms.Return or event.keyval == gtk.keysyms.KP_Enter) and
            (event.state & gtk.gdk.CONTROL_MASK != 0) and
            (event.state & gtk.gdk.SHIFT_MASK == 0)):
            if self.current_editor and self.current_editor.needs_calculate:
                self.current_editor.calculate()
            return True
        return False

    def on_delete_event(self, window, event):
        self._close_window()
        return True

    def on_notify_is_active(self, window, paramspec):
        if global_settings.main_menu_mode:
            if window.is_active():
                main_menu.window_activated(self)
            else:
                main_menu.window_deactivated(self)

    #######################################################
    # Public API
    #######################################################

    def show(self):
        self.window.show()

    def update_sensitivity(self):
        self._set_action_sensitive('calculate', self.current_editor is not None and self.current_editor.needs_calculate)
        self._set_action_sensitive('break', self.current_editor is not None and self.current_editor.state == NotebookFile.EXECUTING)

        # This seems more annoying than useful. gedit doesn't desensitize save
        # self._set_action_sensitive('save', self.current_editor is not None and self.current_editor.modified)
