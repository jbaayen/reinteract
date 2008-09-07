import gobject
import gtk
import pango
import re

from application import application
from global_settings import global_settings
from notebook_window import NotebookWindow
from window_builder import WindowBuilder

class OpenNotebookBuilder(WindowBuilder):
    def __init__(self):
        WindowBuilder.__init__(self, 'open-notebook')

        tree = self.notebooks_tree

        self.model = gtk.ListStore(gobject.TYPE_PYOBJECT)

        for info in application.get_notebook_infos():
            iter = self.model.append()
            self.model.set_value(iter, 0, info)

        tree.set_model(self.model)

        ##############################

        name_column = gtk.TreeViewColumn("Name")
        tree.append_column(name_column)

        cell_renderer = gtk.CellRendererText()
        name_column.pack_start(cell_renderer, True)
        name_column.set_cell_data_func(cell_renderer, self.__name_data_func)

        self.model.set_sort_func(0, self.__name_column_sort)
        name_column.set_sort_column_id(0)
        self.model.set_sort_column_id(0, gtk.SORT_ASCENDING)

        ##############################

        description_column = gtk.TreeViewColumn("Description")
        description_column.set_expand(True)
        tree.append_column(description_column)

        cell_renderer = gtk.CellRendererText()
        cell_renderer.props.ellipsize = pango.ELLIPSIZE_END
        description_column.pack_start(cell_renderer, True)
        description_column.set_cell_data_func(cell_renderer, self.__description_data_func)

        ##############################

        modified_column = gtk.TreeViewColumn("Last Modified")
        tree.append_column(modified_column)

        cell_renderer = gtk.CellRendererText()
        modified_column.pack_start(cell_renderer, True)
        modified_column.set_cell_data_func(cell_renderer, self.__modified_data_func)

        self.model.set_sort_func(2, self.__modified_column_sort)
        modified_column.set_sort_column_id(2)

        ##############################

        tree.get_selection().connect('changed', self.__update_open_button_sensitivity)
        self.__update_open_button_sensitivity()

        tree.connect('row-activated', self.on_row_activated)

    def __name_data_func(self, column, cell, model, iter):
        info = model.get_value(iter, 0)
        cell.props.text = info.name

        # This is a very inefficient thing to do in a cell-data func, but we assume
        # that the number of open windows is very small
        already_open = False
        for window in application.windows:
            if isinstance(window, NotebookWindow) and window.notebook.folder == info.folder:
                already_open = True

        if already_open:
            cell.props.weight = pango.WEIGHT_BOLD
        else:
            cell.props.weight_set = False

    def __name_column_sort(self, model, iter_a, iter_b):
        a = model.get_value(iter_a, 0)
        b = model.get_value(iter_b, 0)
        return cmp(a.name, b.name)

    def __description_data_func(self, column, cell, model, iter):
        info = model.get_value(iter, 0)
        # The short description is the description up to the first newline or
        # up to the first "sentence end" if that comes first
        description = re.sub(r"(.*?)(\n|\r|(<=\.)\s)(.*)", r"\1", info.description)
        cell.props.text = description

    def __modified_data_func(self, column, cell, model, iter):
        info = model.get_value(iter, 0)
        cell.props.text = info.last_modified_text

    def __modified_column_sort(self, model, iter_a, iter_b):
        a = model.get_value(iter_a, 0)
        b = model.get_value(iter_b, 0)
        return - cmp(a.last_modified, b.last_modified)

    def __update_open_button_sensitivity(self, *args):
        self.open_button.set_sensitive(self.get_selected_info() != None)

    def on_row_activated(self, tree_view, path, column):
        self.dialog.response(gtk.RESPONSE_OK)

    def get_selected_info(self):
        model, selected = self.notebooks_tree.get_selection().get_selected()
        if selected:
            return model.get_value(selected, 0)
        else:
            return None

def run(parent=None):
    builder = OpenNotebookBuilder()
    builder.dialog.set_transient_for(parent)
    result_window = None

    while True:
        response = builder.dialog.run()
        if response == 0: # gtk-builder-convert puts check/radio buttons in action-widgets
            continue

        if response == gtk.RESPONSE_OK:
            # We have to hide the modal dialog, or with metacity the new window pops at the back
            builder.dialog.hide()
            selected_info = builder.get_selected_info()
            result_window = application.open_notebook(selected_info.folder)
        elif response == 1: # Browse...
            if global_settings.use_hildon:
                import hildon
                chooser = hildon.FileChooserDialog(parent, gtk.FILE_CHOOSER_ACTION_OPEN)
            else:
                chooser = gtk.FileChooserDialog("Open Notebook...", parent, gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                                                (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                                 gtk.STOCK_OPEN,   gtk.RESPONSE_OK))
            chooser.set_default_response(gtk.RESPONSE_OK)

            response = chooser.run()
            if response == gtk.RESPONSE_OK:
                filename = chooser.get_filename()
                result_window = application.open_notebook(filename)

            chooser.destroy()

        break

    builder.dialog.destroy()
    return result_window
