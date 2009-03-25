# Copyright 2008-2009 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

from ConfigParser import RawConfigParser, ParsingError, NoOptionError, NoSectionError
import gobject
import os
import re

_FLUSH_INTERVAL = 1000 # 1 second

_need_quote_re = re.compile(r'[\s"]');
_backslash_re = re.compile(r'(\\)')
_backslash_quote_re = re.compile(r'([\\"])')
_unescape_re = re.compile(r'\\(.)')
_list_item_re = re.compile(r'"(?:[^\\\"]+|\\.)*"|[^\s"]+')

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

class ConfigFile(object):
    """Class to load and store configuration and state infomration from an .INI-style file

    ConfigFile provides a high-evel interface around ConfigParser. It handles loading and
    saving the file (saving is automatically done in a timeout once a modification has been
    made, it auto-creates sections on demand, it handles quoting and has type-specific
    get and set functions with a the provision to pass a default to the get functions.

    """

    def __init__(self, location):
        self.location = location
        self.flush_timeout = 0
        self.parser = RawConfigParser()

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

    def get_float(self, section, option, default=None):
        try:
            return self.parser.getfloat(section, option)
        except NoOptionError:
            return default
        except NoSectionError:
            return default

    def get_int(self, section, option, default=None):
        try:
            return self.parser.getint(section, option)
        except NoOptionError:
            return default
        except NoSectionError:
            return default

    def get_bool(self, section, option, default=None):
        try:
            return self.parser.get(section, option).lower() == 'true'
        except NoOptionError:
            return default
        except NoSectionError:
            return default

    def get_string(self, section, option, default=None):
        try:
            return _unquote(self.parser.get(section, option))
        except NoOptionError:
            return default
        except NoSectionError:
            return default

    def get_list(self, section, option, default=None):
        try:
            return _unquote_list(self.parser.get(section, option))
        except NoOptionError:
            return default
        except NoSectionError:
            return default

    def __set(self, section, option, value):
        if not self.parser.has_section(section):
            self.parser.add_section(section)

        self.parser.set(section, option, value)
        self.queue_flush()

    def set_int(self, section, option, value):
        self.__set(section, option, str(value))

    def set_float(self, section, option, value):
        self.__set(section, option, str(value))

    def set_bool(self, section, option, value):
        self.__set(section, option, str(value))

    def set_string(self, section, option, value):
        self.__set(section, option, _quote(value))

    def set_list(self, section, option, value):
        self.__set(section, option, _quote_list(value))

    def remove_option(self, section, option):
        if self.parser.has_section(section):
            self.parser.remove_option(section, option)
            self.queue_flush()

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
