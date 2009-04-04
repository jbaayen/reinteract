# Copyright 2008-2009 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import gtk
import os

from application import application
from window_builder import WindowBuilder

class SaveFileBuilder(WindowBuilder):
    def __init__(self, title, display_name, save_button_text, check_name=None):
        WindowBuilder.__init__(self, 'save-file')

        if check_name is not None:
            self.check_name = check_name

        self.dialog.set_title(title)
        self.dialog.set_default_response(gtk.RESPONSE_OK)

        self.message_label.set_text("Please enter a new name for '%s'" % display_name)

        self.name_entry.connect('changed', self.__update_save_sensitivity)
        self.__update_save_sensitivity()

        self.save_button.set_label(save_button_text)
        self.save_button.set_image(gtk.image_new_from_stock('gtk-save', gtk.ICON_SIZE_BUTTON))

    def __update_save_sensitivity(self, *args):
        self.save_button.set_sensitive(self.check_name(self.name_entry.get_text().strip()))

    def check_name(self, name):
        return name != ""

    def prompt_for_name(self, folder, extension, action):
        while True:
            response = self.dialog.run()
            if response != gtk.RESPONSE_OK:
                break

            raw_name = self.name_entry.get_text()

            error_message = None
            try:
                raw_name = application.validate_name(raw_name)
            except ValueError, e:
                error_message = e.message

            if not error_message:
                if not (raw_name.lower().endswith("." + extension)):
                    raw_name += "." + extension

            if not error_message:
                fullname = os.path.join(folder, raw_name)
                if os.path.exists(fullname):
                    error_message = "'%s' already exists" % raw_name

            if error_message:
                dialog = gtk.MessageDialog(parent=self.dialog, buttons=gtk.BUTTONS_OK,
                                           type=gtk.MESSAGE_ERROR)
                dialog.set_markup("<big><b>Please choose a different name</b></big>")
                dialog.format_secondary_text(error_message)
                dialog.run()
                dialog.destroy()
                continue

            action(fullname)
            break
