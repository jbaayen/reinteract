import os

import gobject
import gtk
import pango

from application import application
from format_escaped import format_escaped
from notebook import NotebookFile
from shell_buffer import ShellBuffer
from shell_view import ShellView
from save_file import SaveFileBuilder

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

    def _update_filename(self, *args):
        self.notify('filename')
        self.notify('title')

    def _update_modified(self, *args):
        self.notify('modified')
        self.notify('title')

    def _update_state(self, *args):
        self.notify('state')

    def _update_file(self):
        self.notify('file')

    def __promt_for_name(self, title, save_button_text, action, check_name=None):
        builder = SaveFileBuilder(title, self._get_display_name(), save_button_text, check_name)
        builder.dialog.set_transient_for(self.widget.get_toplevel())

        if self._get_filename() != None:
            builder.name_entry.set_text(os.path.basename(self._get_filename()))

        while True:
            response = builder.dialog.run()
            if response != gtk.RESPONSE_OK:
                break

            raw_name = builder.name_entry.get_text()

            error_message = None
            try:
                raw_name = application.validate_name(raw_name)
            except ValueError, e:
                error_message = e.message

            if not error_message:
                extension = "." + self._get_extension()
                if not (raw_name.lower().endswith(extension)):
                    raw_name += extension

            if not error_message:
                fullname = os.path.join(self.notebook.folder, raw_name)
                if os.path.exists(fullname):
                    error_message = "'%s' already exists" % raw_name

            if error_message:
                dialog = gtk.MessageDialog(parent=self.widget.get_toplevel(), buttons=gtk.BUTTONS_OK,
                                           type=gtk.MESSAGE_ERROR)
                dialog.set_markup("<big><b>Please choose a different name</b></big>")
                dialog.format_secondary_text(error_message)
                dialog.run()
                dialog.destroy()
                continue

            action(fullname)
            break

        builder.dialog.destroy()

    #######################################################
    # Implemented by subclasses
    #######################################################

    def _get_display_name(self):
        raise NotImplementedError()

    def _get_modified(self):
        raise NotImplementedError()

    def _get_state(self):
        return NotebookFile.NONE

    def _get_filename(self):
        return NotImplementedError()

    def _get_file(self):
        return NotImplementedError()

    def _get_extension(self):
        return NotImplementedError()

    def _save(self, filename):
        return NotImplementedError()

    #######################################################
    # Public API
    #######################################################

    def close(self):
        if self._unsaved_index != None:
            application.free_unsaved_index(self._unsaved_index)
            self._unsaved_index = None

        self.widget.destroy()

    def confirm_discard(self, before_quit=False):
        if not self.modified:
            return True

        if before_quit:
            message_format = self.DISCARD_FORMAT_BEFORE_QUIT
            continue_button_text = '_Quit without saving'
        else:
            message_format = self.DISCARD_FORMAT
            continue_button_text = '_Discard'

        if self._get_filename() == None:
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


    def save(self, filename=None):
        if filename == None:
            filename = self._get_filename()

        if filename == None:
            def action(fullname):
                self._save(fullname)
                self._clear_unsaved()
                self.notebook.refresh()

            self.__promt_for_name(title="Save As...", save_button_text="_Save", action=action)
        else:
            self._save(filename)

    def rename(self):
        if self._get_filename() == None:
            self.save()
            return

        old_name = os.path.basename(self._get_filename())

        title = "Rename '%s'" % old_name

        def check_name(name):
            return name != "" and name != old_name

        def action(fullname):
            old_filename = self._get_filename()
            self._save(fullname)
            self._clear_unsaved()
            os.remove(old_filename)
            self.notebook.refresh()

        self.__promt_for_name(title=title, save_button_text="_Rename", action=action, check_name=check_name)

    @gobject.property
    def filename(self):
        return self._get_filename()

    @gobject.property
    def file(self):
        return self._get_file()

    @gobject.property
    def modified(self):
        return self._get_modified()

    @gobject.property
    def state(self):
        return self._get_state()

    @gobject.property
    def title(self):
        if self.modified:
            return "*" + self._get_display_name()
        else:
            return self._get_display_name()
