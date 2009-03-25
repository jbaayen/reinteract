# Copyright 2008-2009 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import gtk
import os

from base_notebook_window import BaseNotebookWindow
from file_list import FileList
from format_escaped import format_escaped
from notebook import NotebookFile, WorksheetFile, LibraryFile
from save_file import SaveFileBuilder

gtk.rc_parse_string(
    """
    style "notebook-close-button" {
       GtkWidget::focus-line-width = 0
       GtkWidget::focus-padding = 0
       GtkButton::inner-border = { 0, 0, 0, 0 }
    }
    widget "*.notebook-close-button" style : highest "notebook-close-button"
     """)

class NotebookWindow(BaseNotebookWindow):
    UI_STRING="""
<ui>
   <menubar name="TopMenu">
      <menu action="file">
         <menuitem action="new-notebook"/>
         <menuitem action="open-notebook"/>
         <menuitem action="notebook-properties"/>
         <separator/>
         <menuitem action="new-worksheet"/>
         <menuitem action="new-library"/>
         <menuitem action="open"/>
         <menuitem action="save"/>
         <menuitem action="rename"/>
         <menuitem action="close"/>
         <separator/>
         <menuitem action="quit"/>
      </menu>
      <menu action="edit">
         <menuitem action="cut"/>
         <menuitem action="copy"/>
         <menuitem action="copy-as-doctests"/>
         <menuitem action="paste"/>
         <menuitem action="delete"/>
         <separator/>
         <menuitem action="calculate"/>
         <menuitem action="break"/>
         <separator/>
         <menuitem action="calculate-all"/>
         <separator/>
         <menuitem action="preferences"/>
      </menu>
	<menu action="help">
        <menuitem action="about"/>
      </menu>
   </menubar>
   <toolbar name="ToolBar">
      <toolitem action="save"/>
      <separator/>
      <toolitem action="calculate"/>
      <toolitem action="break"/>
   </toolbar>
</ui>
"""
    def __init__(self, notebook):
        BaseNotebookWindow.__init__(self, notebook)

        self.window.set_default_size(800, 800)

    #######################################################
    # Overrides
    #######################################################

    def _fill_content(self):
        hpaned = gtk.HPaned()
        position = self.state.get_pane_position()
        if position == -1:
            hpaned.set_position(200)
        else:
            hpaned.set_position(position)
        hpaned.connect('notify::position', self.on_hpaned_notify_position)
        self.main_vbox.pack_start(hpaned, expand=True, fill=True)

        scrolled_window = gtk.ScrolledWindow()
        scrolled_window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        hpaned.pack1(scrolled_window, resize=False)

        self.__file_list = FileList(self.notebook)
        scrolled_window.add(self.__file_list)
        self.__file_list.connect('open-file', self.on_file_list_open_file)
        self.__file_list.connect('close-file', self.on_file_list_close_file)
        self.__file_list.connect('rename-file', self.on_file_list_rename_file)
        self.__file_list.connect('delete-file', self.on_file_list_delete_file)

        hpaned.pack2(self.nb_widget, resize=True)

        self.nb_widget.set_scrollable(True)

    def _add_editor(self, editor):
        # Set first since _add_editor() calls _update_editor_title()
        editor._notebook_tab_label = gtk.Label()
        editor._notebook_tab_status = gtk.Image()
        editor._notebook_tab_status.props.icon_size = gtk.ICON_SIZE_MENU
        BaseNotebookWindow._add_editor(self, editor)

        label_widget = gtk.HBox(False, 4)
        label_widget.pack_start(editor._notebook_tab_status, True, True, 0)
        label_widget.pack_start(editor._notebook_tab_label, True, True, 0)
        tab_button = gtk.Button()
        tab_button.set_name('notebook-close-button')
        tab_button.set_relief(gtk.RELIEF_NONE)
        tab_button.props.can_focus = False
        tab_button.connect('clicked', lambda *args: self.on_tab_close_button_clicked(editor))
        label_widget.pack_start(tab_button, False, False, 0)
        close = gtk.image_new_from_stock('gtk-close', gtk.ICON_SIZE_MENU)
        tab_button.add(close)
        label_widget.show_all()

        self.nb_widget.set_tab_label(editor.widget, label_widget)

        self.nb_widget.set_tab_reorderable(editor.widget, True)

    def _update_editor_title(self, editor):
        BaseNotebookWindow._update_editor_title(self, editor)
        editor._notebook_tab_label.set_text(editor.title)

    def _update_editor_state(self, editor):
        BaseNotebookWindow._update_editor_state(self, editor)
        editor._notebook_tab_status.props.stock = NotebookFile.stock_id_for_state(editor.state)

    #######################################################
    # Callbacks
    #######################################################

    def on_tab_close_button_clicked(self, editor):
        self._close_editor(editor)

    def on_file_list_open_file(self, file_list, file):
        self.open_file(file)

    def on_file_list_close_file(self, file_list, file):
        for editor in self.editors:
            if editor.file == file:
                self._close_editor(editor)

    def on_file_list_rename_file(self, file_list, file):
        if file.active:
            # If we have the file open, we need to rename via the editor
            for editor in self.editors:
                if editor.file == file:
                    editor.rename()
                # Reselect the new item in the list
                new_file = self.notebook.file_for_absolute_path(editor.filename)
                file_list.select_file(new_file)
        else:
            # Otherwise do it directly
            def check_name(name):
                return name != "" and name != file.path

            def do_rename(new_path):
                old_path = os.path.join(self.notebook.folder, file.path)
                os.rename(old_path, new_path)
                self.notebook.refresh()

                # Reselect the new item in the list
                new_file = self.notebook.file_for_absolute_path(new_path)
                file_list.select_file(new_file)

            title = "Rename '%s'" % file.path
            builder = SaveFileBuilder(title, file.path, "Rename", check_name)
            builder.dialog.set_transient_for(self.window)
            builder.name_entry.set_text(file.path)

            if isinstance(file, WorksheetFile):
                extension = "rws"
            elif isinstance(file, LibraryFile):
                extension = "py"
            else:
                extension = ""

            builder.prompt_for_name(self.notebook.folder, extension, do_rename)
            builder.dialog.destroy()

    def on_file_list_delete_file(self, file_list, file):
        dialog = gtk.MessageDialog(parent=self.window, buttons=gtk.BUTTONS_NONE,
                                   type=gtk.MESSAGE_WARNING)
        message = format_escaped("<big><b>Really delete '%s'?</b></big>", file.path)
        dialog.set_markup(message)

        dialog.add_buttons(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                           gtk.STOCK_DELETE, gtk.RESPONSE_OK)
        dialog.set_default_response(gtk.RESPONSE_CANCEL)
        response = dialog.run()
        dialog.destroy()

        if response != gtk.RESPONSE_OK:
            return

        for editor in self.editors:
            if editor.file == file:
                self._close_editor(editor)

        abspath = os.path.join(self.notebook.folder, file.path)
        os.remove(abspath)
        self.notebook.refresh()

    def on_hpaned_notify_position(self, pane, gparamspec):
        self.state.set_pane_position(pane.get_property('position'))
