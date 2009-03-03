# Copyright 2008 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import os

import gobject
import gtk
import pango

try:
    import gtksourceview
    use_sourceview = True
except:
    use_sourceview = False

if use_sourceview:
    language_manager = gtksourceview.SourceLanguagesManager()

from application import application
from editor import Editor
from global_settings import global_settings
from shell_view import ShellView
from window_builder import WindowBuilder

class LibraryEditor(Editor):
    DISCARD_FORMAT = 'Discard unsaved changes to library "%s"?'
    DISCARD_FORMAT_BEFORE_QUIT = 'Save the changes to library "%s" before quitting?'

    def __init__(self, notebook):
        Editor.__init__(self, notebook)

        self.__filename = None
        self.__modified = False
        self.__file = None

        if use_sourceview:
            self.buf = gtksourceview.SourceBuffer()
            self.buf.set_highlight(True)
            language = language_manager.get_language_from_mime_type("text/x-python")
            if language != None:
                self.buf.set_language(language)
            self.view = gtksourceview.SourceView(self.buf)
            self.view.set_insert_spaces_instead_of_tabs(True)
            self.view.set_tabs_width(4)
        else:
            self.buf = gtk.TextBuffer()
            self.view = gtk.TextView(self.buf)

        self.__font_is_custom_connection = global_settings.connect('notify::editor-font-is-custom', self.__update_font)
        self.__font_name_connection = global_settings.connect('notify::editor-font-name', self.__update_font)
        self.__update_font()

        self.buf.connect_after('insert-text', lambda *args: self.__set_modified(True))
        self.buf.connect_after('delete-range', lambda *args: self.__set_modified(True))

        self.widget = gtk.ScrolledWindow()
        self.widget.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

        self.widget.add(self.view)

        self.widget.show_all()

    #######################################################
    # Callbacks
    #######################################################

    def __update_font(self, *arg):
        font_name = "monospace"
        if global_settings.editor_font_is_custom:
            font_name = global_settings.editor_font_name

        self.view.modify_font(pango.FontDescription(font_name))

    #######################################################
    # Overrides
    #######################################################

    def _get_display_name(self):
        if self.__filename == None:
            return "Unsaved Library %d" % self._unsaved_index
        else:
            return os.path.basename(self.__filename)

    def _get_filename(self):
        return self.__filename

    def _get_file(self):
        return self.__file

    def _get_modified(self):
        return self.__modified

    def _get_extension(self):
        return "py"

    def _save(self, filename):
        start = self.buf.get_start_iter()
        end = self.buf.get_end_iter()
        contents = self.buf.get_slice(start, end)

        f = open(filename, "w")
        f.write(contents)
        f.close()

        self.__set_filename_and_modified(filename, False)
        self.notebook.reset_module_by_filename(self.__filename)

    #######################################################
    # Utility
    #######################################################

    def __update_file(self):
        if self.__filename:
            new_file = self.notebook.file_for_absolute_path(self.__filename)
        else:
            new_file = None

        if new_file == self.__file:
            return

        if self.__file:
            self.__file.active = False
            self.__file.modified = False

        self.__file = new_file

        if self.__file:
            self.__file.active = True
            self.__file.modified = self.__modified

        self._update_file()

    def __set_filename(self, filename):
        if filename == self.__filename:
            return

        self.__filename = filename
        self._update_filename()
        self.notebook.refresh()
        self.__update_file()

    def __set_modified(self, modified):
        if modified == self.__modified :
            return

        self.__modified = modified
        if self.__file:
            self.__file.modified = modified
        self._update_modified()

    def __set_filename_and_modified(self, filename, modified):
        self.freeze_notify()
        self.__set_modified(modified)
        self.__set_filename(filename)
        self.thaw_notify()

    #######################################################
    # Public API
    #######################################################

    def load(self, filename):
        if os.path.exists(filename):
            f = open(filename, "r")
            contents = f.read()
            f.close()

            if use_sourceview:
                self.buf.begin_not_undoable_action()
            pos = self.buf.get_start_iter()
            self.buf.insert(pos, contents)
            if use_sourceview:
                self.buf.end_not_undoable_action()

        self.__set_filename_and_modified(filename, False)

    def close(self):
        Editor.close(self)
        if self.__file:
            self.__file.active = False
            self.__file.modified = False
        global_settings.disconnect(self.__font_is_custom_connection)
        global_settings.disconnect(self.__font_name_connection)

    def undo(self):
        if use_sourceview:
            self.view.emit('undo')

    def redo(self):
        if use_sourceview:
            self.view.emit('redo')
