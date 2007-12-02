import re
import inspect
import pydoc
import gtk

BOLD_RE = re.compile("(?:(.)\b(.))+")
STRIP_BOLD_RE = re.compile("(.)\b(.)")

def _insert_with_tag(buf, iter, text, tag):
    mark = buf.create_mark(None, iter, True)
    buf.insert(iter, text)
    start = buf.get_iter_at_mark(mark)
    buf.apply_tag(tag, start, iter)
    buf.delete_mark(mark)

def insert_docs(buf, iter, obj, bold_tag):
    """Insert documentation about obj into a gtk.TextBuffer

    buf -- the buffer to insert the documentation into
    iter -- the location to insert the documentation
    obj -- the object to get documentation about
    bold_tag -- the tag to use for bold text, such as headings

    """
    
    # If the routine is an instance, we get help on the type instead
    # (Test borrowed from pydoc.py)
    if not (inspect.ismodule(obj) or
            inspect.isclass(obj) or
            inspect.isroutine(obj) or
            inspect.isgetsetdescriptor(obj) or
            inspect.ismemberdescriptor(obj) or
            isinstance(obj, property)):
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
        _insert_with_tag(buf, iter, STRIP_BOLD_RE.sub(lambda m: m.group(1), m.group()), bold_tag)
        pos = m.end()
