import os
import re
import sys

import gtk

from application import application
from base_window import BaseWindow
from file_list import FileList
from format_escaped import format_escaped
from global_settings import global_settings
from notebook import WorksheetFile
from window_builder import WindowBuilder
from worksheet_editor import WorksheetEditor

gtk.rc_parse_string(
    """
    style "notebook-close-button" {
       GtkWidget::focus-line-width = 0
       GtkWidget::focus-padding = 0
       GtkButton::inner-border = { 0, 0, 0, 0 }
    }
    widget "*.notebook-close-button" style : highest "notebook-close-button"
     """)

class MiniWindow(BaseWindow):
    UI_STRING="""
<ui>
   <%(menu_element)s name="TopMenu">
      <menu action="notebook">
         <menuitem action="new-notebook"/>
         <menuitem action="open-notebook"/>
         <menuitem action="notebook-properties"/>
         <separator/>
         <menuitem action="quit"/>
      </menu>
      <menu action="pages" name="PagesMenu">
         <menuitem action="new-worksheet"/>
         <menuitem action="save"/>
         <menuitem action="rename"/>
         <menuitem action="close"/>
      </menu>
      <menu action="edit">
         <menuitem action="cut"/>
         <menuitem action="copy"/>
         <menuitem action="copy-as-doctests"/>
         <menuitem action="paste"/>
         <menuitem action="delete"/>
         <separator/>
         <menuitem action="calculate"/>
      </menu>
	<menu action="help">
        <menuitem action="about"/>
      </menu>
   </%(menu_element)s>
   <toolbar name="ToolBar">
      <toolitem action="new-worksheet"/>
      <toolitem action="save"/>
      <toolitem action="close"/>
      <separator/>
      <toolitem action="calculate"/>
   </toolbar>
</ui>
"""
    def __init__(self, notebook):
        if global_settings.use_hildon:
            global hildon
            import hildon

            menu_element = 'popup'
        else:
            menu_element = 'menubar'

        self.UI_STRING = self.UI_STRING % { 'menu_element': menu_element }

        BaseWindow.__init__(self, notebook)
        self.path = notebook.folder

        self.editors = []
        self.__pages_items = []

        self.__nb_widget = gtk.Notebook()
        self.__nb_widget.set_show_tabs(False)
        self.main_vbox.pack_start(self.__nb_widget, expand=True, fill=True)
        self.__nb_widget.connect_after('switch-page', self.on_page_switched)

        self.window.set_default_size(800, 600)

        self.main_vbox.show_all()

        self.__initial_editor = self.__new_worksheet()
        self.current_editor.view.grab_focus()

        self.__update_pages()
        self.__update_title()

    #######################################################
    # Overrides
    #######################################################

    def _create_window(self, menu, toolbar):
        if global_settings.use_hildon:
            self.window = hildon.Window()
            self.window.set_menu(menu)
            self.window.add_toolbar(toolbar)

            settings = self.window.get_settings()
            settings.set_property("gtk-button-images", False)
            settings.set_property("gtk-menu-images", False)
        else:
            BaseWindow._create_window(self, menu, toolbar)
            toolbar.set_style(gtk.TOOLBAR_ICONS)

    def _add_actions(self, action_group):
        BaseWindow._add_actions(self, action_group)

        action_group.add_actions([
            ('notebook',    None,                "_Notebook"),
            ('pages',       None,                "_Pages"),
            ('notebook-properties', gtk.STOCK_PROPERTIES, "Notebook _Properties", None,         None, self.on_notebook_properties),
            ('new-worksheet',      gtk.STOCK_NEW,         "_New Worksheet",       "<control>n", None, self.on_new_worksheet),
        ])

    def _close_current(self):
        if self.current_editor:
            self.__close_editor(self.current_editor)

    def _close_window(self):
        if not self.__confirm_discard('Discard unsaved changes to worksheet "%s"?', '_Discard'):
            return

        application.window_closed(self)
        self.window.destroy()

    #######################################################
    # Utility
    #######################################################

    def __add_editor(self, editor):
        self.editors.append(editor)
        self.__nb_widget.add(editor.widget)
        editor.connect('notify::title', self.on_editor_notify_title)

        self.__update_editor_title(editor)
        self.__update_pages()

        return editor

    def __close_editor(self, editor):
        if not editor.confirm_discard('Discard unsaved changes to worksheet "%s"?', '_Discard'):
            return

        if editor == self.current_editor:
            # Either we'll switch page and a new editor will be set, or we have no pages left
            self.current_editor = None

        if editor == self.__initial_editor:
            self.__initial_editor = None

        self.editors.remove(editor)
        editor.close()
        self.__update_pages()
        self.__update_title()

    def __make_editor_current(self, editor):
        self.__nb_widget.set_current_page(self.__nb_widget.page_num(editor.widget))

    def __close_initial_editor(self):
        if self.__initial_editor and not self.__initial_editor.buf.worksheet.filename and not self.__initial_editor.modified:
            self.__close_editor(self.__initial_editor)
            self.__initial_editor = None

    def __new_worksheet(self):
        editor = WorksheetEditor(self.notebook)
        self.__add_editor(editor)
        self.__make_editor_current(editor)

        return editor

    def __create_editor_item(self, editor):
        def on_activate(item):
            self.__make_editor_current(editor)

        item = gtk.MenuItem("")
        item.get_child().set_markup(format_escaped("<b>%s</b>", editor.title))
        item.connect('activate', on_activate)

        return item

    def __create_file_item(self, file):
        def on_activate(item):
            self.open_file(file)

        item = gtk.MenuItem(os.path.basename(file.path))
        item.connect('activate', on_activate)

        return item

    def __sort_files(self, file_a, file_b):
        name_a = os.path.basename(file_a.path)
        name_b = os.path.basename(file_b.path)

        c = cmp(name_a.lower(), name_b.lower())
        if c != 0:
            return c

        return cmp(name_a, name_b)

    def __update_pages(self):
        for item in self.__pages_items:
            item.destroy()

        items = self.__pages_items = []

        open_editors = {}
        for editor in self.editors:
            if editor.buf.worksheet.filename == None:
                items.append(self.__create_editor_item(editor))
            else:
                open_editors[editor.buf.worksheet.filename] = editor

        if len(items) > 0:
            items.append(gtk.SeparatorMenuItem())

        for file in sorted(self.notebook.files.values(), self.__sort_files):
            absolute = os.path.join(self.notebook.folder, file.path)
            if absolute in open_editors:
                editor = open_editors[absolute]
                item = self.__create_editor_item(editor)
            else:
                item = self.__create_file_item(file)

            items.append(item)

        if len(items) > 0:
            items.append(gtk.SeparatorMenuItem())

        menu = self.ui_manager.get_widget("/TopMenu/PagesMenu").get_submenu()

        items.reverse()
        for item in items:
            item.show()
            menu.prepend(item)

    def __update_title(self, *args):
        if self.current_editor:
            title = self.current_editor.title + " - " + os.path.basename(self.notebook.folder) + " - Reinteract"
        else:
            title = os.path.basename(self.notebook.folder) + " - Reinteract"

        self.window.set_title(title)

    def __update_editor_title(self, editor):
        if editor == self.current_editor:
            self.__update_title()

    def __confirm_discard(self, message_format, continue_button_text):
        for editor in self.editors:
            if editor.modified:
                # Let the user see what they are discard or not discarding
                self.window.present_with_time(gtk.get_current_event_time())
                self.__make_editor_current(editor)
                if not editor.confirm_discard(message_format, continue_button_text):
                    return False

        return True

    #######################################################
    # Callbacks
    #######################################################

    # Override the next to to get "one window at a time" behavior. We cheat and open
    # the new and close the old to avoid writing code to retarget an existing MiniWindow,
    # though that probably wouldn't be that hard. (And would look better). Doing it this
    # way is more to prototype out the user interface idea.

    def on_new_notebook(self, action):
        if not self.__confirm_discard('Discard unsaved changes to worksheet "%s"?', '_Discard'):
            return

        new_window = application.create_notebook_dialog(parent=self.window)
        if new_window:
            self._close_window()

    def on_open_notebook(self, action):
        if not self.__confirm_discard('Discard unsaved changes to worksheet "%s"?', '_Discard'):
            return

        new_window = application.open_notebook_dialog(parent=self.window)
        if new_window:
            self._close_window()

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

    def on_page_switched(self, notebook, _, page_num):
        widget = self.__nb_widget.get_nth_page(page_num)
        for editor in self.editors:
            if editor.widget == widget:
                self.current_editor = editor
                self.__update_title()
                break

    def on_editor_notify_title(self, editor, *args):
        self.__update_editor_title(editor)

    def on_tab_close_button_clicked(self, editor):
        self.__close_editor(editor)

    def on_file_list_open_file(self, file_list, file):
        self.open_file(file)

    #######################################################
    # Public API
    #######################################################

    def confirm_discard(self):
        if not self.__confirm_discard('Save the changes to worksheet "%s" before quitting?', '_Quit without saving'):
            return False

        return True

    def open_file(self, file):
        if isinstance(file, WorksheetFile):
            if file.worksheet: # Already open
                for editor in self.editors:
                    if isinstance(editor, WorksheetEditor) and editor.buf.worksheet == file.worksheet:
                        self.__make_editor_current(editor)
                        return
            else:
                editor = WorksheetEditor(self.notebook)
                editor.load(os.path.join(self.notebook.folder, file.path))
                self.__add_editor(editor)
                self.__make_editor_current(editor)

                self.__close_initial_editor()
