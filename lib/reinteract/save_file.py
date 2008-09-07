import gtk
import os

from window_builder import WindowBuilder

class SaveFileBuilder(WindowBuilder):
    def __init__(self, title, display_name, save_button_text, check_name=None):
        WindowBuilder.__init__(self, 'save-file')

        if check_name != None:
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
