# The global application object; it from global_settings because it handles tracking
# the user interface objects of the current session, rather than global options and
# preferences.

import gtk
import re
import os
import sys

# SEE BOTTOM OF FILE FOR LOCAL IMPORTS
#
# Done that way to allow 'from Application import application'
# We'll have to rethink this if we ever statically compile reinteract

_VALID_CHAR = re.compile("[A-Za-z0-9._ -]")

class Application():
    def __init__(self):
        self.__unsaved_indices = []
        self.windows = set()

    def get_notebook_infos(self):
        infos = []

        notebooks_folder = self.get_notebooks_folder()
        for f in os.listdir(notebooks_folder):
            fullpath = os.path.join(notebooks_folder, f)
            if not os.path.isdir(fullpath):
                continue

            infos.append(NotebookInfo(fullpath))

        # Wedge the examples notebook into the Open Notebook dialog so people
        # can find it. Longer-term, a possibility:
        #
        # - keep track of the history of recently opened notebooks
        # - include them when listing known notebooks
        # - on first startup, prime that with the examples notebook
        #
        infos.append(NotebookInfo(global_settings.examples_dir))

        return infos

    def get_notebooks_folder(self):
        # In a shocking example of cross-platform convergence, ~/Documents
        # is the documents directory on OS X, Windows, and Linux
        return os.path.expanduser("~/Documents/Reinteract")

    def validate_name(self, name):
        # Remove surrounding whitespace
        name = name.strip()
        if name == "":
            raise ValueError("Name cannot be empty")

        # Replace series of whitespace with a single space
        name = name.replace("\s+", " ")

        bad_chars = set()
        for c in name:
            if not _VALID_CHAR.match(c):
                bad_chars.add(c)

        bad = ", ".join(("'" + c + "'" for c in bad_chars))

        if len(bad_chars) == 1:
            raise ValueError("Name contains invalid character: %s" % bad)
        elif len(bad_chars) > 0:
            raise ValueError("Name contains invalid characters: %s" % bad)

        return name

    def open_notebook(self, path):
        for window in self.windows:
            if isinstance(window, NotebookWindow) and window.notebook.folder == path:
                window.window.present()
                return window

        notebook = Notebook(path)
        window = NotebookWindow(notebook)
        window.show()
        self.windows.add(window)

        return window

    def __find_notebook(self, path):
        # Given a path, possibly inside a notebook, find the notebook and the relative
        # path of the notebook inside the file
        relative = None
        while True:
            if os.path.isdir(path):
                if os.path.exists(os.path.join(path, "index.rnb")):
                    return path, relative
            parent, basename = os.path.split(path)
            if parent == path: # At the root
                return None, None

            path = parent
            if relative == None:
                relative = basename
            else:
                relative = os.path.join(basename, relative)

        return path, relative

    def open_path(self, path):
        """Figure out what path points to, and open it appropriately"""

        absolute = os.path.abspath(path)
        basename, dirname = os.path.split(absolute)

        if basename.lower() == "index.rnb":
            notebook_path, relative = dirname, None
        else:
            notebook_path, relative = self.__find_notebook(absolute)

        if notebook_path:
            window = self.open_notebook(notebook_path)
            if relative and relative in window.notebook.files:
                window.open_file(window.notebook.files[relative])
        else:
            window = WorksheetWindow()
            window.load(absolute)
            window.show()

    def create_notebook(self, path, description=None):
        os.makedirs(path)
        notebook = Notebook(path)
        if description != None:
            notebook.info.description = description
        window = NotebookWindow(notebook)
        window.show()
        self.windows.add(window)

        return window

    def create_notebook_dialog(self, parent=None):
        new_notebook.run(parent)

    def open_notebook_dialog(self, parent=None):
        open_notebook.run(parent)

    def quit(self):
        for window in self.windows:
            if not window.confirm_discard():
                return

        gtk.main_quit()

    def window_closed(self, window):
        self.windows.remove(window)
        if len(self.windows) == 0:
            gtk.main_quit()

    def allocate_unsaved_index(self):
        """Allocate an index to be used when displaying an unsaved object ("Unsaved Worksheet 1")"""

        for i in xrange(0, len(self.__unsaved_indices)):
            if not self.__unsaved_indices[i]:
                self.__unsaved_indices[i] = True
                return i + 1
        self.__unsaved_indices.append(True)
        return len(self.__unsaved_indices)

    def free_unsaved_index(self, index):
        """Free an index previously returned by allocate_unsaved_index()"""

        self.__unsaved_indices[index - 1] = False

# The global singleton
application = Application()

from global_settings import global_settings
from notebook import Notebook
from notebook_info import NotebookInfo
from notebook_window import NotebookWindow
import new_notebook
import open_notebook
