# Copyright 2007-2009 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

from __future__ import with_statement

import gobject
import gtk
import logging
import pango

from custom_result import CustomResult
from chunks import StatementChunk,CommentChunk
import doc_format
from notebook import HelpResult
from statement import WarningResult
import retokenize
from worksheet import Worksheet, NEW_LINE_RE

_debug = logging.getLogger("ShellBuffer").debug

# See comment in iter_copy_from.py
try:
    gtk.TextIter.copy_from
    def _copy_iter(dest, src):
        dest.copy_from(src)
except AttributeError:
    from iter_copy_from import iter_copy_from as _copy_iter

class _RevalidateIters:
    def __init__(self, buffer, *iters):
        self.buffer = buffer
        self.iters = iters

    def __enter__(self):
        self.marks = map(lambda iter: (iter, self.buffer.create_mark(None, iter, True)), self.iters)

    def __exit__(self, exception_type, exception_value, exception_traceback):
        for iter, mark in self.marks:
            _copy_iter(iter, self.buffer.get_iter_at_mark(mark))
            self.buffer.delete_mark(mark)

ADJUST_BEFORE = 0
ADJUST_AFTER = 1
ADJUST_NONE = 2

#######################################################
# GtkTextView fixups
#######################################################

# Return value of iter.forward_line() is useless "whether the iter is
# derefenceable" ... causes bugs with empty last lines where you move
# onto the last line and it is immediately not dereferenceable
def _forward_line(iter):
    """iter.forward_line() with fixed-up return value (moved to next line)"""

    line = iter.get_line()
    iter.forward_line()
    return iter.get_line() != line

# Mostly for consistency ... iter.forward_line() has more useful return value
# (moved) then backward_line
def _backward_line(iter):
    """iter.backward_line() with fixed-up return value (moved to next line)"""

    line = iter.get_line()
    iter.backward_line()
    return iter.get_line() != line

####################################################################

