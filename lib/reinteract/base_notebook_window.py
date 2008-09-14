import os
import re
import sys

import gtk

from application import application
from base_window import BaseWindow
from library_editor import LibraryEditor
from notebook import LibraryFile, NotebookFile, WorksheetFile
from window_builder import WindowBuilder
from worksheet_editor import WorksheetEditor

class BaseNotebookWindow(BaseWindow):
    def __init__(self, notebook):
        BaseWindow.__init__(self, notebook)

        self.state = application.state.get_notebook_state(notebook.folder)

        self.path = notebook.folder

        self.editors = []

        self.nb_widget = gtk.Notebook()
        self.nb_widget.connect_after('switch-page', self.on_page_switched)
        self.nb_widget.connect('page-reordered', self.on_page_reordered)

        self._fill_content()

        self.main_vbox.show_all()

        self.__initial_editor = None

        open_file_paths = self.state.get_open_files()
        current_file = self.state.get_current_file()

        for path in open_file_paths:
            if not path in self.notebook.files:
                continue

            file = self.notebook.files[path]
            self.open_file(file)

        current_file_editor = None
        if current_file != None:
            filename = os.path.join(notebook.folder, current_file)
            for editor in self.editors:
                if editor.filename == filename:
                    current_file_editor = editor

        if current_file_editor == None and len(self.editors) > 0:
            current_file_editor = self.editors[0]

        if current_file_editor != None:
            self._make_editor_current(current_file_editor)
            current_file_editor.view.grab_focus()

        self.__update_title()

    #######################################################
    # Implemented by subclasses
    #######################################################

    def _fill_contents(self, editor):
        raise NotImplementedError()

    def _add_editor(self, editor):
        self.editors.append(editor)
        self.nb_widget.add(editor.widget)
        editor.widget._notebook_window_editor = editor
        editor.connect('notify::title', self.on_editor_notify_title)
        editor.connect('notify::filename', self.on_editor_notify_filename)
        editor.connect('notify::modified', self.on_editor_notify_modified)
        editor.connect('notify::state', self.on_editor_notify_state)

        self._update_editor_title(editor)
        self._update_editor_state(editor)
        self._update_open_files()

    def _close_editor(self, editor):
        if not editor.confirm_discard():
            return

        if editor == self.current_editor:
            # Either we'll switch page and a new editor will be set, or we have no pages left
            self.current_editor = None

        if editor == self.__initial_editor:
            self.__initial_editor = None

        self.editors.remove(editor)
        editor.widget._notebook_window_editor = None
        editor.close()
        self.__update_title()
        self._update_open_files()

    def _update_editor_state(self, editor):
        self._update_sensitivity()

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
            ('calculate-all',       gtk.STOCK_REFRESH,    "Calculate _All",       "<control><shift>Return",  None, self.on_calculate_all),
        ])

    def _close_current(self):
        if self.current_editor:
            self._close_editor(self.current_editor)

    def _close_window(self):
        if not self._confirm_discard():
            return

        application.window_closed(self)
        self.window.destroy()

    def _update_sensitivity(self):
        BaseWindow._update_sensitivity(self)

        some_need_calculate = False
        for editor in self.editors:
            if (editor.state != NotebookFile.EXECUTE_SUCCESS and
                editor.state != NotebookFile.NONE and
                editor.state != NotebookFile.EXECUTING):
                some_need_calculate = True

        calculate_all_action = self.action_group.get_action('calculate-all')
        calculate_all_action.set_sensitive(some_need_calculate)

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

    def _update_open_files(self):
        open_file_paths = []
        for child in self.nb_widget.get_children():
            file = child._notebook_window_editor.file
            if not file:
                continue

            open_file_paths.append(file.path)

        self.state.set_open_files(open_file_paths)

    def _update_current_file(self):
        file = self.current_editor.file
        if file != None:
            self.state.set_current_file(file.path)
        else:
            self.state.set_current_file(None)

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

    def on_calculate_all(self, action):
        for editor in self.editors:
            if (editor.state != NotebookFile.EXECUTE_SUCCESS and
                editor.state != NotebookFile.NONE and
                editor.state != NotebookFile.EXECUTING):
                editor.buf.worksheet.calculate()

    def on_page_switched(self, notebook, _, page_num):
        widget = self.nb_widget.get_nth_page(page_num)
        for editor in self.editors:
            if editor.widget == widget:
                self.current_editor = editor
                self.__update_title()
                self._update_current_file()
                self._update_sensitivity()
                break

    def on_page_reordered(self, notebook, page, new_page_num):
        self._update_open_files()

    def on_editor_notify_title(self, editor, *args):
        self._update_editor_title(editor)

    def on_editor_notify_filename(self, editor, *args):
        self._update_open_files()
        self._update_current_file()

    def on_editor_notify_modified(self, editor, *args):
        if editor == self.current_editor:
            self._update_sensitivity()

    def on_editor_notify_state(self, editor, *args):
        self._update_editor_state(editor)

    #######################################################
    # Public API
    #######################################################

    def confirm_discard(self):
        if not self._confirm_discard(before_quit=True):
            return False

        return True

    def open_file(self, file):
        filename = os.path.join(self.notebook.folder, file.path)

        for editor in self.editors:
            if editor.file == file:
                self._make_editor_current(editor)
                return

        if isinstance(file, WorksheetFile):
            editor = WorksheetEditor(self.notebook)
        elif isinstance(file, LibraryFile):
            editor = LibraryEditor(self.notebook)
        else:
            # Unknown, ignore for now
            return

        editor.load(filename)

        self._add_editor(editor)
        self._make_editor_current(editor)

        self.__close_initial_editor()

    def add_initial_worksheet(self):
        """If there are no editors open, add a new blank worksheet"""

        if len(self.editors) == 0:
            self.__initial_editor = self.__new_worksheet()
            self.__initial_editor.view.grab_focus()
