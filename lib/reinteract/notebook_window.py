import gtk

from base_notebook_window import BaseNotebookWindow
from file_list import FileList
from notebook import NotebookFile

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
        hpaned.set_position(200)
        self.main_vbox.pack_start(hpaned, expand=True, fill=True)

        scrolled_window = gtk.ScrolledWindow()
        scrolled_window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        hpaned.pack1(scrolled_window, resize=False)

        self.__file_list = FileList(self.notebook)
        scrolled_window.add(self.__file_list)
        self.__file_list.connect('open-file', self.on_file_list_open_file)

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