class ShellBuffer(gtk.TextBuffer):
    __gsignals__ = {
        'begin-user-action': 'override',
        'end-user-action': 'override',
        'insert-text': 'override',
        'delete-range': 'override',
        'add-custom-result':  (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT)),
        'pair-location-changed': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT))
    }

    def __init__(self, notebook, edit_only=False):
        gtk.TextBuffer.__init__(self)

        self.worksheet = Worksheet(notebook, edit_only)
        self.worksheet.connect('text-inserted', self.on_text_inserted)
        self.worksheet.connect('text-deleted', self.on_text_deleted)
        self.worksheet.connect('lines-inserted', self.on_lines_inserted)
        self.worksheet.connect('lines-deleted', self.on_lines_deleted)
        self.worksheet.connect('chunk-inserted', self.on_chunk_inserted)
        self.worksheet.connect('chunk-changed', self.on_chunk_changed)
        self.worksheet.connect('chunk-deleted', self.on_chunk_deleted)
        self.worksheet.connect('chunk-status-changed', self.on_chunk_status_changed)
        self.worksheet.connect('chunk-results-changed', self.on_chunk_results_changed)
        self.worksheet.connect('place-cursor', self.on_place_cursor)

        self.__result_tag = self.create_tag(family="monospace",
                                            style="italic",
                                            wrap_mode=gtk.WRAP_WORD,
                                            editable=False)
        # Order here is significant ... we want the recompute tag to have higher priority, so
        # define it second
        self.__warning_tag = self.create_tag(foreground="#aa8800")
        self.__error_tag = self.create_tag(foreground="#aa0000")
        self.__recompute_tag = self.create_tag(foreground="#888888")
        self.__comment_tag = self.create_tag(foreground="#3f7f5f")
        self.__bold_tag = self.create_tag(weight=pango.WEIGHT_BOLD)
        self.__help_tag = self.create_tag(family="sans",
                                          style=pango.STYLE_NORMAL,
                                          paragraph_background="#ffff88",
                                          left_margin=10,
                                          right_margin=10)

        punctuation_tag = None

        self.__fontify_tags = {
            retokenize.TOKEN_KEYWORD      : self.create_tag(foreground="#7f0055", weight=600),
            retokenize.TOKEN_NAME         : None,
            retokenize.TOKEN_COMMENT      : self.__comment_tag,
            retokenize.TOKEN_BUILTIN_CONSTANT : self.create_tag(foreground="#55007f"),
            retokenize.TOKEN_STRING       : self.create_tag(foreground="#00aa00"),
            retokenize.TOKEN_PUNCTUATION  : punctuation_tag,
            retokenize.TOKEN_CONTINUATION : punctuation_tag,
            retokenize.TOKEN_LPAREN       : punctuation_tag,
            retokenize.TOKEN_RPAREN       : punctuation_tag,
            retokenize.TOKEN_LSQB         : punctuation_tag,
            retokenize.TOKEN_RSQB         : punctuation_tag,
            retokenize.TOKEN_LBRACE       : punctuation_tag,
            retokenize.TOKEN_RBRACE       : punctuation_tag,
            retokenize.TOKEN_BACKQUOTE    : punctuation_tag,
            retokenize.TOKEN_COLON        : punctuation_tag,
            retokenize.TOKEN_DOT          : punctuation_tag,
            retokenize.TOKEN_EQUAL        : punctuation_tag,
            retokenize.TOKEN_AUGEQUAL     : punctuation_tag,
            retokenize.TOKEN_NUMBER       : None,
            retokenize.TOKEN_JUNK         : self.create_tag(underline="error"),
        }

        self.__line_marks = [self.create_mark(None, self.get_start_iter(), True)]
        self.__line_marks[0].line = 0
        self.__in_modification_count = 0

        self.__have_pair = False
        self.__pair_mark = self.create_mark(None, self.get_start_iter(), True)

    #######################################################
    # Utility
    #######################################################

    def __begin_modification(self):
        self.__in_modification_count += 1

    def __end_modification(self):
        self.__in_modification_count -= 1

    def __insert_results(self, chunk):
        if not isinstance(chunk, StatementChunk):
            return

        if chunk.results_start_mark:
            raise RuntimeError("__insert_results called when we already have results")

        if (chunk.results == None or len(chunk.results) == 0) and chunk.error_message == None:
            return

        self.__begin_modification()

        location = self.pos_to_iter(chunk.end - 1)
        if not location.ends_line():
            location.forward_to_line_end()

        # We don't want to move the insert cursor in the common case of
        # inserting a result right at the insert cursor
        if location.compare(self.get_iter_at_mark(self.get_insert())) == 0:
            saved_insert = self.create_mark(None, location, True)
        else:
            saved_insert = None

        self.insert(location, "\n")

        chunk.results_start_mark = self.create_mark(None, location, True)
        chunk.results_start_mark.source = chunk

        if chunk.error_message:
            results = [ chunk.error_message ]
        else:
            results = chunk.results

        first = True
        for result in results:
            if not first:
                self.insert(location, "\n")
            first = False

            if isinstance(result, basestring):
                self.insert(location, result)
            elif isinstance(result, WarningResult):
                start_mark = self.create_mark(None, location, True)
                self.insert(location, result.message)
                start = self.get_iter_at_mark(start_mark)
                self.delete_mark(start_mark)
                self.apply_tag(self.__warning_tag, start, location)
            elif isinstance(result, HelpResult):
                start_mark = self.create_mark(None, location, True)
                doc_format.insert_docs(self, location, result.arg, self.__bold_tag)
                start = self.get_iter_at_mark(start_mark)
                self.delete_mark(start_mark)
                self.apply_tag(self.__help_tag, start, location)
            elif isinstance(result, CustomResult):
                anchor = self.create_child_anchor(location)
                self.emit("add-custom-result", result, anchor)
                location = self.get_iter_at_child_anchor(anchor)
                location.forward_char() # Skip over child

        start = self.get_iter_at_mark(chunk.results_start_mark)
        self.apply_tag(self.__result_tag, start, location)
        chunk.results_end_mark = self.create_mark(None, location, True)
        chunk.results_start_mark.source = chunk

        if saved_insert != None:
            self.place_cursor(self.get_iter_at_mark(saved_insert))
            self.delete_mark(saved_insert)

        self.__end_modification()

    def __delete_results_marks(self, chunk):
        if not (isinstance(chunk, StatementChunk) and chunk.results_start_mark):
            return

        self.delete_mark(chunk.results_start_mark)
        self.delete_mark(chunk.results_end_mark)
        chunk.results_start_mark = None
        chunk.results_end_mark = None

    def __delete_results(self, chunk):
        if not (isinstance(chunk, StatementChunk) and chunk.results_start_mark):
            return

        self.__begin_modification()

        start = self.get_iter_at_mark(chunk.results_start_mark)
        end = self.get_iter_at_mark(chunk.results_end_mark)
        # Delete the newline before the result along with the result
        start.backward_line()
        if not start.ends_line():
            start.forward_to_line_end()
        self.delete(start, end)
        self.__delete_results_marks(chunk)

        self.__end_modification()

    def __set_pair_location(self, location):
        changed = False
        old_location = None

        if location == None:
            if self.__have_pair:
                old_location = self.get_iter_at_mark(self.__pair_mark)
                self.__have_pair = False
                changed = True
        else:
            if not self.__have_pair:
                self.__have_pair = True
                self.move_mark(self.__pair_mark, location)
                changed = True
            else:
                old_location = self.get_iter_at_mark(self.__pair_mark)
                if location.compare(old_location) != 0:
                    self.move_mark(self.__pair_mark, location)
                    changed = True

        if changed:
            self.emit('pair-location-changed', old_location, location)

    def __calculate_pair_location(self):
        location = self.get_iter_at_mark(self.get_insert())

        # GTK+-2.10 has fractionally-more-efficient buffer.get_has_selection()
        selection_bound = self.get_iter_at_mark(self.get_selection_bound())
        if location.compare(selection_bound) != 0:
            self.__set_pair_location(None)
            return

        location = self.get_iter_at_mark(self.get_insert())
        line, offset = self.iter_to_pos(location, adjust=ADJUST_NONE)

        if line == None:
            self.__set_pair_location(None)
            return

        chunk = self.worksheet.get_chunk(line)
        if not isinstance(chunk, StatementChunk):
            self.__set_pair_location(None)
            return

        if offset == 0:
            self.__set_pair_location(None)
            return

        pair_line, pair_start = chunk.tokenized.get_pair_location(line - chunk.start, offset - 1)

        if pair_line == None:
            self.__set_pair_location(None)
            return

        pair_iter = self.pos_to_iter(chunk.start + pair_line, pair_start)
        self.__set_pair_location(pair_iter)

    def __fontify_statement_chunk(self, chunk, changed_lines):
        iter = self.pos_to_iter(chunk.start)
        i = 0
        for l in changed_lines:
            while i < l:
                iter.forward_line()
                i += 1
            end = iter.copy()
            if not end.ends_line():
                end.forward_to_line_end()
            self.remove_all_tags(iter, end)

            end = iter.copy()
            for token_type, start_index, end_index, _ in chunk.tokenized.get_tokens(l):
                tag = self.__fontify_tags[token_type]
                if tag != None:
                    iter.set_line_index(start_index)
                    end.set_line_index(end_index)
                    self.apply_tag(tag, iter, end)

    #######################################################
    # Overrides for GtkTextView behavior
    #######################################################

    def do_begin_user_action(self):
        self.worksheet.begin_user_action()

    def do_end_user_action(self):
        self.worksheet.end_user_action()
        if not self.worksheet.in_user_action():
            self.__calculate_pair_location()

    def do_insert_text(self, location, text, text_len):
        if self.__in_modification_count > 0:
            gtk.TextBuffer.do_insert_text(self, location, text, text_len)
            return

        line, offset = self.iter_to_pos(location, adjust=ADJUST_NONE)
        if line == None:
            return

        with _RevalidateIters(self, location):
            self.worksheet.insert(line, offset, text[0:text_len])

    def do_delete_range(self, start, end):
        if self.__in_modification_count > 0:
            gtk.TextBuffer.do_delete_range(self, start, end)
            return

        start_line, start_offset = self.iter_to_pos(start, adjust=ADJUST_AFTER)
        end_line, end_offset = self.iter_to_pos(end, adjust=ADJUST_AFTER)

        # If start and end crossed, then they were both within a result. Ignore
        # (This really shouldn't happen)
        if start_line > end_line or (start_line == end_line and start_offset > end_offset):
            return

        # If start and end ended up at the same place, then we must have been
        # trying to join a result with a adjacent text line. Treat that as joining
        # the two text lines.
        if start_line == end_line and start_offset == end_offset:
            if start_offset == 0: # Start of the line after
                if start_line > 0:
                    start_line -= 1
                    start_offset = len(self.worksheet.get_line(start_line))
            else: # End of the previous line
                if end_line < self.worksheet.get_line_count() - 1:
                    end_line += 1
                    end_offset = 0

        with _RevalidateIters(self, start, end):
            self.worksheet.delete_range(start_line, start_offset, end_line, end_offset)

    def do_mark_set(self, location, mark):
        try:
            gtk.TextBuffer.do_mark_set(self, location, mark)
        except NotImplementedError:
            # the default handler for ::mark-set was added in GTK+-2.10
            pass

        if mark != self.get_insert() and mark != self.get_selection_bound():
            return

        if not self.worksheet.in_user_action():
            self.__calculate_pair_location()

    #######################################################
    # Callbacks on worksheet changes
    #######################################################

    def on_text_inserted(self, worksheet, line, offset, text):
        self.__begin_modification()
        location = self.pos_to_iter(line, offset)

        # The inserted text may carry a set of results away from the chunk
        # that produced it. Worksheet doesn't care what we do with the
        # result chunks on an insert location, as long as the resulting
        # text (ignoring results) matches what it expects. If the
        # text doesn't start with a newline, then the chunk above is
        # necessarily modified, and we'll fix things up when we get the
        # ::chunk-changed. If the text starts with a newline, then we
        # insert after the results, since it doesn't matter. But we
        # also have to fix the cursor.

        chunk = worksheet.get_chunk(line)
        if (line == chunk.end - 1 and NEW_LINE_RE.match(text) and
            isinstance(chunk, StatementChunk) and
            offset == len(chunk.tokenized.lines[-1]) and
            chunk.results_start_mark):

            result_end = self.get_iter_at_mark(chunk.results_end_mark)
            cursor_location = self.get_iter_at_mark(self.get_insert())

            if (location.compare(cursor_location) == 0):
                self.place_cursor(result_end)

            location = result_end

        self.insert(location, text, -1)

        # Worksheet considers an insertion of multiple lines of text at
        # offset 0 to shift that line down. Since our line start marks
        # have left gravity and don't move, we need to fix them up.
        if offset == 0:
            count = 0
            for m in NEW_LINE_RE.finditer(text):
                count += 1

            if count > 0:
                mark = self.__line_marks[line]
                iter = self.get_iter_at_mark(mark)
                while count > 0:
                    iter.forward_line()
                    count -= 1
                self.move_mark(mark, iter)

        self.__end_modification()

    def on_text_deleted(self, worksheet, start_line, start_offset, end_line, end_offset):
        self.__begin_modification()
        start = self.pos_to_iter(start_line, start_offset)
        end = self.pos_to_iter(end_line, end_offset)

        # The range may contain intervening results; Worksheet doesn't care
        # if we delete them or not, but the resulting text in the buffer (ignoring
        # results) matches what it expects. In the normal case, we just delete
        # the results, and if they belong to a statement above, they will be added
        # back when we get the ::chunk-changed signal. There is a special case when
        # the chunk above doesn't change; when we delete from * to * in:
        #
        # 1 + 1 *
        # /2/
        # [ ... more stuff ]
        # * <empty line>
        #
        # In this case, we adjust the range to start at the end of the first result,
        # But we also have to fix up the cursor.
        #
        start_chunk = worksheet.get_chunk(start_line)
        if (isinstance(start_chunk, StatementChunk) and start_chunk.results_start_mark and
            start_line == start_chunk.end - 1 and start_offset == len(start_chunk.tokenized.lines[-1]) and
            end.get_line_offset() == 0 and end.ends_line()):

            cursor_location = self.get_iter_at_mark(self.get_insert())
            if (start.compare(cursor_location) < 0 and end.compare(cursor_location) >= 0):
                self.place_cursor(start)

            start = self.get_iter_at_mark(start_chunk.results_end_mark)
            start_line += 1

        for chunk in worksheet.iterate_chunks(start_line, end_line):
            if chunk != worksheet.get_chunk(end_line):
                self.__delete_results_marks(chunk)

        self.delete(start, end)
        self.__end_modification()

    def on_lines_inserted(self, worksheet, start, end):
        _debug("...lines %d:%d inserted", start, end)
        if start == 0:
            iter = self.get_start_iter()
        else:
            iter = self.pos_to_iter(start - 1)
            iter.forward_line()
            while True:
                for mark in iter.get_marks():
                    if hasattr(mark, 'source'): # A result chunk!
                        iter = self.get_iter_at_mark(mark.source.results_end_mark)
                        iter.forward_line()
                        continue
                break

        self.__line_marks[start:start] = (None for x in xrange(start, end))
        for i in xrange(start, end):
            self.__line_marks[i] = self.create_mark(None, iter, True)
            self.__line_marks[i].line = i
            iter.forward_line()

        for i in xrange(end, len(self.__line_marks)):
            self.__line_marks[i].line += (end - start)

    def on_lines_deleted(self, worksheet, start, end):
        _debug("...lines %d:%d deleted", start, end)
        for i in xrange(start, end):
            self.delete_mark(self.__line_marks[i])

        self.__line_marks[start:end] = []

        for i in xrange(start, len(self.__line_marks)):
            self.__line_marks[i].line -= (end - start)

    def on_chunk_inserted(self, worksheet, chunk):
        _debug("...chunk %s inserted", chunk);
        chunk.results_start_mark = None
        chunk.results_end_mark = None
        self.on_chunk_changed(worksheet, chunk, range(0, chunk.end - chunk.start))

    def on_chunk_deleted(self, worksheet, chunk):
        _debug("...chunk %s deleted", chunk);
        self.__delete_results(chunk)

    def on_chunk_changed(self, worksheet, chunk, changed_lines):
        _debug("...chunk %s changed", chunk);

        if chunk.results_start_mark:
            # Check that the result is still immediately after the chunk, and if
            # not, delete it and insert it again
            iter = self.pos_to_iter(chunk.end - 1)
            if (not _forward_line(iter) or not chunk.results_start_mark in iter.get_marks()):
                self.__delete_results(chunk)
                self.__insert_results(chunk)
        else:
            self.__insert_results(chunk)

        if isinstance(chunk, StatementChunk):
            self.__fontify_statement_chunk(chunk, changed_lines)
        elif isinstance(chunk, CommentChunk):
            start = self.pos_to_iter(chunk.start)
            end = self.pos_to_iter(chunk.end - 1, len(self.worksheet.get_line(chunk.end - 1)))
            self.remove_all_tags(start, end)
            self.apply_tag(self.__comment_tag, start, end)

    def on_chunk_status_changed(self, worksheet, chunk):
        _debug("...chunk %s status changed", chunk);
        pass

    def on_chunk_results_changed(self, worksheet, chunk):
        _debug("...chunk %s results changed", chunk);
        self.__delete_results(chunk)
        self.__insert_results(chunk)

    def on_place_cursor(self, worksheet, line, offset):
        self.place_cursor(self.pos_to_iter(line, offset))

    #######################################################
    # Public API
    #######################################################

    def pos_to_iter(self, line, offset=0):
        """Get an iter at the specification code line and offset

        @param line: the line in the code of the worksheet (not the gtk.TextBuffer line)
        @param offset: the character within the line (defaults 0). -1 means end

        """

        iter = self.get_iter_at_mark(self.__line_marks[line])
        if offset < 0:
            offset = len(self.worksheet.get_line(line))
        iter.set_line_offset(offset)

        return iter

    def iter_to_pos(self, iter, adjust=ADJUST_BEFORE):
        """Get the code line and offset at the given iterator

        Return a tuple of (code_line, offset).

        @param iter: an iterator within the buffer
        @param adjust: how to handle the case where the iterator isn't on a line of code.

              ADJUST_BEFORE: end previous line of code
              ADJUST_AFTER: start of next line of code
              ADJUST_NONE: return (None, None)

        """

        offset = iter.get_line_offset()
        tmp = iter.copy()
        tmp.set_line_offset(0)
        for mark in tmp.get_marks():
            if hasattr(mark, 'line'):
                return (mark.line, offset)

        if adjust == ADJUST_NONE:
            return None, None

        if adjust == ADJUST_AFTER:
            while _forward_line(tmp):
                for mark in tmp.get_marks():
                    if hasattr(mark, 'line'):
                        return mark.line, 0
                # Not found, we must be in a result chunk after the last line
                # fall through to the !after case

        while _backward_line(tmp):
            for mark in tmp.get_marks():
                if hasattr(mark, 'line'):
                    if not tmp.ends_line():
                        tmp.forward_to_line_end()
                    return mark.line, tmp.get_line_offset()

        raise AssertionError("Not reached")

    def get_public_text(self, start=None, end=None):
        """Gets the text in the buffer in the specified range, ignoring results

        This method satisfies the contract required by sanitize_textview_ipc.py

        start - iter for the end of the text  (None == buffer start)
        end - iter for the start of the text (None == buffer end)

        """

        if start == None:
            start = self.get_start_iter();
        if end == None:
            end = self.get_end_iter();

        start_line, start_offset = self.iter_to_pos(start, adjust=ADJUST_AFTER)
        end_line, end_offset = self.iter_to_pos(end, adjust=ADJUST_BEFORE)

        return self.worksheet.get_text(start_line, start_offset, end_line, end_offset)

    def get_pair_location(self):
        """Return an iter pointing to the character paired with the character before the cursor, or None"""

        if self.__have_pair:
            return self.get_iter_at_mark(self.__pair_mark)
        else:
            return None

    def in_modification(self):
        """Return True if the text buffer is modifying its contents itself

        This can be useful to distinguish user edits from internal edits.

        """

        return self.__in_modification_count > 0

