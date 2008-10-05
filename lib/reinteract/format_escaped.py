# Copyright 2007 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################
#
# Very, very partial implementation of g_markup_printf_escaped(). Doesn't
# handling things like a %c with an integer argument that evaluates to
# a markup special character, or special characters in the repr() or str()
# of an object. It also doesn't handle %(name)s type arguments with
# keyword arguments.
#
# To do better at escaping everything, you'd probably want to apply the
# implementation technique of g_markup_printf_escaped(). The main difficulty
# of that is that you need then to be able to split the format string into
# format specifiers and other sections, which means
# a big regular expression encoding the format specifers defined by
# http://docs.python.org/lib/typesseq-strings.html
#

from gobject import markup_escape_text

def _escape(o):
    if isinstance(o, basestring):
        return markup_escape_text(o)
    else:
        return o
    
def format_escaped(fmt, *args):
    return fmt % tuple((_escape(x) for x in args))

if __name__ == '__main__':
    assert format_escaped("%s %.4f", "&foo", 4.3) == "&amp;foo 4.3000"


