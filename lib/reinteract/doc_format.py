# Copyright 2007 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import re
import pydoc
import gtk

from data_format import insert_with_tag, is_data_object

BOLD_RE = re.compile("(?:(.)\b(.))+")
STRIP_BOLD_RE = re.compile("(.)\b(.)")

def insert_docs(buf, iter, obj, bold_tag):
    """Insert documentation about obj into a gtk.TextBuffer

    @param buf: the buffer to insert the documentation into
    @param iter: the location to insert the documentation
    @param obj: the object to get documentation about
    @param bold_tag: the tag to use for bold text, such as headings

    """
    
    # If the routine is an instance, we get help on the type instead
    if is_data_object(obj):
        obj = type(obj)
        
    name = getattr(obj, '__name__', None)
    document = pydoc.text.document(obj, name)

    # pydoc.text.document represents boldface with overstrikes, we need to
    # reverse engineer this and find the spans of bold text
    pos = 0
    while True:
        m = BOLD_RE.search(document, pos)
        if m == None:
            # Strip the trailing newline; this isn't very justifiable in general terms,
            # but matches what we need in Reinteract
            if document.endswith("\n"):
                buf.insert(iter, document[pos:-1])
            else:
                buf.insert(iter, document[pos:])
            break

        buf.insert(iter, document[pos:m.start()])
        insert_with_tag(buf, iter, STRIP_BOLD_RE.sub(lambda m: m.group(1), m.group()), bold_tag)
        pos = m.end()
