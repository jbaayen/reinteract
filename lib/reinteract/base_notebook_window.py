import os
import re
import sys

import gtk

from application import application
from base_window import BaseWindow
from library_editor import LibraryEditor
from notebook import LibraryFile, WorksheetFile
from window_builder import WindowBuilder
from worksheet_editor import WorksheetEditor

class BaseNotebookWindow(BaseWindow):
    def __init__(self, notebook):
        BaseWindow.__init__(self, notebook)
        self.path = notebook.folder

        self.editors = []

        self.nb_widget = gtk.Notebook()
        self.nb_widget.connect_after('switch-page', self.on_page_switched)

        self._fill_content()

        self.main_vbox.show_all()

        self.__initial_editor = self.__new_worksheet()
        self.current_editor.view.grab_focus()

        self.__update_title()

    #######################################################
    # Implemented by subclasses
    #######################################################

    def _fill_contents(self, editor):
        raise NotImplementedError()

    def _add_editor(self, editor):
        self.editors.append(editor)
        self.nb_widget.add(editor.widget)
        editor.connect('notify::title', self.on_editor_notify_title)

        self._update_editor_title(editor)

    def _close_editor(self, editor):
        if not editor.confirm_discard():
            return

        if editor == self.current_editor:
            # Either we'll switch page and a new editor will be set, or we have no pages left
            self.current_editor = None

        if editor == self.__initial_editor:
            self.__initial_editor = None

        self.editors.remove(editor)
        editor.close()
        self.__update_title()

    def _update_editor_title(self, editor):
        if editor == self.current_editor:
            self.__update_title()

    #######################################################
    # Overrides
    #######################################################

    def _add_actions(self, action_group):
        BaseWindow._add_actions(self, action_group)

        action_group.add_actions([
            ('notebook-properties', gtk.STOCK_PROPERTIES, "Notebook _Properties", None,         None, self.on_notebook_properties),
            ('new-worksheet',       gtk.STOCK_NEW,        "_New Worksheet",       "<control>n", None, self.on_new_worksheet),
            ('new-library',         gtk.STOCK_NEW,        "New _Library",         "",           None, self.on_new_library),
        ])

    def _close_current(self):
        if self.current_editor:
            self._close_editor(self.current_editor)

    def _close_window(self):
        if not self._confirm_discard():
            return

        application.window_closed(self)
        self.window.destroy()

    #######################################################
    # Utility
    #######################################################

    def _make_editor_current(self, editor):
        self.nb_widget.set_current_page(self.nb_widget.page_num(editor.widget))

    def __close_initial_editor(self):
        if self.__initial_editor and not self.__initial_editor.filename and not self.__initial_editor.modified:
            self._close_editor(self.__initial_editor)
            self.__initial_editor = None

    def __new_worksheet(self):
        editor = WorksheetEditor(self.notebook)
        self._add_editor(editor)
        self._make_editor_current(editor)

        return editor

    def __new_library(self):
        editor = LibraryEditor(self.notebook)
        self._add_editor(editor)
        self._make_editor_current(editor)

        return editor

    def __update_title(self, *args):
        if self.current_editor:
            title = self.current_editor.title + " - " + os.path.basename(self.notebook.folder) + " - Reinteract"
        else:
            title = os.path.basename(self.notebook.folder) + " - Reinteract"

        self.window.set_title(title)

    def _confirm_discard(self, before_quit=False):
        for editor in self.editors:
            if editor.modified:
                # Let the user see what they are discard or not discarding
                self.window.present_with_time(gtk.get_current_event_time())
                self._make_editor_current(editor)
                if not editor.confirm_discard(before_quit=before_quit):
                    return False

        return True

    #######################################################
    # Callbacks
    #######################################################

    def on_notebook_properties(self, action):
        builder = WindowBuilder('notebook-properties')
        builder.dialog.set_transient_for(self.window)
        builder.dialog.set_title("%s - Properties" % self.notebook.info.name)
        builder.name_entry.set_text(self.notebook.info.name)
        builder.name_entry.set_sensitive(False)
        builder.description_text_view.get_buffer().props.text = self.notebook.info.description

        response = builder.dialog.run()
        if response == gtk.RESPONSE_OK:
            self.notebook.info.description = builder.description_text_view.get_buffer().props.text

        builder.dialog.destroy()

    def on_new_worksheet(self, action):
        self.__new_worksheet()

    def on_new_library(self, action):
        self.__new_library()

    def on_page_switched(self, notebook, _, page_num):
        widget = self.nb_widget.get_nth_page(page_num)
        for editor in self.editors:
            if editor.widget == widget:
                self.current_editor = editor
                self.__update_title()
                break

    def on_editor_notify_title(self, editor, *args):
        self._update_editor_title(editor)

    #######################################################
    # Public API
    #######################################################

    def confirm_discard(self):
        if not self._confirm_discard(before_quit=True):
            return False

        return True

    def open_file(self, file):
        filename = os.path.join(self.notebook.folder, file.path)

        if isinstance(file, WorksheetFile):
            if file.worksheet: # Already open
                for editor in self.editors:
                    if isinstance(editor, WorksheetEditor) and editor.buf.worksheet == file.worksheet:
                        self._make_editor_current(editor)
                        return
            else:
                editor = WorksheetEditor(self.notebook)
        elif isinstance(file, LibraryFile):
            for editor in self.editors:
                if isinstance(editor, LibraryEditor) and editor.filename == filename:
                    self._make_editor_current(editor)
                    return
            else:
                editor = LibraryEditor(self.notebook)
        else:
            # Unknown, ignore for now
            return

        editor.load(filename)

        self._add_editor(editor)
        self._make_editor_current(editor)

        self.__close_initial_editor()
