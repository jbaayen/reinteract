import gtk
import os

from application import application
from base_notebook_window import BaseNotebookWindow
from format_escaped import format_escaped
from global_settings import global_settings
from notebook import NotebookFile

class MiniWindow(BaseNotebookWindow):
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
         <menuitem action="new-library"/>
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

        self.__pages_items = []
        BaseNotebookWindow.__init__(self, notebook)

        self.window.set_default_size(800, 600)

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
            BaseNotebookWindow._create_window(self, menu, toolbar)
            toolbar.set_style(gtk.TOOLBAR_ICONS)

    def _fill_content(self):
        self.nb_widget.set_show_tabs(False)
        self.main_vbox.pack_start(self.nb_widget, expand=True, fill=True)

    def _add_actions(self, action_group):
        BaseNotebookWindow._add_actions(self, action_group)

        action_group.add_actions([
            ('notebook',    None,                "_Notebook"),
            ('pages',       None,                "_Pages")
        ])


    def _add_editor(self, editor):
        BaseNotebookWindow._add_editor(self, editor)
        self.__update_pages()

    def _close_editor(self, editor):
        BaseNotebookWindow._close_editor(self, editor)
        self.__update_pages()

    def _update_editor_title(self, editor):
        BaseNotebookWindow._update_editor_title(self, editor)
        if hasattr(editor, '_menu_item_label'):
            editor._menu_item_label.set_markup(format_escaped("<b>%s</b>", editor.title))

    def _update_editor_state(self, editor):
        BaseNotebookWindow._update_editor_state(self, editor)
        if hasattr(editor, '_menu_item_status'):
            editor._menu_item_status.props.stock = NotebookFile.stock_id_for_state(editor.state)

    #######################################################
    # Utility
    #######################################################

    def __create_editor_item(self, editor):
        def on_activate(item):
            self._make_editor_current(editor)

        item = gtk.ImageMenuItem("")
        editor._menu_item_label = item.get_child()
        editor._menu_item_label.set_markup(format_escaped("<b>%s</b>", editor.title))
        item.connect('activate', on_activate)

        editor._menu_item_status = gtk.Image()
        editor._menu_item_status.props.icon_size = gtk.ICON_SIZE_MENU
        editor._menu_item_status.props.stock = NotebookFile.stock_id_for_state(editor.state)
        item.set_image(editor._menu_item_status)
 
        return item

    def __create_file_item(self, file):
        def on_activate(item):
            self.open_file(file)

        item = gtk.MenuItem(os.path.basename(file.path))
        item.connect('activate', on_activate)
        item.editor = None

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
            if editor.file == None:
                items.append(self.__create_editor_item(editor))
            else:
                open_editors[editor.file.path] = editor

        if len(items) > 0:
            items.append(gtk.SeparatorMenuItem())

        for file in sorted(self.notebook.files.values(), self.__sort_files):
            if file.path in open_editors:
                editor = open_editors[file.path]
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

    #######################################################
    # Callbacks
    #######################################################

    # Override the next to to get "one window at a time" behavior. We cheat and open
    # the new and close the old to avoid writing code to retarget an existing MiniWindow,
    # though that probably wouldn't be that hard. (And would look better). Doing it this
    # way is more to prototype out the user interface idea.

    def on_new_notebook(self, action):
        if not self._confirm_discard():
            return

        new_window = application.create_notebook_dialog(parent=self.window)
        if new_window:
            self._close_window()

    def on_open_notebook(self, action):
        if not self._confirm_discard():
            return

        new_window = application.open_notebook_dialog(parent=self.window)
        if new_window:
            self._close_window()
