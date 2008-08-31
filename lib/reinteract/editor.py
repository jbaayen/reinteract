import os

import gobject
import gtk
import pango

from application import application
from format_escaped import format_escaped
from shell_buffer import ShellBuffer
from shell_view import ShellView
from window_builder import WindowBuilder

class Editor(gobject.GObject):
    def __init__(self, notebook):
        gobject.GObject.__init__(self)

        self.notebook = notebook
        self._unsaved_index = application.allocate_unsaved_index()

    #######################################################
    # Utility
    #######################################################

    def _clear_unsaved(self):
        if self._unsaved_index != None:
            application.free_unsaved_index(self._unsaved_index)
            self._unsaved_index = None

    def _update_title(self, *args):
        self.notify('title')

    #######################################################
    # Implemented by subclasses
    #######################################################

    def _get_display_name(self):
        raise NotImplementedError()

    def _get_modified(self):
        raise NotImplementedError()

    #######################################################
    # Public API
    #######################################################

    def close(self):
        if self._unsaved_index != None:
            application.free_unsaved_index(self._unsaved_index)
            self._unsaved_index = None

        self.widget.destroy()

    def confirm_discard(self, message_format, continue_button_text):
        if not self.modified:
            return True

        if self.buf.worksheet.filename == None:
            save_button_text = gtk.STOCK_SAVE_AS
        else:
            save_button_text = gtk.STOCK_SAVE

        message = format_escaped("<big><b>" + message_format + "</b></big>", self._get_display_name())

        dialog = gtk.MessageDialog(parent=self.widget.get_toplevel(), buttons=gtk.BUTTONS_NONE,
                                   type=gtk.MESSAGE_WARNING)
        dialog.set_markup(message)

        dialog.add_buttons(continue_button_text, gtk.RESPONSE_OK,
                           gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                           save_button_text, 1)
        dialog.set_default_response(1)
        response = dialog.run()
        dialog.destroy()

        if response == gtk.RESPONSE_OK:
            return True
        elif response == 1:
            self.save()

            if self.modified:
                return False
            else:
                return True
        else:
            return False

    def load(self, filename):
        raise NotImplementedError()

    def save(self):
        raise NotImplementedError()

    def rename(self):
        raise NotImplementedError()

    @gobject.property
    def modified(self):
        return self._get_modified()

    @gobject.property
    def title(self):
        if self.modified:
            return "*" + self._get_display_name()
        else:
            return self._get_display_name()
