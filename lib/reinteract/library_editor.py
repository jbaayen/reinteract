import os

import gobject
import gtk
import pango

try:
    import gtksourcevieww
    use_sourceview = True
except:
    use_sourceview = False

if use_sourceview:
    language_manager = gtksourceview.SourceLanguagesManager()

from application import application
from editor import Editor
from shell_view import ShellView
from window_builder import WindowBuilder

class LibraryEditor(Editor):
    DISCARD_FORMAT = 'Discard unsaved changes to library "%s"?'
    DISCARD_FORMAT_BEFORE_QUIT = 'Save the changes to library "%s" before quitting?'

    def __init__(self, notebook):
        Editor.__init__(self, notebook)

        self.__filename = None
        self.__modified = False

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

        self.view.modify_font(pango.FontDescription("monospace"))

        self.buf.connect_after('insert-text', lambda *args: self.__mark_modified())
        self.buf.connect_after('delete-range', lambda *args: self.__mark_modified())

        self.widget = gtk.ScrolledWindow()
        self.widget.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

        self.widget.add(self.view)

        self.widget.show_all()

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

        self.__filename = filename
        self.__modified = False
        self._update_title()

    #######################################################
    # Utility
    #######################################################

    def __mark_modified(self):
        if not self.__modified:
            self.__modified = True
            self._update_title()

    #######################################################
    # Public API
    #######################################################

    def load(self, filename):
        if os.path.exists(filename):
            f = open(filename, "r")
            contents = f.read()
            f.close()

            pos = self.buf.get_start_iter()
            self.buf.insert(pos, contents)

        self.__filename = filename
        self.__modified = False
        self._update_title()