######################################################################
# The tests we include here are tests of the interaction of editing
# with results. Results don't appear inline in a Worksheet, so these
# tests have to be here rather than with Worksheet. Almost all other
# testing is done in Worksheet.
#

if __name__ == '__main__': #pragma: no cover
    import sys

    gobject.threads_init()

    from notebook import Notebook

    if "-d" in sys.argv:
        logging.basicConfig(level=logging.DEBUG, format="DEBUG: %(message)s")

    from StringIO import StringIO

    import stdout_capture
    stdout_capture.init()

    buf = ShellBuffer(Notebook())

    def insert(line, offset, text):
        i = buf.get_iter_at_line_offset(line, offset)
        buf.insert_interactive(i, text, True)

    def delete(start_line, start_offset, end_line, end_offset):
        i = buf.get_iter_at_line_offset(start_line, start_offset)
        j = buf.get_iter_at_line_offset(end_line, end_offset)
        buf.delete_interactive(i, j, True)

    def calculate():
        buf.worksheet.calculate(True)

    def clear():
        buf.worksheet.clear()

    def expect(expected):
        si = StringIO()
        i = buf.get_start_iter()
        while True:
            end = i.copy()
            if not end.ends_line():
                end.forward_to_line_end()
            text = buf.get_slice(i, end)

            line, _ = buf.iter_to_pos(i, adjust=ADJUST_NONE)
            if line != None:
                chunk = buf.worksheet.get_chunk(line)
            else:
                chunk = None

            if chunk and isinstance(chunk, StatementChunk):
                if line == chunk.start:
                    si.write(">>> ")
                else:
                    si.write("... ")

            si.write(text)

            if _forward_line(i):
                si.write("\n")
            else:
                break

        result = si.getvalue()
        if not result == expected:
            raise AssertionError("\nGot:\n%s\nExpected:\n%s" % (result, expected))

    # Calculation resulting in result chunks
    insert(0, 0, "1 \\\n + 2\n3\n")
    calculate()
    expect(""">>> 1 \\
...  + 2
3
>>> 3
3
""")

    # Check that splitting a statement with a delete results in the
    # result chunk being moved to the last line of the first half
    delete(1, 0, 1, 1)
    expect(""">>> 1 \\
3
>>> + 2
>>> 3
3
""")

    # Editing a line with an existing error chunk to fix the error
    clear()

    insert(0, 0, "a\na = 2")
    calculate()

    insert(0, 0, "2")
    delete(0, 1, 0, 2)
    calculate()
    expect(""">>> 2
2
>>> a = 2""")

    # Test an attempt to join a ResultChunk onto a previous chunk; should join
    # the line with the following line, moving the result chunk
    clear()

    insert(0, 0, "1\n");
    calculate()
    expect(""">>> 1
1
""")

    delete(0, 1, 1, 0)
    expect(""">>> 1
1""")

    # Test an attempt to join a chunk onto a previous ResultChunk, should move
    # the ResultChunk and do the modification
    clear()
    expect("")

    insert(0, 0, "1\n2\n");
    calculate()
    expect(""">>> 1
1
>>> 2
2
""")
    delete(1, 1, 2, 0)
    expect(""">>> 12
1
""")

    # Test inserting random text inside a result chunk, should ignore
    clear()

    insert(0, 0, "1\n2");
    calculate()
    expect(""">>> 1
1
>>> 2
2""")
    insert(1, 0, "foo")
    expect(""">>> 1
1
>>> 2
2""")


    # Calculation resulting in a multi-line result change
    clear()

    insert(0, 0, "for i in range(0, 3): print i")
    calculate()
    expect(""">>> for i in range(0, 3): print i
0
1
2""")

    # Test deleting a range containing both results and statements
    clear()

    insert(0, 0, "1\n2\n3\n4\n")
    calculate()
    expect(""">>> 1
1
>>> 2
2
>>> 3
3
>>> 4
4
""")

    delete(2, 0, 5, 0)
    expect(""">>> 1
1
>>> 4
4
""")

    # Inserting an entire new statement in the middle
    insert(2, 0, "2.5\n")
    expect(""">>> 1
1
>>> 2.5
>>> 4
4
""")
    calculate()
    expect(""">>> 1
1
>>> 2.5
2.5
>>> 4
4
""")

    # Check that inserting a blank line at the beginning of a statement leaves
    # the result behind
    insert(2, 0, "\n")
    expect(""">>> 1
1

>>> 2.5
2.5
>>> 4
4
""")

    # Test deleting a range including a result and joining two statements
    clear()
    insert(0, 0, "12\n34")
    calculate()
    expect(""">>> 12
12
>>> 34
34""")
    delete(0, 1, 2, 1)
    expect(""">>> 14
12""")

    # Test a deletion that splits the buffer into two (invalid) pieces
    clear()
    insert(0, 0, "try:\n    a = 1\nfinally:\n    print 'Done'")
    calculate()
    expect(""">>> try:
...     a = 1
... finally:
...     print 'Done'
Done""")
    delete(2, 7, 2, 8)
    calculate()
    expect(""">>> try:
...     a = 1
invalid syntax
>>> finally
...     print 'Done'
invalid syntax""")

    # Try an insertion that combines the two pieces and makes them valid
    # again (combining across the error result chunk)
    insert(3, 7, ":")
    calculate()
    expect(""">>> try:
...     a = 1
... finally:
...     print 'Done'
Done""")

    # Test an undo of an insert that caused insertion of result chunks
    clear()

    insert(0, 0, "2\n")
    expect(""">>> 2
""")
    calculate()
    expect(""">>> 2
2
""")
    insert(0, 0, "1\n")
    calculate()
    buf.worksheet.undo()
    expect(""">>> 2
2
""")

    # Test insertion of WarningResult

    clear()

    insert(0, 0, """class A(object):
    def __copy__(self): raise RuntimeError("Can't copy")
    def __repr__(a): return 'A()'
    def foo(x): return x
a = A()
a.foo()""")
    calculate()
    expect(""">>> class A(object):
...     def __copy__(self): raise RuntimeError("Can't copy")
...     def __repr__(a): return 'A()'
...     def foo(x): return x
>>> a = A()
>>> a.foo()
'a' apparently modified, but can't copy it
A()""")
