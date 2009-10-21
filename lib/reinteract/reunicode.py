# Copyright 2009 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

# This file handles routines for Unicode manipulation. In particular, it's concern
# for the limitations of the various parties. Valid Unicode characters are the
# range U+0001-U+10ffff, excluding the ranges U+fdd0-U+fdef and U+fffe-U+ffff
# and all characters whose low 16-bits are in the range U+d800-U+dfff.
#
# Python-in UCS-4 mode:
#  Unicode strings can contain any codepoint U+0000-U+10ffff, whether valid
#  or not.
#
# Python-in UCS-2 mode:
#  Unicode strings can contain any codepoint U+0000-0+ffff. When converting from
#  other encodings or from escapes, non-BMP codepoints are converted into surrogate
#  pairs. Unpaired surrogates can also occur.
#
# GTK+:
#  Unicode strings are represented in UTF-8. They must contain only valid characters,
#  and have no embedded NULs.
#
# Trying to handle non-BMP characters with GTK+ and Python in UCS-2 mode is
# pretty hopeless because something like GtkTextView has no ability to index by
# UTF-8 codepoint index, but only by byte index or character offset.
#
# With UCS-4 Python, handling non-BMP characters is more feasible, but we avoid it
# anyways, a) for cross-platform consistency. b) because writing efficient checks
# for validity beyond the BMP in Python is quite difficult.

import re
import sys
import StringIO

# An unsafe character is one outside the range that everybody can handle; we
# escape them in groups so that when we escape them legitimate surrogate pairs
# get represented as \Uxxxxyyyy escapes.
_UNSAFE_CHARACTERS = re.compile(u"[^\u0001-\ud7ff\ue000-\ufdcf\ufdf0-\ufffd]+")

_NON_ASCII_BYTE = re.compile("[\x80-\xff]")

class ConversionError(Exception):
    pass

def _escape(g):
    return g.group(0).encode("unicode_escape").decode()

def _escape_byte(g):
    return "\\x%02x" % ord(g.group(0))

def _decode_escaped(s, encoding):
    # Note that cStringIO wouldn't work here, because it doesn't handle Unicode
    out = StringIO.StringIO()
    pos = 0
    while pos < len(s):
        try:
            out.write(s[pos:].decode("utf8"))
            pos = len(s)
        except UnicodeDecodeError, e:
            out.write(s[pos:pos + e.start].decode("utf8"))
            out.write(_NON_ASCII_BYTE.sub(_escape_byte, s[pos + e.start:pos + e.end]))
            pos += e.end

    return out.getvalue()


def decode(s, encoding="utf8", escape=False):
    """

    @param s the str object to decode into Unicode
    @param encoding the encoding to use (defaults to UTF-8)
    @param escape if True,

    """
    try:
        u = s.decode(encoding)
    except UnicodeDecodeError, e:
        if escape:
            u = _decode_escaped(s, encoding)
        else:
            raise ConversionError(e.reason)

    if escape:
        return escape_unsafe(u)
    else:
        m = _UNSAFE_CHARACTERS.search(u)
        if m:
            # Do a bunch of work here to get an explaination about what is wrong
            c = ord(u[m.start(0)])
            if c == 0:
                raise ConversionError('text contains NUL byte')
            elif c >= 0xd800 and c < 0xe000:
                # Detect non-BMP characters in UCS-2 Python
                if sys.maxunicode == 0xffff and c < 0xdc00:
                    if m.start(0) + 1 < m.end(0):
                        c2 = ord(u[m.start(0) + 1])
                        if c2 >= 0xdc00 and c2 < 0xe000:
                            raise ConversionError('text contains characters not in basic multilingual plane')
                raise ConversionError('text contains unpaired surrogates')
            elif c > 0xffff:
                raise ConversionError('text contains characters not in basic multilingual plane')
            else:
                # Byte reversed BOM, etc.
                raise ConversionError('text contains invalid Unicode codepoints')

        return u

def escape_unsafe(u):
    """Encode any characters in a string that might cause problems for Reinteract
    as \\u<nnnn> or \\U<nnnnnnnn> escape sequences. This includes embedded NULs, characters
    not in the BMP and codepoints that are defined by the Unicode spec as not
    valid characters."""

    return _UNSAFE_CHARACTERS.sub(_escape, u)

######################################################################

if __name__ == '__main__': #pragma: no cover
    from test_utils import assert_equals

    def test_escape_unsafe(u, expected):
        assert_equals(escape_unsafe(u), expected)

    # Embedded NUL is \x00
    test_escape_unsafe(u"a\x00b", u"a\\x00b")
    # Test a tab is left untouched
    test_escape_unsafe(u"\t", u"\t")
    # Non-BMP character (represented as surrogates for UCS-2 python)
    test_escape_unsafe(u"\U00010000", u"\\U00010000")
    # Unpaired surrogate
    test_escape_unsafe(u"\ud800", u"\\ud800")

    def test_decode_escaped(s, expected):
        assert_equals(decode(s, escape=True), expected)

    # Valid UTF-8
    test_decode_escaped(u"\u1234".encode("utf8"), u"\u1234")
    # Invalid UTF-8
    test_decode_escaped("abc\x80\x80abc", u"abc\\x80\\x80abc")
    # Mixture
    test_decode_escaped(u"\u1234".encode("utf8") + "\x80", u"\u1234\\x80")
    # embedded NUL
    test_decode_escaped("\x00", "\\x00")

    # Test a non-UTF-8 encoding
    assert_equals(decode("\xc0", encoding="ISO-8859-1"), u"\u00c0")
