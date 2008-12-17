# Copyright 2007 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import re
import inspect
import pydoc
import gtk
from cStringIO import StringIO

#
# For most objects, we simply call their repr() function, but we handle
# tuples, lists, and dicts specially. We handle them in one of two ways:
#
#  - As a list of items, one per line.
#
#    Dictionaries are always formatted this way. Lists and Tuples are
#    formatted this way if them items in the sequence have long
#    or multi-line representations.
#    
#  - As a list of items, wrapped into multiple lines
#
#    Lists and Tuples are formatted this way if them items in the sequence
#    have short, single-line representations.
#
    
# total maximum number of lines
_MAX_LINES = 17
    
# if a sequence has items longer than this, force separate-lines mode
_MAX_WRAPPED_ITEM_LEN = 20

# maximum number of lines for a wrapped sequence
_MAX_WRAPPED_ITEM_LINES = 5

# max line width when line-wrapping
_MAX_WIDTH = 80

# Common parameters to the functions below:
#
#  open: opening delimeter
#  close: closing delimeter
#  nl: "what to use for break lines". The idea is that if you are at an
#      indentation level of 3, and use "\n   " to break lines, the
#      broken lines stay at indentation level 3.
#  object_stack: stack of objects currently being formatted. This is
#      used to catch recursive data structures.

def __format_separate(sequence, open, close, nl):
    # Used to format dictionaries, lists, and tuples as a list of items
    # 1-per-line.

    buf = StringIO()
    buf.write(open)

    lines = 1
    last_str, last_lines = None, 0
    for str, item_lines in sequence:
        if last_str != None:
            # Process the last item, we'll have one more after it
            new_lines = lines + last_lines

            # The new line takes us over the maximum item count, so we
            # won't have room for the next item
            if new_lines > _MAX_LINES:
                buf.write("...")
                last_str = None
                break

            buf.write(last_str)
            buf.write(",")
            buf.write(nl)
            lines = new_lines

        last_str = str
        last_lines = item_lines

    if last_str != None:
        buf.write(last_str)

    buf.write(close)
    return buf.getvalue(), lines

def __format_wrapped(sequence, open, close, nl):
    # Used to format lists, and tuples as a line-wrapped list of items
    
    lines = 1

    buf = StringIO()

    buf.write(open)

    available_width = _MAX_WIDTH - (len(nl) - 1)

    last_str, last_lines = None, 0
    count = 0
    count_on_line = 0
    for str, item_lines in sequence:
        if item_lines > 1:
            return None
        if len(str) > _MAX_WRAPPED_ITEM_LEN:
            return None

        if last_str != None:
            # Process the last item, we'll have one more after it
            new_available_width = available_width - (len(last_str) + 1) # len(last_str) + len(",")
            if count_on_line > 0:
                new_available_width -= 1 # len(" ")

            if lines == _MAX_WRAPPED_ITEM_LINES:
                # An ellipsis won't fit after this item, and most likely the item after either
                if new_available_width < 4 + len(close): # len(" ...") + len(close)
                    if count_on_line > 0:
                        buf.write(" ")
                    buf.write("...")
                    last_str = None
                    break
            else:
                if new_available_width < 0:
                    buf.write(nl)
                    count_on_line = 0
                    lines += 1
                    available_width = _MAX_WIDTH - (len(nl) - 1)
                    
            if count_on_line > 0:
                buf.write(" ")
                available_width -= 1

            buf.write(last_str)
            buf.write(",")
            available_width -= (len(last_str) + 1)
            count_on_line += 1

        last_str = str
        last_lines = item_lines

    if last_str != None:
        new_available_width = available_width - (len(last_str) + len(close))

        if count_on_line > 0:
            new_available_width -= 1

        if new_available_width < 0:
            buf.write(nl)
        elif count_on_line > 0:
            buf.write(" ")
            
        buf.write(last_str)

    buf.write(close)

    return buf.getvalue(), lines

def __format_dict(obj, nl, object_stack):
    nl = nl + " "

    def iter():
        for key, value in sorted(obj.items()):
            key_str, key_lines = __format(key, nl, object_stack)
            value_str, value_lines = __format(value, nl, object_stack)

            yield key_str + ": " + value_str, key_lines + value_lines - 1

    return __format_separate(iter(), "{", "}", nl)

def __format_sequence(obj, open, close, nl, object_stack):
    nl = nl + " "
    
    seq = (__format(x, nl, object_stack) for x in obj)
    result = __format_wrapped(seq, open, close, nl)
    if result == None:
        seq = (__format(x, nl, object_stack) for x in obj)
        result = __format_separate(seq, open, close, nl)

    return result

