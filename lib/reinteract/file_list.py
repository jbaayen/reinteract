import gobject
import gtk
import logging
import os
import pango

from notebook import Notebook, NotebookFile, WorksheetFile, MiscFile, LibraryFile

_debug = logging.getLogger("FileList").debug

######################################################################
# Basic sorting primitives: paths and classes of files
######################################################################

def _split_path(path):
    # Break a relative filesystem path into components
    result = []
    while True:
        dirname, basename = os.path.split(path)
        result.append(basename)
        if dirname == '':
            break
        path = dirname

    result.reverse()
    return result

def _collate(a, b):
    # Crappy 'collation' ... ignore case unless the two names match in case
    c = cmp(a.lower(), b.lower())
    if c != 0:
        return c
    return cmp(a, b)

def _compare_paths(a, b):
    # Compare two relative paths lexicographically by component
    for f_a,f_b in zip(_split_path(a), _split_path(b)):
        c = _collate(f_a, f_b)
        if c != 0:
            return c

    return cmp(len(a), len(b))

_file_class_order = {}
_file_class_order[WorksheetFile] = 0
_file_class_order[LibraryFile] = 1
_file_class_order[MiscFile] = 2

def _compare_files(file_a, file_b):
    c = cmp(_file_class_order[file_a.__class__], _file_class_order[file_b.__class__])
    if c != 0:
        return c

    return _compare_paths(file_a.path, file_b.path)

######################################################################
# Classes for the items in the list
######################################################################

class _Item:
    def get_text(self):
        return os.path.basename(self.path)

    def __cmp__(self, other):
        c = cmp(_file_class_order[self.klass], _file_class_order[other.klass])
        if c != 0:
            return c

        c = _compare_paths(self.path, other.path)
        if c != 0:
            return c

        # This is to keep a file and folder with the same path from looking identical
        # ordering is arbitrary
        return cmp(self.__class__.__name__, other.__class__.__name__)

class _FileItem(_Item):
    def __init__(self, file):
        self.file = file
        self.path = file.path
        self.klass = file.__class__

    def get_text(self):
        name = _Item.get_text(self)
        if self.file.modified:
            return "*" + name
        else:
            return name

class _FolderItem(_Item):
    def __init__(self, path, klass):
        self.path = path
        self.klass = klass

class _HeaderItem(_Item):
    def __init__(self, klass):
        # Using a path of '' means it will sort before all the other items of the same class
        self.path = ''
        self.klass = klass

    def get_text(self):
        if self.klass == WorksheetFile:
            return "Worksheets"
        elif self.klass == LibraryFile:
            return "Libraries"
        else:
            return "Other Files"

######################################################################
# Tree view utility
######################################################################

def _next_row_depthfirst(model, iter):
    # Return the next row after a row in depth-first order

    if model.iter_has_child(iter):
        return model.iter_children(iter)

    while iter != None:
        next = model.iter_next(iter)
        if next != None:
            return next

        iter = model.iter_parent(iter)

    return None

def _remove_row_depthfirst(model, iter):
    # Remove a row and returns an iterator to the next row in depth-first order.
    # (This implementation depends on the TreeStore being "iters_persist")

    parent = model.iter_parent(iter)
    if model.remove(iter):
        return iter

    while parent != None:
        next = model.iter_next(parent)
        if next != None:
            return next

        parent = model.iter_parent(parent)

    return None

######################################################################

