# Copyright 2008-2009 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################
#
# The global application object; it from global_settings because it handles tracking
# the user interface objects of the current session, rather than global options and
# preferences.

import gtk
import re
import os
import sys

# SEE BOTTOM OF FILE FOR MOST LOCAL IMPORTS
#
# Done that way to allow 'from Application import application'
# We'll have to rethink this if we ever statically compile reinteract

from application_state import ApplicationState
from global_settings import global_settings

class Application():
    def __init__(self):
        self.__unsaved_indices = []
        self.windows = set()
        self.__about_dialog = None

        config_folder = global_settings.config_dir
        if not os.path.exists(config_folder):
            os.makedirs(config_folder)

        state_location = os.path.join(config_folder, 'reinteract.state')
        self.state = ApplicationState(state_location)

    def get_notebook_infos(self):
        paths = []

        recent = self.state.get_recent_notebooks()
        notebooks_dir = global_settings.notebooks_dir
        recent_paths = [os.path.abspath(r.path) for r in recent]
        folder_paths = [os.path.join(notebooks_dir, f) for f in os.listdir(notebooks_dir)]
        paths = recent_paths + folder_paths

        example_state = self.state.get_notebook_state(global_settings.examples_dir)
        if example_state.get_last_opened() == -1:
            paths.append(global_settings.examples_dir)
        paths = [p for p in paths if os.path.isdir(p)]
        paths = list(set((os.path.normpath(path) for path in paths)))

        return [NotebookInfo(p) for p in paths]

    def __make_notebook_window(self, notebook):
        if global_settings.mini_mode:
            global MiniWindow
            from mini_window import MiniWindow
            return MiniWindow(notebook)
        else:
            global NotebookWindow
            from notebook_window import NotebookWindow
            return NotebookWindow(notebook)

    def open_notebook(self, path):
        for window in self.windows:
            if window.path == path:
                window.window.present()
                return window

        notebook = Notebook(path)
        window = self.__make_notebook_window(notebook)
        window.show()
        self.windows.add(window)

        self.state.notebook_opened(path)

        return window

    def find_notebook_path(self, path):
        # Given a path, possibly inside a notebook, find the notebook and the relative
        # path of the notebook inside the file
        relative = None
        tmp = path
        while True:
            if os.path.isdir(tmp):
                if os.path.exists(os.path.join(tmp, "index.rnb")):
                    return tmp, relative
            parent, basename = os.path.split(tmp)
            if parent == tmp: # At the root
                # As a transition thing, for now allow specifying a folder without
                # an index.rnb as a folder
                if os.path.isdir(path):
                    return path, None
                else:
                    return None, None

            tmp = parent
            if relative is None:
                relative = basename
            else:
                relative = os.path.join(basename, relative)

        return tmp, relative

    def open_path(self, path):
        """Figure out what path points to, and open it appropriately"""

        absolute = os.path.abspath(path)
        basename, dirname = os.path.split(absolute)

        if basename.lower() == "index.rnb":
            notebook_path, relative = dirname, None
        else:
            notebook_path, relative = self.find_notebook_path(absolute)

        if notebook_path:
            window = self.open_notebook(notebook_path)
            if relative and relative in window.notebook.files:
                window.open_file(window.notebook.files[relative])
        else:
            global EditorWindow
            from editor_window import EditorWindow

            window = EditorWindow()
            if not window.load(absolute):
                window.window.destroy()
                return False

            window.show()
            self.windows.add(window)

        return True

    def create_notebook(self, path, description=None):
        os.makedirs(path)
        notebook = Notebook(path)
        if description is not None:
            notebook.info.description = description
        window = self.__make_notebook_window(notebook)
        window.show()
        self.windows.add(window)

        self.state.notebook_opened(path)

        return window

    def create_notebook_dialog(self, parent=None):
        return new_notebook.run(parent)

    def open_notebook_dialog(self, parent=None):
        return open_notebook.run(parent)

    def on_about_dialog_destroy(self, dialog):
        self.__about_dialog = None

    def show_about_dialog(self, parent=None):
        if not self.__about_dialog:
            self.__about_dialog = AboutDialog()
            self.__about_dialog.connect("destroy", self.on_about_dialog_destroy)

        self.__about_dialog.set_transient_for(parent)
        self.__about_dialog.present()

    def quit(self):
        for window in self.windows:
            if not window.confirm_discard():
                return

        self.state.flush()
        gtk.main_quit()

    def window_closed(self, window):
        self.windows.remove(window)
        if not global_settings.main_menu_mode and len(self.windows) == 0:
            self.quit()

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

from about_dialog import AboutDialog
from notebook import Notebook
from notebook_info import NotebookInfo
import new_notebook
import open_notebook

if global_settings.main_menu_mode:
    from main_menu import main_menu
