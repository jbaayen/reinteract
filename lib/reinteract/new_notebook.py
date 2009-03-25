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
from global_settings import global_settings
from window_builder import WindowBuilder

class CreateNotebookBuilder(WindowBuilder):
    def __init__(self):
        WindowBuilder.__init__(self, 'new-notebook')

        self.name_entry.connect('changed', self.__update_create_sensitivity)
        self.__update_create_sensitivity()

        self.description_text_view.set_accepts_tab(False)

        self.other_folder_radio_button.set_group(self.default_folder_radio_button)

        self.other_folder_radio_button.connect('toggled', self.__update_other_folder_sensitivity)
        self.__update_other_folder_sensitivity(self.other_folder_radio_button)

        self.other_folder_chooser.set_filename(global_settings.notebooks_dir)

        self.create_button.set_image(gtk.image_new_from_stock('gtk-new', gtk.ICON_SIZE_BUTTON))

    def __update_create_sensitivity(self, *args):
        self.create_button.set_sensitive(self.name_entry.get_text().strip() != "")

    def __update_other_folder_sensitivity(self, *args):
        self.other_folder_chooser.set_sensitive(self.other_folder_radio_button.get_active())


def run(parent=None):
    builder = CreateNotebookBuilder()
    builder.dialog.set_transient_for(parent)
    result_window = None

    while True:
        response = builder.dialog.run()
        if response == 0: # gtk-builder-convert puts check/radio buttons in action-widgets
            continue
        if response != gtk.RESPONSE_OK:
            break

        error_message = None
        error_detail = None
        try:
            name = application.validate_name(builder.name_entry.get_text())
        except ValueError, e:
            error_message = "<big><b>Please choose a different name</b></big>"
            error_detail = e.message

        if error_message == None:
            if builder.other_folder_radio_button.get_active():
                parent_folder = builder.other_folder_chooser.get_filename()
            else:
                parent_folder = global_settings.notebooks_dir

            fullname = os.path.join(parent_folder, name)
            if os.path.exists(fullname):
                error_message = "<big><b>Please choose a different name</b></big>"
                error_detail = "'%s' already exists" % name

        if error_message == None:
            try:
                builder.dialog.hide()
                description = builder.description_text_view.get_buffer().props.text.strip()
                result_window = application.create_notebook(fullname, description=description)
            except OSError, e:
                builder.dialog.show()
                error_message = "<big><b>Error creating notebook</b></big>"
                error_detail = e.message

        if error_message:
            dialog = gtk.MessageDialog(parent=builder.dialog, buttons=gtk.BUTTONS_OK,
                                       type=gtk.MESSAGE_ERROR)
            dialog.set_markup(error_message)
            dialog.format_secondary_text(error_detail)
            dialog.run()
            dialog.destroy()
            continue

        break

    builder.dialog.destroy()
    return result_window