def __format(obj, nl, object_stack):
    for o in object_stack:
        if obj is o:
            return "<Recursion>", 1

    object_stack += (obj,)

    t = type(obj)
    repr_attr = getattr(t, '__repr__', None)
    if issubclass(t, dict) and repr_attr is dict.__repr__:
        return __format_dict(obj, nl, object_stack)
    elif issubclass(t, list) and repr_attr is list.__repr__:
        return __format_sequence(obj, '[', ']', nl, object_stack)
    elif issubclass(t, tuple) and repr_attr is tuple.__repr__:
        return __format_sequence(obj, '(', ')', nl, object_stack)
    else:
        s = repr(obj)
        return s.replace("\n", nl),  1 + s.count("\n")

def format(obj):
    """Format obj as text

    This in spirit similar to pprint.format(), but differs in the details of
    how the formatting done. Sequences and dictionaries are trunctated as
    necessary to keep the entire display compact.

    """
    
    return __format(obj, "\n", ())[0]
    
def insert_formatted(buf, iter, obj, heading_type_tag, inline_type_tag, value_tag):
    """Insert a nicely-formatted display of obj into a gtk.TextBuffer

    @param buf: the buffer to insert the formatted display into
    @param iter: the location to insert the formatted display
    @param obj: the object to display in the buffer
    @param heading_type_tag: tag to use for the object type if we are outputting a block
    @param inline_type_tag: tag to use for the object type if we are outputting a single line
    @param value_tag: the tag to use for the objects value

    """

    text = format(obj)
     
    if text.find("\n") >= 0:
        insert_with_tag(buf, iter, pydoc.describe(obj), heading_type_tag)
        buf.insert(iter, "\n")
    else:
        insert_with_tag(buf, iter, pydoc.describe(obj), inline_type_tag)
        buf.insert(iter, ": ")

    insert_with_tag(buf, iter, text, value_tag)
    
def is_data_object(obj):
    """Return True of obj holds data

    This routine is used to distinguish objects we should show help
    for (like modules, classes, methods, and so forth) from other
    types of object.
    
    """
    
    # Test borrowed from pydoc.py
    return not (inspect.ismodule(obj) or
                inspect.isclass(obj) or
                inspect.isroutine(obj) or
                inspect.isgetsetdescriptor(obj) or
                inspect.ismemberdescriptor(obj) or
                isinstance(obj, property))
        
def insert_with_tag(buf, iter, text, tag):
    """Insert text into a gtk.TextBuffer, then tag it with the given tag"""
    
    mark = buf.create_mark(None, iter, True)
    buf.insert(iter, text)
    start = buf.get_iter_at_mark(mark)
    buf.apply_tag(tag, start, iter)
    buf.delete_mark(mark)

####################################################################################

if __name__ == "__main__":

    CHOMP_RE = re.compile(r"^\s*\|", re.MULTILINE)
    def do_test(obj, expected):
        # Trim off initial and trailing blank lines, and use the amount of white
        # space on the first remaining line as an overall indent to remove
        expected = re.sub("^\s*\n","", expected)
        expected = re.sub("\n\s*$","", expected)
        initial_white = len(re.match(r"^\s*", expected).group(0))
        expected = "\n".join([s[initial_white:] for s in expected.split("\n")])
        
        expected = CHOMP_RE.sub("", expected)
        result = format(obj)

        if result != expected:
            print "For %s,\nGot:\n%s\nExpected:\n%s" % (obj, repr(result), repr(expected))

    # We whack down the maximums to reduce the size of our test cases
    _MAX_LINES = 5
    _MAX_WRAPPED_ITEM_LINES = 3
    _MAX_WIDTH = 40

    do_test(1, "1")

    do_test({'a': 1, 'b': 2},
            """
            {'a': 1,
             'b': 2}
            """)

    do_test(dict(((x, x) for x in range(5))),
            """
            {0: 0,
             1: 1,
             2: 2,
             3: 3,
             4: 4}
            """)
    do_test(dict(((x, x) for x in range(6))),
            """
            {0: 0,
             1: 1,
             2: 2,
             3: 3,
             ...}
            """)

    #       ----------------------------------------
    do_test(range(100),
            """
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
             12, 13, 14, 15, 16, 17, 18, 19, 20, 21,
             22, 23, 24, 25, 26, 27, 28, 29, ...]
            """)

    do_test(["a" * 9] * 4,
            """
            ['aaaaaaaaa', 'aaaaaaaaa', 'aaaaaaaaa',
             'aaaaaaaaa']
            """)

    try:
        import numpy

        do_test([numpy.float64(1.0)],
                """
                [1.0]
                """)

        do_test([numpy.float64(1.0), numpy.float64(1.0)],
                """
                [1.0, 1.0]
                """)
    except ImportError:
        pass

    a = [1]
    a.append(a)

    do_test(a, "[1, <Recursion>]")
