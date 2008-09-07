from ConfigParser import RawConfigParser, ParsingError, NoOptionError, NoSectionError
import gobject
import os
import re
import time

_FLUSH_INTERVAL = 1000 # 1 second

_need_quote_re = re.compile(r'[\s"]');
_backslash_re = re.compile(r'(\\)')
_backslash_quote_re = re.compile(r'([\\"])')
_unescape_re = re.compile(r'\\(.)')
_list_item_re = re.compile(r'"(?:[^\\\"]+|\\.)*"|[^\s"]+')
_brackets_re = re.compile(r'([\]\[])')

def _escape(s, unsafe_re):
    return unsafe_re.sub(r'\\\1', s)

def _unescape(s):
    return _unescape_re.sub(r'\1', s)

def _quote(s):
    if s == "" or _need_quote_re.search(s):
        return '"' + _escape(s, _backslash_quote_re) + '"'
    else:
        return _escape(s, _backslash_re)

def _unquote(s):
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return _unescape(s[1:-1])
    else:
        return _unescape(s)

def _quote_list(l):
    return " ".join((_quote(x) for x in l))

def _unquote_list(s):
    return [_unquote(x.group(0)) for x in _list_item_re.finditer(s)]

def _hex_escape(s, unsafe_re):
    return unsafe_re.sub(lambda x: '%%%02x' % ord(x.group(1)), s)

def _section_name(path):
    return _hex_escape(path, _brackets_re)

class NotebookState:
    def __init__(self, app_state, path):
        self.path = path
        self.app_state = app_state
        self.section_name = _section_name(path)

    def __ensure_section(self):
        if not self.app_state.parser.has_section(self.section_name):
            self.app_state.parser.add_section(self.section_name)

    def get_open_files(self):
        try:
            return _unquote_list(self.app_state.parser.get(self.section_name, 'open_files'))
        except NoOptionError:
            return []
        except NoSectionError:
            return []

        return _unquote_list(s)

    def get_last_opened(self):
        try:
            return self.app_state.parser.getfloat(self.section_name, 'last_opened')
        except NoOptionError:
            return -1
        except NoSectionError:
            return -1

    def get_current_file(self):
        try:
            return _unquote(self.app_state.parser.get(self.section_name, 'current_file'))
        except NoOptionError:
            return None
        except NoSectionError:
            return None

    def set_open_files(self, files):
        self.__ensure_section()
        self.app_state.parser.set(self.section_name, 'open_files', _quote_list(files))
        self.app_state.queue_flush()

    def set_current_file(self, file):
        self.__ensure_section()
        if file:
            self.app_state.parser.set(self.section_name, 'current_file', _quote(file))
        else:
            self.app_state.parser.remove_option(self.section_name, 'current_file')
        self.app_state.queue_flush()

    def update_last_opened(self):
        self.__ensure_section()
        self.app_state.parser.set(self.section_name, 'last_opened', str(time.time()))
        self.app_state.queue_flush()

class ApplicationState:
    def __init__(self, location):
        self.location = location
        self.flush_timeout = 0
        self.parser = RawConfigParser()
        self.notebook_states = {}

        try:
            f = open(location, "r")
        except IOError, e:
            # If not readable, just ignore
            return

        try:
            self.parser.readfp(f)
        except ParsingError:
            # If not readable, just ignore
            return
        finally:
            f.close()

    def __ensure_section(self):
        if not self.parser.has_section('Reinteract'):
            self.parser.add_section('Reinteract')

    def __get_recent_notebook_paths(self):
        try:
            s = self.parser.get('Reinteract', 'recent_notebooks')
        except NoOptionError:
            return []
        except NoSectionError:
            return []

        return _unquote_list(s)

    def notebook_opened(self, path):
        nb_state = self.get_notebook_state(path)
        nb_state.update_last_opened()

        old_paths = self.__get_recent_notebook_paths()
        try:
            old_paths.remove(path)
        except ValueError:
            pass
        old_paths.insert(0, path)

        self.__ensure_section()
        self.parser.set('Reinteract', 'recent_notebooks', _quote_list(old_paths))

        self.queue_flush()

    def get_recent_notebooks(self, max_count=10):
        paths = self.__get_recent_notebook_paths()
        if max_count >= 0:
            paths = paths[0:max_count]

        return [self.get_notebook_state(path) for path in paths]

    def get_notebook_state(self, path):
        if not path in self.notebook_states:
            self.notebook_states[path] = NotebookState(self, path)

        return self.notebook_states[path]

    def flush(self):
        if self.flush_timeout != 0:
            gobject.source_remove(self.flush_timeout)
            self.flush_timeout = 0

        tmpname = self.location + ".tmp"
        f = open(tmpname, "w")
        success = False
        try:
            self.parser.write(f)
            f.close()
            if os.path.exists(self.location):
                os.remove(self.location)
            os.rename(tmpname, self.location)
            success = True
        finally:
            if not success:
                f.close()
                try:
                    os.remove(tmpname)
                except:
                    pass

    def queue_flush(self):
        if self.flush_timeout == 0:
            self.flush_timeout = gobject.timeout_add(_FLUSH_INTERVAL, self.flush)

######################################################################

if __name__ == '__main__': #pragma: no cover
    import tempfile
    from test_utils import assert_equals

    def test_quote(s, expected):
        quoted = _quote(s)
        assert_equals(quoted, expected)
        unquoted = _unquote(quoted)
        assert_equals(unquoted, s)

    test_quote(r'',  r'""')
    test_quote(r'foo',  r'foo')
    test_quote(r'fo"o', r'"fo\"o"')
    test_quote(r'fo o', r'"fo o"')
    test_quote(r'fo\o', r'fo\\o')

    def test_quote_list(l, expected):
        quoted = _quote_list(l)
        assert_equals(quoted, expected)
        unquoted = _unquote_list(quoted)
        assert_equals(unquoted, l)

    test_quote_list(['foo'], 'foo')
    test_quote_list(['foo bar'], '"foo bar"')
    test_quote_list(['foo', 'bar'], 'foo bar')
    test_quote_list(['foo', 'bar baz'], 'foo "bar baz"')

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