class FileList(gtk.TreeView):
    __gsignals__ = {
        'open-file':  (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        'row-activated':  'override',
        'destroy': 'override'
    }

    def __init__(self, notebook):
        self.__model = gtk.TreeStore(gobject.TYPE_PYOBJECT)
        gtk.TreeView.__init__(self, self.__model)
        self.notebook = notebook
        self.__files_changed_handler = self.notebook.connect('files-changed', self.on_files_changed)

        column = gtk.TreeViewColumn()
        self.append_column(column)

        cell_renderer = gtk.CellRendererText()
        column.pack_start(cell_renderer, True)
        column.set_cell_data_func(cell_renderer, self.__filename_cell_data_func)

        self.set_headers_visible(False)
        self.get_selection().set_select_function(self.__select_function)

        self.__rescan()

    def do_destroy(self):
        iter = self.__model.get_iter_first()
        while iter:
            item = self.__model.get_value(iter, 0)
            self.__disconnect_item(item)
            iter = _next_row_depthfirst(self.__model, iter)

        self.notebook.disconnect(self.__files_changed_handler)

    def do_row_activated(self, path, column):
        iter = self.__model.get_iter(path)
        item = self.__model.get_value(iter, 0)
        if isinstance(item, _FileItem):
            self.emit('open-file', item.file)

    def __filename_cell_data_func(self, column, cell, model, iter):
        item = model.get_value(iter, 0)
        cell.props.text = item.get_text()

        if isinstance(item, _HeaderItem):
            cell.props.background_gdk = gtk.gdk.Color(0xffff,0xdddd,0xbbbb)
        else:
            cell.props.background_set = False

        if isinstance(item, _FileItem) and item.file.active:
            cell.props.weight = pango.WEIGHT_BOLD
        else:
            cell.props.weight_set = False

    def __select_function(self, path):
        obj = self.__model.get_value(self.__model.get_iter(path), 0)
        return isinstance(obj, _FileItem)

    ############################################################

    def __iter_for_item(self, item):
        iter = self.__model.get_iter_first()
        while iter:
            row_item = self.__model.get_value(iter, 0)
            if row_item == item:
                return iter
            iter = _next_row_depthfirst(self.__model, iter)

        return None

    def __refresh_item(self, item):
        iter = self.__iter_for_item(item)
        path = self.__model.get_path(iter)
        self.__model.row_changed(path, iter)

    def __connect_item(self, item):
        if isinstance(item, _FileItem):
            item.notify_active_handler = item.file.connect('notify::active',
                                                           lambda *args: self.__refresh_item(item))
            item.notify_modified_handler = item.file.connect('notify::modified',
                                                             lambda *args: self.__refresh_item(item))
            item.worksheet = None
            item.notify_code_modified_handler = 0

    def __disconnect_item(self, item):
        if isinstance(item, _FileItem):
            item.file.disconnect(item.notify_active_handler)
            item.notify_active_handler = None
            item.file.disconnect(item.notify_modified_handler)
            item.notify_modified_handler = None

    ############################################################

    def __iter_items(self):
        # Generator yielding all the items to display in the list in order
        klass = None
        path = []
        for file in sorted(self.notebook.files.values(), _compare_files):
            if file.__class__ != klass:
                klass = file.__class__
                path = []
                yield (_HeaderItem(file.__class__), len(path))

            new_path = _split_path(file.path)[0:-1]
            while len(path) > len(new_path) or (len(path) > 0 and path[len(path) - 1] != new_path[len(path) - 1]):
                path.pop()

            while len(new_path) > len(path):
                folder_name = new_path[len(path)]
                path.append(folder_name)
                yield (_FolderItem(os.path.join(*new_path[0:len(path)]), klass), len(path) - 1)

            yield (_FileItem(file), len(path))

    def __rescan(self):
        #
        # Compare the items that should be in the list (from __iter_items) with the items that are
        # currently in the list, insert missing items, and remove items that no longer in the list.
        # We go through quite a bit of trouble here to make the minimal set of inserts and removals
        # rather than just starting over from scratch to avoid problems with scroll position,
        # selection, and expanded state that will occur if we delete everything and add them again.
        # Efficiency is not the main concern.
        #
        depth = 0
        parent = None
        next_old = self.__model.get_iter_first()
        seen_folders = False
        for (item, new_depth) in self.__iter_items():
            # Delete old items that are logically before the next item
            found_item = False
            while next_old != None:
                old_item = self.__model.get_value(next_old, 0)
                c = cmp(item, old_item)
                if c < 0:
                    break
                elif c == 0:
                    found_item = True
                    iter = next_old
                    next_old = _next_row_depthfirst(self.__model, next_old)
                    break
                else:
                    next_parent = self.__model.iter_parent(next_old)
                    _debug("Removing %s", old_item.get_text())
                    next_old = _remove_row_depthfirst(self.__model, next_old)
                    self.__disconnect_item(next_old)

            while new_depth < depth:
                parent = self.__model.iter_parent(parent)
                depth -= 1

            if not found_item:
                if next_old:
                    _debug("Inserting %s before %s", item.get_text(), self.__model.get_value(next_old, 0).get_text())
                else:
                    _debug("Appending %s", item.get_text())

                next = None
                if next_old:
                    if parent:
                        parent_path = self.__model.get_path(parent)
                    else:
                        parent_path = ()
                    if self.__model.get_path(next_old)[0:-1] == parent_path:
                        next = next_old
                iter = self.__model.insert_before(parent, next)
                self.__model.set_value(iter, 0, item)
                self.__connect_item(item)
                next_old = _next_row_depthfirst(self.__model, iter)

            if isinstance(item, _FolderItem):
                seen_folders = True
                parent = iter
                depth += 1

        while next_old != None:
            next_old = _remove_row_depthfirst(self.__model, next_old)

        self.set_show_expanders(seen_folders)

    def on_files_changed(self, notebook):
        self.__rescan()

######################################################################

if __name__ == '__main__': #pragma: no cover
    import sys

    if "-d" in sys.argv:
        logging.basicConfig(level=logging.DEBUG, format="DEBUG: %(message)s")

    def expect_split_path(p, expected):
        if _split_path(p) != expected:
            raise AssertionError("For %r got %s expected %s" % (p, _split_path(p), expected))

    expect_split_path("", [""])
    expect_split_path("a", ["a"])
    expect_split_path("a/b", ["a", "b"])

    def expect_compare_paths(a, b, expected):
        if _compare_paths(a, b) != expected:
            raise AssertionError("For %r <=> %r got %s expected %s" % (a, b, _compare_paths(a, b), expected))

        if _compare_paths(b, a) != - expected:
            raise AssertionError("For %r <=> %r got %s expected %s" % (a, b, _compare_paths(b, a), - expected))

    expect_compare_paths("a", "a", 0)
    expect_compare_paths("a", "b", -1)
    expect_compare_paths("a", "a/b", -1)
    expect_compare_paths("a/a", "a/b", -1)
    expect_compare_paths("a/b", "a/b", 0)

    import tempfile

    notebook_folder = tempfile.mkdtemp("", "reinteract_notebook.")

    def make_folder(relative):
        absolute = os.path.join(notebook_folder, relative)
        os.mkdir(absolute)

    def make_file(relative):
        absolute = os.path.join(notebook_folder, relative)
        open(absolute, 'w').close()

    def remove(relative=None):
        if relative:
            absolute = os.path.join(notebook_folder, relative)
        else:
            absolute = notebook_folder

        if os.path.isdir(absolute):
            for root, dirs, files in os.walk(absolute, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))

            os.rmdir(absolute)
        else:
            os.remove(absolute)

    try:
        make_folder("subdir")

        make_file("worksheet_a.rws")
        make_file("subdir/worksheet_c.rws")

        make_file("library_a.py")
        make_file("subdir/library_b.py")

        notebook = Notebook(notebook_folder)
        file_list = FileList(notebook)

        def expect(*expected_items):
            items = []
            model = file_list.get_model()
            iter = model.get_iter_first()
            while iter:
                depth = len(model.get_path(iter)) - 1
                items.append((">" * depth) + model.get_value(iter, 0).get_text())
                iter = _next_row_depthfirst(model, iter)

            if items != list(expected_items):
                raise AssertionError("Got %s expected %s" % (items, expected_items))

        expect("Worksheets",
               "subdir",
               ">worksheet_c.rws",
               "worksheet_a.rws",
               "Libraries",
               "library_a.py",
               "subdir",
               ">library_b.py")

        remove("subdir/worksheet_c.rws")
        notebook.refresh()

        expect("Worksheets",
               "worksheet_a.rws",
               "Libraries",
               "library_a.py",
               "subdir",
               ">library_b.py")

        make_folder("subdir/subsubdir")
        make_file("subdir/subsubdir/misc.txt")
        notebook.refresh()

        expect("Worksheets",
               "worksheet_a.rws",
               "Libraries",
               "library_a.py",
               "subdir",
               ">library_b.py",
               "Other Files",
               "subdir",
               ">subsubdir",
               ">>misc.txt")

        # Test insertion where the next item is at the toplevel
        make_file("worksheet_b.rws")
        notebook.refresh()

        expect("Worksheets",
               "worksheet_a.rws",
               "worksheet_b.rws",
               "Libraries",
               "library_a.py",
               "subdir",
               ">library_b.py",
               "Other Files",
               "subdir",
               ">subsubdir",
               ">>misc.txt")

        # Test insertion where the next item is at the same sublevel
        make_file("subdir/library_0.py")
        notebook.refresh()

        expect("Worksheets",
               "worksheet_a.rws",
               "worksheet_b.rws",
               "Libraries",
               "library_a.py",
               "subdir",
               ">library_0.py",
               ">library_b.py",
               "Other Files",
               "subdir",
               ">subsubdir",
               ">>misc.txt")

        # Test insertion where the next item is at a lower level
        make_file("subdir/library_c.py")
        notebook.refresh()

        expect("Worksheets",
               "worksheet_a.rws",
               "worksheet_b.rws",
               "Libraries",
               "library_a.py",
               "subdir",
               ">library_0.py",
               ">library_b.py",
               ">library_c.py",
               "Other Files",
               "subdir",
               ">subsubdir",
               ">>misc.txt")

        # Test a removal where the next row is at a lower level
        remove("subdir/library_c.py")
        notebook.refresh()

        expect("Worksheets",
               "worksheet_a.rws",
               "worksheet_b.rws",
               "Libraries",
               "library_a.py",
               "subdir",
               ">library_0.py",
               ">library_b.py",
               "Other Files",
               "subdir",
               ">subsubdir",
               ">>misc.txt")

        # Test a removal of trailing items
        make_file("subdir/aaa.txt")
        remove("subdir/subsubdir/misc.txt")
        notebook.refresh()

        expect("Worksheets",
               "worksheet_a.rws",
               "worksheet_b.rws",
               "Libraries",
               "library_a.py",
               "subdir",
               ">library_0.py",
               ">library_b.py",
               "Other Files",
               "subdir",
               ">aaa.txt")

        remove("library_a.py")
        remove("subdir/library_0.py")
        remove("subdir/library_b.py")
        notebook.refresh()

        expect("Worksheets",
               "worksheet_a.rws",
               "worksheet_b.rws",
               "Other Files",
               "subdir",
               ">aaa.txt")

    finally:
        remove()

    file_list.destroy()
