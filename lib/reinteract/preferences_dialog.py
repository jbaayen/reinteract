# Copyright 2008 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import gtk

from global_settings import global_settings
from window_builder import WindowBuilder

class PreferencesBuilder(WindowBuilder):
    def __init__(self):
        WindowBuilder.__init__(self, 'preferences')

        self.dialog.connect('response', self.__on_response)
        self.dialog.connect('delete-event', self.__on_delete_event)

        global_settings.connect('notify::editor-font-is-custom', self.__on_notify_editor_font_is_custom)
        self.__on_notify_editor_font_is_custom()

        self.editor_font_custom_check_button.connect('toggled', self.__on_editor_font_custom_check_button_toggled)
        self.__on_editor_font_custom_check_button_toggled()

        global_settings.connect('notify::editor-font-name', self.__on_notify_editor_font_name)
        self.__on_notify_editor_font_name()

        self.editor_font_button.connect('font-set', self.__on_editor_font_set)

        global_settings.connect('notify::doc_tooltip-font-is-custom', self.__on_notify_doc_tooltip_font_is_custom)
        self.__on_notify_doc_tooltip_font_is_custom()

        self.doc_tooltip_font_custom_check_button.connect('toggled', self.__on_doc_tooltip_font_custom_check_button_toggled)
        self.__on_doc_tooltip_font_custom_check_button_toggled()

        global_settings.connect('notify::doc_tooltip-font-name', self.__on_notify_doc_tooltip_font_name)
        self.__on_notify_doc_tooltip_font_name()

        self.doc_tooltip_font_button.connect('font-set', self.__on_doc_tooltip_font_set)

    def __on_notify_editor_font_is_custom(self, *args):
        self.editor_font_custom_check_button.set_active(global_settings.editor_font_is_custom)

    def __on_notify_editor_font_name(self, *args):
        self.editor_font_button.set_font_name(global_settings.editor_font_name)

    def __on_editor_font_custom_check_button_toggled(self, *args):
        font_is_custom = self.editor_font_custom_check_button.get_active()
        self.editor_font_button.set_sensitive(font_is_custom)
        if font_is_custom != global_settings.editor_font_is_custom:
            global_settings.editor_font_is_custom = font_is_custom

    def __on_editor_font_set(self, font_button):
        font_name = font_button.get_font_name()
        if font_name != global_settings.editor_font_name:
            global_settings.editor_font_name = font_name

    def __on_notify_doc_tooltip_font_is_custom(self, *args):
        self.doc_tooltip_font_custom_check_button.set_active(global_settings.doc_tooltip_font_is_custom)

    def __on_notify_doc_tooltip_font_name(self, *args):
        self.doc_tooltip_font_button.set_font_name(global_settings.doc_tooltip_font_name)

    def __on_doc_tooltip_font_custom_check_button_toggled(self, *args):
        font_is_custom = self.doc_tooltip_font_custom_check_button.get_active()
        self.doc_tooltip_font_button.set_sensitive(font_is_custom)
        if font_is_custom != global_settings.doc_tooltip_font_is_custom:
            global_settings.doc_tooltip_font_is_custom = font_is_custom

    def __on_doc_tooltip_font_set(self, font_button):
        font_name = font_button.get_font_name()
        if font_name != global_settings.doc_tooltip_font_name:
            global_settings.doc_tooltip_font_name = font_name

    def __on_response(self, dialog, response_id):
        self.dialog.hide()

    def __on_delete_event(self, dialog, event):
        self.dialog.hide()
        return True

_builder = None

def show_preferences(parent=None):
    global _builder

    if not _builder:
        _builder = PreferencesBuilder()

    _builder.dialog.set_transient_for(parent)
    if _builder.dialog.flags() & gtk.VISIBLE == 0:
        _builder.dialog.show()
    else:
        _builder.dialog.present_with_time(gtk.get_current_event_time())
