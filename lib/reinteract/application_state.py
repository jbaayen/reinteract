# Copyright 2008 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import gobject
import os
import re
import time

_brackets_re = re.compile(r'([\]\[])')

from notebook_info import format_duration
from config_file import ConfigFile

def _hex_escape(s, unsafe_re):
    return unsafe_re.sub(lambda x: '%%%02x' % ord(x.group(1)), s)

def _section_name(path):
    return _hex_escape(path, _brackets_re)

class NotebookState:
    def __init__(self, app_state, path):
        self.path = path
        self.app_state = app_state
        self.section_name = _section_name(path)

    def get_open_files(self):
        return self.app_state.get_list(self.section_name, 'open_files', [])

    def get_last_opened(self):
        return self.app_state.get_float(self.section_name, 'last_opened', -1)

    def get_last_opened_text(self):
        return format_duration(self.get_last_opened())

    def get_current_file(self):
        value = self.app_state.get_string(self.section_name, 'current_file')

    def get_size(self):
        width = self.app_state.get_int(self.section_name, 'width', -1)
        height = self.app_state.get_int(self.section_name, 'height', -1)

        return (width, height)

    def get_pane_position(self):
        return self.app_state.get_int(self.section_name, 'pane_position', -1)

    def set_open_files(self, files):
        self.app_state.set_list(self.section_name, 'open_files', files)

    def set_current_file(self, file):
        if file:
            self.app_state.set_string(self.section_name, 'current_file', file)
        else:
            self.app_state.remove_option(self.section_name, 'current_file')

    def set_size(self, width, height):
        self.app_state.set_int(self.section_name, 'width', width)
        self.app_state.set_int(self.section_name, 'height', height)

    def set_pane_position(self, position):
        self.app_state.set_int(self.section_name, 'pane_position', position)

    def update_last_opened(self):
        self.app_state.set_float(self.section_name, 'last_opened', time.time())

class ApplicationState(ConfigFile):
    def __init__(self, location):
        ConfigFile.__init__(self, location)
        self.notebook_states = {}

    def __get_recent_notebook_paths(self):
        return self.get_list('Reinteract', 'recent_notebooks', [])

    def notebook_opened(self, path):
        nb_state = self.get_notebook_state(path)
        nb_state.update_last_opened()

        old_paths = self.__get_recent_notebook_paths()
        try:
            old_paths.remove(path)
        except ValueError:
            pass
        old_paths.insert(0, path)

        self.set_list('Reinteract', 'recent_notebooks', old_paths)

    def get_recent_notebooks(self, max_count=10):
        paths = self.__get_recent_notebook_paths()
        if max_count >= 0:
            paths = paths[0:max_count]

        return [self.get_notebook_state(path) for path in paths]

    def get_notebook_state(self, path):
        if not path in self.notebook_states:
            self.notebook_states[path] = NotebookState(self, path)

        return self.notebook_states[path]

######################################################################

if __name__ == '__main__': #pragma: no cover
    import tempfile
    from test_utils import assert_equals

    def test_section_name(path, expected):
        section_name = _section_name(path)
        assert_equals(section_name, expected)

    test_section_name('C:\foo', 'C:\foo')
    test_section_name('foo[]', 'foo%5b%5d')

    ######

    f, location = tempfile.mkstemp(".state", "reinteract")
    os.close(f)
    try:
        nb_path = "C:\\Foo\\Bar"

        application_state = ApplicationState(location)
        application_state.notebook_opened(nb_path)
        nb_state = application_state.get_notebook_state(nb_path)
        nb_state.set_open_files(["foo.rws", "bar.rws"])
        application_state.flush()

        application_state = ApplicationState(location)

        recent_notebooks = application_state.get_recent_notebooks()
        assert_equals(len(recent_notebooks), 1)
        assert_equals(recent_notebooks[0].path, nb_path)

        nb_state = application_state.get_notebook_state(nb_path)
        assert nb_state.get_last_opened() > 0
        assert_equals(nb_state.get_open_files(), ["foo.rws", "bar.rws"])

    finally:
        try:
            os.remove(location)
        except:
            pass
