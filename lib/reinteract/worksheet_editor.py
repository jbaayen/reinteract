import os

import gobject
import gtk
import pango

from application import application
from editor import Editor
from format_escaped import format_escaped
from shell_buffer import ShellBuffer
from shell_view import ShellView
from window_builder import WindowBuilder

class WorksheetEditor(Editor):
    def __init__(self, notebook):
        Editor.__init__(self, notebook)

        self.buf = ShellBuffer(self.notebook)
        self.view = ShellView(self.buf)
        self.view.modify_font(pango.FontDescription("monospace"))

        self.widget = gtk.ScrolledWindow()
        self.widget.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

        self.widget.add(self.view)

        self.widget.show_all()

        self.buf.worksheet.connect('notify::filename', lambda *args: self._update_title())
        self.buf.worksheet.connect('notify::code-modified', lambda *args: self._update_title())

    #######################################################
    # Utility
    #######################################################

    def __prompt_for_name(self, title, save_button_text, action, check_name=None):
        if check_name == None:
            def check_name(name):
                return name != ""

        builder = WindowBuilder('save-worksheet')
        builder.dialog.set_transient_for(self.widget.get_toplevel())
        builder.dialog.set_title(title)
        builder.dialog.set_default_response(gtk.RESPONSE_OK)

        builder.save_button.set_label(save_button_text)
        builder.save_button.set_image(gtk.image_new_from_stock('gtk-save', gtk.ICON_SIZE_BUTTON))

        def update_save_sensitivity(*args):
            builder.save_button.set_sensitive(check_name(builder.name_entry.get_text().strip()))

        if self.buf.worksheet.filename != None:
            builder.name_entry.set_text(os.path.basename(self.buf.worksheet.filename))

        builder.name_entry.connect('changed', update_save_sensitivity)
        update_save_sensitivity()

        builder.message_label.set_text("Please enter a new name for '%s'" % self._get_display_name())
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
                if not (raw_name.endswith(".rws") or
                        raw_name.endswith(".RWS") or
                        raw_name.endswith(".py") or
                        raw_name.endswith(".PY")):
                    raw_name += ".rws"

            if not error_message:
                fullname = os.path.join(self.buf.worksheet.notebook.folder, raw_name)
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
    # Overrides
    #######################################################

    def _get_display_name(self):
        if self.buf.worksheet.filename == None:
            return "Unsaved Worksheet %d" % self._unsaved_index
        else:
            return os.path.basename(self.buf.worksheet.filename)

    def _get_modified(self):
        return self.buf.worksheet.code_modified

    #######################################################
    # Public API
    #######################################################

    def close(self):
        Editor.close(self)
        self.buf.worksheet.close()

    def load(self, filename):
        if not os.path.exists(filename):
            # FIXME
            self.buf.worksheet.filename = filename
        else:
            self.buf.worksheet.load(filename)
            self.buf.place_cursor(self.buf.get_start_iter())
            self.view.calculate()

    def save(self):
        if self.buf.worksheet.filename == None:
            def action(fullname):
                self.buf.worksheet.save(fullname)
                self._clear_unsaved()
                self.buf.worksheet.notebook.refresh()

            self.__prompt_for_name(title="Save As...", save_button_text="_Save", action=action)
        else:
            self.buf.worksheet.save()

    def rename(self):
        if self.buf.worksheet.filename == None:
            self.save()
            return

        old_name = os.path.basename(self.buf.worksheet.filename)

        title = "Rename '%s'" % old_name

        def check_name(name):
            return name != "" and name != old_name

        def action(fullname):
            old_filename = self.buf.worksheet.filename
            self.buf.worksheet.save(fullname)
            self._clear_unsaved()
            os.remove(old_filename)
            self.buf.worksheet.notebook.refresh()

        self.__prompt_for_name(title=title, save_button_text="_Rename", action=action, check_name=check_name)
