# -*- mode: python; c-basic-offset: 4; indent-tabs-mode: nil -*- *
import sys

import gobject
import logging
import os
import re
from StringIO import StringIO

from chunks import *
from notebook import Notebook
from undo_stack import UndoStack, InsertOp, DeleteOp

_debug = logging.getLogger("Worksheet").debug

_DEFINE_GLOBALS = compile("""
global reinteract_output, reinteract_print
def reinteract_output(*args):
   __reinteract_statement.do_output(*args)
def reinteract_print(*args):
   __reinteract_statement.do_print(*args)
""", __name__, 'exec')

BLANK_RE = re.compile(r'^\s*$')
BLANK = 0
COMMENT_RE = re.compile(r'^\s*#')
COMMENT = 1
STATEMENT_START = 2
CONTINUATION_RE = re.compile(r'^(?:\s+|(?:except|finally)[^A-Za-z0-9_])')
CONTINUATION = 3

NEW_LINE_RE = re.compile(r'\n|\r|\r\n')

def calc_line_class(text):
    if BLANK_RE.match(text):
        return BLANK
    elif COMMENT_RE.match(text):
        return COMMENT
    elif CONTINUATION_RE.match(text):
        return CONTINUATION
    else:
        return STATEMENT_START

def order_positions(start_line, start_offset, end_line, end_offset):
    if start_line > end_line or (start_line == end_line and start_offset > end_offset):
        t = end_line
        end_line = start_line
        start_line = t

        t = end_offset
        end_offset = start_offset
        start_offset = t

    return start_line, start_offset, end_line, end_offset

class Worksheet(gobject.GObject):
    __gsignals__ = {
        # text-* are emitted before we fix up our internal state, so what can be done
        # in them are limited. They are meant for keeping a UI in sync with the internal
        # state.
        'text-inserted': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (int, int, str)),
        'text-deleted': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (int, int, int, int)),
        'lines-inserted': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (int, int)),
        'lines-deleted': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (int, int)),
        'chunk-inserted': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        'chunk-changed': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT)),
        'chunk-deleted': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        'chunk-status-changed': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        'chunk-results-changed': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        # This is only for the convenience of the undo stack; otherwise we ignore cursor position
        'place-cursor': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (int, int))
    }

    filename = gobject.property(type=str, default=None)
    code_modified = gobject.property(type=bool, default=False)

    def __init__(self, notebook):
        gobject.GObject.__init__(self)

        self.global_scope = {}
        notebook.setup_globals(self.global_scope)
        exec _DEFINE_GLOBALS in self.global_scope

        self.__lines = [""]
        self.__chunks = [BlankChunk(0,1)]
        self.__chunks[0].line_count += 1

        # There's quite a bit of complexity knowing when a change to lines changes
        # adjacent chunks. We use a simple and slightly inefficient algorithm for this
        # and just scan everything that might have changed. But we don't want typing
        # within a line to cause an unlimited rescan. So we keep *two* separate ranges
        # of things that might have changed:
        #
        # This range is the range where line classes changed or lines were inserted
        # and deleted
        self.__rescan_start = None
        self.__rescan_end = None
        # This range is the range where lines changed without changing classes
        self.__change_start = None
        self.__change_end = None

        self.__changed_chunks = set()
        self.__deleted_chunks = set()
        self.__freeze_changes_count = 0
        self.__user_action_count = 0

        self.__undo_stack = UndoStack(self)

        # pygobject bug, default None doesn't work for a string property and gets
        # turned into ""
        self.filename = None

    def do_import(self, name, globals, locals, fromlist, level):
        __import__(self, name, globals, locals, fromlist, level)

    def iterate_chunks(self, start_line=0, end_line=None):
        if end_line == None or end_line > len(self.__chunks):
            end_line = len(self.__chunks)
        if start_line >= len(self.__chunks) or end_line <= start_line:
            return

        prev_chunk = None
        for i in xrange(start_line, end_line):
            chunk = self.__chunks[i]
            if chunk != prev_chunk:
                yield chunk
            prev_chunk = chunk

    def __freeze_changes(self):
        self.__freeze_changes_count += 1

    def __thaw_changes(self):
        self.__freeze_changes_count -= 1
        if self.__freeze_changes_count == 0:
            self.__rescan()
            self.__emit_chunk_changes()

    def __emit_chunk_changes(self):
        deleted_chunks = self.__deleted_chunks
        self.__deleted_chunks = set()

        changed_chunks = self.__changed_chunks
        self.__changed_chunks = set()

        for chunk in deleted_chunks:
            self.emit('chunk-deleted', chunk)

        for chunk in sorted(changed_chunks, lambda a, b: cmp(a.start,b.start)):
            if chunk.newly_inserted:
                chunk.newly_inserted = False
                chunk.changed_lines = None
                chunk.status_changed = False
                self.emit('chunk-inserted', chunk)
            elif chunk.changed_lines != None:
                changed_lines = sorted(chunk.changed_lines)
                chunk.changed_lines = None
                chunk.status_changed = False
                self.emit('chunk-changed', chunk, changed_lines)
            elif chunk.status_changed:
                chunk.status_changed = False
                self.emit('chunk-status-changed', chunk)
            if chunk.results_changed:
                chunk.results_changed = False
                self.emit('chunk-results-changed', chunk)

    def __chunk_changed(self, chunk):
        self.__changed_chunks.add(chunk)

    def __mark_rest_for_execute(self, start_line):
        # Mark all statements starting from start_line as needing execution.
        # We do this immediately when we change or delete a previous
        # StatementChunk. The alternative would be to do it when we
        # __thaw_changes(), which would conceivably be more efficient, but
        # it's hard to see how to handle deleted chunks in that case.
        for chunk in self.iterate_chunks(start_line):
            if isinstance(chunk, StatementChunk):
                if chunk.mark_for_execute():
                    self.__chunk_changed(chunk)
                else:
                    # Everything after the first chunk that was previously
                    # marked for execution must also have been marked for
                    # execution, so we can stop
                    break

    def __mark_changed_statement(self, chunk):
        self.__chunk_changed(chunk)
        self.__mark_rest_for_execute(chunk.end)

    def __decrement_line_count(self, chunk, line):
        if chunk != None:
            if chunk.line_count <= 0:
                raise RuntimeError("Decrementing line count for a deleted chunk")

            chunk.line_count -= 1
            if chunk.line_count == 0:
                try:
                    self.__changed_chunks.remove(chunk)
                except KeyError:
                    pass
                if isinstance(chunk, StatementChunk):
                    self.__deleted_chunks.add(chunk)
                    self.__mark_rest_for_execute(line + 1)

    def __set_line_chunk(self, i, chunk):
        old_chunk = self.__chunks[i]
        self.__chunks[i] = chunk
        chunk.line_count += 1
        self.__decrement_line_count(old_chunk, i)

    def __clear_line_chunks(self, start, end):
        for i in xrange(start, end):
            self.__decrement_line_count(self.__chunks[i], i)
            self.__chunks[i] = None

    def __assign_lines(self, chunk_start, lines, statement_end):
        if statement_end > chunk_start:
            chunk_lines = lines[0:statement_end - chunk_start]

            old_statement = None
            for i in xrange(chunk_start, statement_end):
                if isinstance(self.__chunks[i], StatementChunk):
                    old_statement = self.__chunks[i]
                    break

            if old_statement != None:
                # An old statement can only be turned into *one* new statement; this
                # prevents us getting fooled if we split a statement
                self.__clear_line_chunks(max(old_statement.start, statement_end), old_statement.end)

                chunk = old_statement
                changed = chunk.set_lines(chunk_lines)

                # If we moved the statement with respect to the worksheet, then the we
                # need to refontify, even if the old statement didn't change
                if old_statement.start != chunk_start:
                    changed = True
                    chunk.changed_lines = set(range(0, statement_end - chunk_start))
            else:
                chunk = StatementChunk()
                chunk.set_lines(chunk_lines)
                changed = True

            chunk.start = chunk_start
            chunk.end = statement_end

            for i in xrange(chunk_start, statement_end):
                self.__set_line_chunk(i, chunk)

            if changed:
                self.__mark_changed_statement(chunk)

        for i in xrange(statement_end, chunk_start + len(lines)):
            line = lines[i - chunk_start]

            if i > 0:
                chunk = self.__chunks[i - 1]
            else:
                chunk = None

            line_class = calc_line_class(line)
            if line_class == BLANK:
                if not isinstance(chunk, BlankChunk):
                    chunk = BlankChunk()
                    chunk.start = i
                chunk.end = i + 1
                self.__set_line_chunk(i, chunk)
            elif line_class == COMMENT:
                if not isinstance(chunk, CommentChunk):
                    chunk = CommentChunk()
                    chunk.start = i
                chunk.end = i + 1
                self.__set_line_chunk(i, chunk)

    def __rescan(self):
        _debug("  Rescan range %s-%s", self.__rescan_start, self.__rescan_end)
        _debug("  Changed range %s-%s", self.__change_start, self.__change_end)

        if self.__rescan_start == None and self.__change_start == None:
            return

        if self.__rescan_start != None:
            rescan_start = self.__rescan_start
            rescan_end = self.__rescan_end

            while rescan_start > 0:
                rescan_start -= 1
                chunk = self.__chunks[rescan_start]
                if isinstance(chunk, StatementChunk):
                    rescan_start = chunk.start
                    break

            while rescan_end < len(self.__lines):
                chunk = self.__chunks[rescan_end]
                if isinstance(chunk, StatementChunk) and chunk.start == rescan_end:
                    break
                rescan_end += 1

            if self.__change_start != None:
                if self.__change_start < rescan_start:
                    rescan_start = self.__change_start
                if self.__change_end > rescan_end:
                    rescan_end = self.__change_end
        else:
            rescan_start = self.__change_start
            rescan_end = self.__change_end

        self.__rescan_start = None
        self.__rescan_end = None
        self.__change_start = None
        self.__change_end = None

        if self.__chunks[rescan_start] != None:
            rescan_start = self.__chunks[rescan_start].start;
        if self.__chunks[rescan_end - 1] != None:
            rescan_end = self.__chunks[rescan_end - 1].end;

        _debug("  Rescanning lines %s-%s", rescan_start, rescan_end)

        chunk_start = rescan_start
        statement_end = rescan_start
        chunk_lines = []

        for line in xrange(rescan_start, rescan_end):
            line_text = self.__lines[line]

            line_class = calc_line_class(line_text)
            if line_class == BLANK:
                chunk_lines.append(line_text)
            elif line_class == COMMENT:
                chunk_lines.append(line_text)
            elif line_class == CONTINUATION:
                chunk_lines.append(line_text)
                statement_end = line + 1
            else:
                if len(chunk_lines) > 0:
                    self.__assign_lines(chunk_start, chunk_lines, statement_end)
                chunk_start = line
                statement_end = line + 1
                chunk_lines = [line_text]

        self.__assign_lines(chunk_start, chunk_lines, statement_end)

    def __mark_for_rescan(self, start, end):
        if self.__rescan_start == None:
            self.__rescan_start = start
            self.__rescan_end = end
        else:
            if start < self.__rescan_start:
                self.__rescan_start = start
            if end > self.__rescan_end:
                self.__rescan_end = end

    def __mark_change(self, start, end):
        if self.__change_start == None:
            self.__change_start = start
            self.__change_end = end
        else:
            if start < self.__rescan_start:
                self.__change_start = start
            if end > self.__rescan_end:
                self.__change_end = end

    def __set_line(self, line, text):
        if self.__lines[line] != None:
            old_class = calc_line_class(self.__lines[line])
        else:
            old_class = None
        self.__lines[line] = text
        if old_class != calc_line_class(text):
            self.__mark_for_rescan(line, line + 1)
        else:
            self.__mark_change(line, line + 1)

    def begin_user_action(self):
        self.__user_action_count += 1
        self.__undo_stack.begin_user_action()
        self.__freeze_changes()

    def end_user_action(self):
        self.__user_action_count -= 1
        self.__thaw_changes()
        self.__undo_stack.end_user_action()

    def in_user_action(self):
        return self.__user_action_count > 0

    def insert(self, line, offset, text):
        _debug("Inserting %r at %s,%s", text, line, offset)
        if len(text) == 0:
            return

        self.__freeze_changes()

        self.emit('text-inserted', line, offset, text)

        count = 0
        ends_with_new_line = False
        for m in NEW_LINE_RE.finditer(text):
            count += 1
            ends_with_new_line = m.end() == len(text)

        chunk = self.__chunks[line]
        left = self.__lines[line][0:offset]
        right = self.__lines[line][offset:]

        if count == 0:
            self.__set_line(line, left + text + right)
            end_line = line
            end_offset = offset + len(text)
        else:
            if offset == 0 and ends_with_new_line:
                # This is a pure insertion of an integral number of lines
                self.__chunks[line:line] = (None for i in xrange(count))
                self.__lines[line:line] = (None for i in xrange(count))
                self.emit('lines-inserted', line, line + count)

                adjust_start = line + count
            else:
                self.__chunks[line + 1:line + 1] = (chunk for i in xrange(count))
                chunk.line_count += count
                self.__lines[line + 1:line + 1] = (None for i in xrange(count))

                if offset == 0:
                    self.emit('lines-inserted', line, line + count)
                else:
                    self.emit('lines-inserted', line + 1, line + count + 1)

                chunk.end += count
                adjust_start = chunk.end

            iter = NEW_LINE_RE.finditer(text)
            i = line

            m = iter.next()
            self.__set_line(line, left + text[0:m.start()])
            last = m.end()
            i += 1

            while True:
                try:
                    m = iter.next()
                except StopIteration:
                    break

                self.__set_line(i, text[last:m.start()])
                last = m.end()
                i += 1

            if not (offset == 0 and ends_with_new_line):
                self.__set_line(i, text[last:] + right)

            end_line = i
            end_offset = len(text) - last

            for chunk in self.iterate_chunks(adjust_start):
                if chunk.start >= line:
                    chunk.start += count
                if chunk.end >= line:
                    chunk.end += count

        self.__thaw_changes()
        self.__undo_stack.append_op(InsertOp((line, offset), (end_line, end_offset), text))

        if self.__user_action_count > 0 and not self.code_modified:
            self.code_modified = True

    def __delete_lines(self, start_line, end_line):
        if end_line > start_line:
            for i in xrange(start_line,end_line):
                self.__decrement_line_count(self.__chunks[i], i)

            self.__lines[start_line:end_line] = ()
            self.__chunks[start_line:end_line] = ()
            self.__mark_for_rescan(start_line, start_line)
            self.emit('lines-deleted', start_line, end_line)

    def delete_range(self, start_line, start_offset, end_line, end_offset):
        _debug("Deleting from %s,%s to %s,%s", start_line, start_offset, end_line, end_offset)

        if start_line == end_line and start_offset == end_offset:
            return

        self.__freeze_changes()

        start_line, start_offset, end_line, end_offset = order_positions(start_line, start_offset, end_line, end_offset)

        deleted_text = self.get_text(start_line, start_offset, end_line, end_offset)

        self.emit('text-deleted', start_line, start_offset, end_line, end_offset)

        if start_offset == 0 and end_offset == 0:
            # Deleting some whole number of lines
            self.__delete_lines(start_line, end_line)
        else:
            left = self.__lines[start_line][0:start_offset]
            right = self.__lines[end_line][end_offset:]

            if start_offset == 0:
                self.__delete_lines(start_line, end_line)
            else:
                self.__delete_lines(start_line + 1, end_line + 1)

            self.__set_line(start_line, left + right)

        if end_line > start_line:
            for chunk in self.iterate_chunks(start_line):
                if chunk.start <= start_line:
                    pass
                elif chunk.start <= end_line:
                    chunk.start = start_line
                else:
                    chunk.start -= (end_line - start_line)

                if chunk.end > end_line:
                    chunk.end -= (end_line - start_line)

        self.__thaw_changes()
        self.__undo_stack.append_op(DeleteOp((start_line, start_offset), (end_line, end_offset), deleted_text))

        if self.__user_action_count > 0 and not self.code_modified:
            self.code_modified = True

    def place_cursor(self, line, offset):
        _debug("Place cursor at %s,%s", line, offset)
        self.emit('place-cursor', line, offset)

    def undo(self):
        self.__undo_stack.undo()

    def redo(self):
        self.__undo_stack.redo()

    def calculate(self):
        _debug("Calculating")

        self.__freeze_changes()

        parent = None
        have_error = False
        for chunk in self.iterate_chunks():
            if isinstance(chunk, StatementChunk):
                changed = False

                if chunk.needs_compile:
                    _debug("  Compiling %s", chunk);
                    changed = True
                    chunk.compile(self)

                if chunk.needs_execute and not have_error:
                    changed = True
                    _debug("  Executing %s", chunk);
                    chunk.execute(parent)

                if chunk.error_message != None:
                    _debug("   Got error '%s' for %s", chunk.error_message, chunk);
                    have_error = True

                if changed:
                    self.__chunk_changed(chunk);

                parent = chunk.statement

        self.__thaw_changes()

    def __get_last_scope(self, chunk):
        # Get the last result scope we have that precedes the specified chunk

        scope = None
        line = chunk.start - 1
        while line >= 0:
            previous_chunk = self.__chunks[line]

            # We intentionally don't check "needs_execute" ... if there is a result scope,
            # it's fair game for completion/help, even if it's old
            if isinstance(previous_chunk, StatementChunk) and previous_chunk.statement != None and previous_chunk.statement.result_scope != None:
                return previous_chunk.statement.result_scope
                break

            line = previous_chunk.start - 1

        return self.global_scope

    def find_completions(self, line, offset):
        """Returns a list of possible completions at the given position.

        Each element in the returned list is a tuple of (display_form,
        text_to_insert, object_completed_to)' where
        object_completed_to can be used to determine the type of the
        completion or get docs about it.

        """

        chunk = self.__chunks[line]
        if not isinstance(chunk, StatementChunk) and not isinstance(chunk, BlankChunk):
            return []

        scope = self.__get_last_scope(chunk)

        if isinstance(chunk, StatementChunk):
            return chunk.tokenized.find_completions(line - chunk.start,
                                                    offset,
                                                    scope)
        else:
            # A BlankChunk Create a dummy TokenizedStatement to get the completions
            # appropriate for the start of a line
            ts = TokenizedStatement()
            ts.set_lines([''])
            return ts.find_completions(0, 0, scope)

    def get_object_at_location(self, line, offset, include_adjacent=False):
        """Find the object at a particular location within the worksheet

        include_adjacent -- if False, then location identifies a character in the worksheet. If True,
           then location identifies a position between characters, and symbols before or after that
           position are included.

        Returns a tuple of (object, start_line, start_offset, end_line, end_offset) or (None, None, None, None, None)

        """

        chunk = self.__chunks[line]
        if not isinstance(chunk, StatementChunk):
            return None, None, None, None, None

        if chunk.statement != None and chunk.statement.result_scope != None:
            result_scope = chunk.statement.result_scope
        else:
            result_scope = None

        obj, start_line, start_index, end_line, end_index = \
            chunk.tokenized.get_object_at_location(line - chunk.start, offset,
                                                   self.__get_last_scope(chunk),
                                                   result_scope, include_adjacent)

        if obj == None:
            return None, None, None, None, None

        start_line += chunk.start
        end_line += chunk.start

        return obj, start_line, start_index, end_line, end_index

    def __do_clear(self):
        self.delete_range(0, 0, len(self.__lines) - 1, len(self.__lines[len(self.__lines) - 1]));

    def clear(self):
        self.__do_clear()
        self.__set_filename_and_modified(None, False)

        # XXX: This prevents redoing New, would that "just work"?
        self.__undo_stack.clear()

    def get_text(self, start_line=0, start_offset=0, end_line=-1, end_offset=-1):
        if start_line < 0:
            start_line = len(self.__lines) -1
        if end_line < 0:
            end_line = len(self.__lines) -1
        if start_offset < 0:
            start_offset = len(self.__lines[start_line])
        if end_offset < 0:
            end_offset = len(self.__lines[end_line])

        start_line, start_offset, end_line, end_offset = order_positions(start_line, start_offset, end_line, end_offset)

        if start_line == end_line:
            return self.__lines[start_line][start_offset:end_offset]

        si = StringIO()

        line = start_line
        si.write(self.__lines[line][start_offset:])
        line += 1

        while line < end_line:
            si.write("\n")
            si.write(self.__lines[line][start_offset:])
            line += 1

        si.write("\n")
        si.write(self.__lines[line][:end_offset])

        return si.getvalue()

    def get_doctests(self, start_line, end_line):
        si = StringIO()

        first = True
        for chunk in self.iterate_chunks(start_line, end_line + 1):
            for i in xrange(chunk.start, chunk.end):
                line_text = self.__lines[i]
                if isinstance(chunk, StatementChunk):
                    if i != chunk.start:
                        si.write("... ")
                    else:
                        si.write(">>> ")
                si.write(line_text)
                # Don't turn a trailing newline into two
                if i != len(self.__lines) - 1 or len(line_text) > 0:
                    si.write("\n")

            if isinstance(chunk, StatementChunk) and chunk.results != None:
                for result in chunk.results:
                    if isinstance(result, basestring):
                        si.write(result)
                        si.write("\n")

        return si.getvalue()

    def get_line_count(self):
        return len(self.__lines)

    def get_chunk(self, line):
        return self.__chunks[line]

    def get_line(self, line):
        return self.__lines[line]

    def __set_filename_and_modified(self, filename, modified):
        self.freeze_notify()
        self.filename = filename
        self.code_modified = modified
        self.thaw_notify()

    def load(self, filename):
        f = open(filename)
        text = f.read()
        f.close()

        self.__do_clear()
        self.__set_filename_and_modified(filename, False)
        self.insert(0, 0, text)
        self.__undo_stack.clear()

    def save(self, filename=None):
        if filename == None:
            if self.filename == None:
                raise ValueError("No current or specified filename")

            filename = self.filename

        tmpname = filename + ".tmp"

        # We use binary mode, since we don't want to munge line endings to the system default
        # on a load-save cycle
        f = open(tmpname, "wb")

        success = False
        try:
            first = True
            for line in self.__lines:
                if not first:
                    f.write("\n")
                first = False
                f.write(line)

            f.close()
            # Windows can't save over an existing filename; we might want to check os.name to
            # see if we have to do this, but it's unlikely that the unlink will succeed and
            # the rename fail, so I think it's 'atomic' enough this way.
            if os.path.exists(filename):
                os.unlink(filename)
            os.rename(tmpname, filename)
            success = True

            self.__set_filename_and_modified(filename, False)
        finally:
            if not success:
                f.close()
                os.remove(tmpname)

######################################################################

if __name__ == '__main__': #pragma: no cover
    if "-d" in sys.argv:
        logging.basicConfig(level=logging.DEBUG, format="DEBUG: %(message)s")

    import stdout_capture
    stdout_capture.init()

    S = StatementChunk
    B = BlankChunk
    C = CommentChunk

    def compare(l1, l2):
        if len(l1) != len(l2):
            return False

        for i in xrange(0, len(l1)):
            e1 = l1[i]
            e2 = l2[i]

            if type(e1) != type(e2) or e1.start != e2.start or e1.end != e2.end:
                return False

        return True

    worksheet = Worksheet(Notebook())

    def expect(expected):
        chunks = [ x for x in worksheet.iterate_chunks() ]
        if not compare(chunks, expected):
            raise AssertionError("\nGot:\n   %s\nExpected:\n   %s" % (chunks, expected))

    def expect_text(expected, start_line=0, start_offset=0, end_line=-1, end_offset=-1):
        text = worksheet.get_text(start_line, start_offset, end_line, end_offset)
        if (text != expected):
            raise AssertionError("\nGot:\n   '%s'\nExpected:\n   '%s'" % (text, expected))

    def expect_doctests(expected, start_line, end_line):
        text = worksheet.get_doctests(start_line, end_line)
        if (text != expected):
            raise AssertionError("\nGot:\n   '%s'\nExpected:\n   '%s'" % (text, expected))

    def expect_results(expected):
        results = [ (x.results if isinstance(x,StatementChunk) else None) for x in worksheet.iterate_chunks() ]
        if (results != expected):
            raise AssertionError("\nGot:\n   '%s'\nExpected:\n   '%s'" % (results, expected))

    def insert(line, offset, text):
        worksheet.insert(line, offset, text)

    def delete(start_line, start_offset, end_line, end_offset):
        worksheet.delete_range(start_line, start_offset, end_line, end_offset)

    def calculate():
        worksheet.calculate()

    def clear():
        worksheet.clear()

    def chunk_label(chunk):
        if chunk.end - chunk.start == 1:
            return "[%s]" % chunk.start
        else:
            return "[%s:%s]" % (chunk.start, chunk.end)

    class CI:
        def __init__(self, start, end):
            self.start = start
            self.end = end

        def __eq__(self, other):
            if not isinstance(other, CI):
                return False

            return self.start == other.start and self.end == other.end

        def __repr__(self):
            return "CI(%s, %s)" % (self.start, self.end)

    class CC:
        def __init__(self, start, end, changed_lines):
            self.start = start
            self.end = end
            self.changed_lines = changed_lines

        def __eq__(self, other):
            if not isinstance(other, CC):
                return False

            return self.start == other.start and self.end == other.end and self.changed_lines == other.changed_lines

        def __repr__(self):
            return "CC(%s, %s, %s)" % (self.start, self.end, self.changed_lines)

    class CD:
        def __eq__(self, other):
            if not isinstance(other, CD):
                return False

            return True

        def __repr__(self):
            return "CD()"

    class CSC:
        def __init__(self, start, end):
            self.start = start
            self.end = end

        def __eq__(self, other):
            if not isinstance(other, CSC):
                return False

            return self.start == other.start and self.end == other.end

        def __repr__(self):
            return "CSC(%s, %s)" % (self.start, self.end)

    class CRC:
        def __init__(self, start, end):
            self.start = start
            self.end = end

        def __eq__(self, other):
            if not isinstance(other, CRC):
                return False

            return self.start == other.start and self.end == other.end

        def __repr__(self):
            return "CRC(%s, %s)" % (self.start, self.end)

    log = []

    def on_chunk_inserted(worksheet, chunk):
        _debug("...Chunk %s inserted", chunk_label(chunk))
        log.append(CI(chunk.start, chunk.end))

    def on_chunk_changed(worksheet, chunk, changed_lines):
        _debug("...Chunk %s changed", chunk_label(chunk))
        log.append(CC(chunk.start, chunk.end, changed_lines))

    def on_chunk_deleted(worksheet, chunk):
        _debug("...Chunk %s deleted", chunk_label(chunk))
        log.append(CD())

    def on_chunk_status_changed(worksheet, chunk):
        _debug("...Chunk %s status changed", chunk_label(chunk))
        log.append(CSC(chunk.start, chunk.end))

    def on_chunk_results_changed(worksheet, chunk):
        _debug("...Chunk %s results changed", chunk_label(chunk))
        log.append(CRC(chunk.start, chunk.end))

    def clear_log():
        global log
        log = []

    def expect_log(expected):
        if log != expected:
            raise AssertionError("\nGot:\n   '%s'\nExpected:\n   '%s'" % (log, expected))
        clear_log()

    worksheet.connect('chunk-inserted', on_chunk_inserted)
    worksheet.connect('chunk-changed', on_chunk_changed)
    worksheet.connect('chunk-deleted', on_chunk_deleted)
    worksheet.connect('chunk-status-changed', on_chunk_status_changed)
    worksheet.connect('chunk-results-changed', on_chunk_results_changed)

    # Insertions
    insert(0, 0, "11\n22\n33")
    expect_text("11\n22\n33")
    expect([S(0,1), S(1,2), S(2,3)])
    insert(0, 1, "a")
    expect_text("1a1\n22\n33")
    expect([S(0,1), S(1,2), S(2,3)])
    insert(1, 1, "a\na")
    expect_text("1a1\n2a\na2\n33")
    expect([S(0,1), S(1,2), S(2,3), S(3,4)])
    insert(1, 0, "bb\n")
    expect_text("1a1\nbb\n2a\na2\n33")
    expect([S(0,1), S(1,2), S(2,3), S(3,4), S(4, 5)])
    insert(4, 3, "\n")
    expect_text("1a1\nbb\n2a\na2\n33\n")
    expect([S(0,1), S(1,2), S(2,3), S(3,4), S(4, 5), B(5, 6)])

    # Deletions
    delete(4, 3, 5, 0)
    expect_text("1a1\nbb\n2a\na2\n33")
    expect([S(0,1), S(1,2), S(2,3), S(3,4), S(4, 5)])
    delete(0, 1, 0, 2)
    expect_text("11\nbb\n2a\na2\n33")
    expect([S(0,1), S(1,2), S(2,3), S(3,4), S(4, 5)])
    delete(0, 0, 1, 0)
    expect_text("bb\n2a\na2\n33")
    expect([S(0,1), S(1,2), S(2,3), S(3,4)])
    delete(1, 1, 2, 1)
    expect_text("bb\n22\n33")
    expect([S(0,1), S(1,2), S(2,3)])
    delete(2, 1, 1, 0)
    expect_text("bb\n3")
    expect([S(0,1), S(1,2)])

    # Basic tokenization of valid python
    clear()
    insert(0, 0, "1\n\n#2\ndef a():\n  3")
    expect([S(0,1), B(1,2), C(2,3), S(3,5)])

    clear()
    expect([B(0,1)])

    # Calculation
    clear()
    insert(0, 0, "1 + 1")
    calculate()
    expect_results([['2']])

    clear()
    insert(0, 0, "if True:\n    print 1\n    print 1")
    calculate()
    expect_results([['1', '1']])

    clear()
    insert(0, 0, "a = 1\nb = 2\na + b")
    calculate()
    expect_results([[], [], ['3']])
    delete(1, 4, 1, 5)
    insert(1, 4, "3")
    calculate()
    expect_results([[], [], ['4']])

    #
    # Test out signals and expect_log()
    #
    clear()
    clear_log()
    insert(0, 0, "1 + 1")
    expect_log([CI(0,1)])
    calculate()
    expect_log([CSC(0,1), CRC(0,1)])

    insert(0, 0, "#")
    expect_log([CD()])

    # Deleting a chunk with results
    clear()
    insert(0, 0, "1\n2")
    calculate()
    expect([S(0,1),S(1,2)])
    expect_results([['1'],['2']])
    clear_log()
    delete(0, 0, 0, 1)
    expect([B(0,1),S(1,2)])
    expect_log([CD(), CSC(1,2)])

    # Turning a statement into a continuation line
    clear()
    insert(0, 0, "1 \\\n+ 2\n")
    clear_log()
    insert(1, 0, " ")
    expect([S(0,2), B(2,3)])
    expect_log([CD(), CC(0,2,[1])])

    # And back
    delete(1, 0, 1, 1)
    expect([S(0,1), S(1,2), B(2,3)])
    expect_log([CC(0,1,[]),CI(1,2)])

    # Deleting an entire continuation line
    clear()

    insert(0, 0, "for i in (1,2):\n    print i\n    print i + 1\n")
    expect([S(0,3), B(3,4)])
    delete(1, 0, 2, 0)
    expect([S(0,2), B(2,3)])

    # Editing a continuation line, while leaving it a continuation
    clear()

    insert(0, 0, "1\\\n  + 2\\\n  + 3")
    delete(1, 0, 1, 1)
    expect([S(0,3)])

    # Test that commenting out a line marks subsequent lines for recalculation
    clear()

    insert(0, 0, "a = 1\na = 2\na")
    worksheet.calculate()
    insert(1, 0, "#")
    assert worksheet.get_chunk(2).needs_execute

    #
    # Undo tests
    #
    clear()

    insert(0, 0, "1")
    worksheet.undo()
    expect_text("")
    worksheet.redo()
    expect_text("1")

    # Undoing insertion of a newline
    clear()

    insert(0, 0, "1 ")
    insert(0, 1, "\n")
    worksheet.calculate()
    worksheet.undo()
    expect_text("1 ")

    # Test the "pruning" behavior of modifications after undos
    clear()

    insert(0, 0, "1")
    worksheet.undo()
    expect_text("")
    insert(0, 0, "2")
    worksheet.redo() # does nothing
    expect_text("2")
    insert(0, 0, "2\n")

    # Test coalescing consecutive inserts
    clear()

    insert(0, 0, "1")
    insert(0, 1, "2")
    worksheet.undo()
    expect_text("")

    # Test grouping of multiple undos by user actions
    clear()

    insert(0, 0, "1")
    worksheet.begin_user_action()
    delete(0, 0, 0, 1)
    insert(0, 0, "2")
    worksheet.end_user_action()
    worksheet.undo()
    expect_text("1")
    worksheet.redo()
    expect_text("2")

    # Make sure that coalescing doesn't coalesce one user action with
    # only part of another
    clear()

    insert(0, 0, "1")
    worksheet.begin_user_action()
    insert(0, 1, "2")
    delete(0, 0, 0, 1)
    worksheet.end_user_action()
    worksheet.undo()
    expect_text("1")
    worksheet.redo()
    expect_text("2")

    #
    # Tests of get_text()
    #
    clear()
    insert(0, 0, "12\n34\n56")
    expect_text("12\n34\n56", -1, -1, 0, 0)
    expect_text("", -1, -1, -1, -1)
    expect_text("1", 0, 0, 0, 1)
    expect_text("2\n3", 0, 1, 1, 1)
    expect_text("2\n3", 1, 1, 0, 1)

    #
    # Tests of get_doctests()
    #
    clear()
    insert(0, 0, """# A tests of doctests
def a(x):
    return x + 1

a(2)
""")
    calculate()

    expect_doctests("""# A tests of doctests
>>> def a(x):
...     return x + 1

>>> a(2)
3
""", 0, 5)

    expect_doctests(""">>> def a(x):
...     return x + 1
""", 2, 2)

    #
    # Try writing to a file, and reading it back
    #
    import tempfile, os

    clear()
    expect([B(0,1)])

    SAVE_TEST = """a = 1
a
# A comment

b = 2"""

    insert(0, 0, SAVE_TEST)
    worksheet.calculate()

    handle, fname = tempfile.mkstemp(".rws", "reinteract_worksheet")
    os.close(handle)

    try:
        worksheet.save(fname)
        f = open(fname, "r")
        saved = f.read()
        f.close()

        if saved != SAVE_TEST:
            raise AssertionError("Got '%s', expected '%s'", saved, SAVE_TEST)

        worksheet.load(fname)
        worksheet.calculate()

        expect_text(SAVE_TEST)
        expect([S(0,1), S(1,2), C(2,3), B(3,4), S(4,5)])
        expect_results([[], ['1'], None, None, []])
    finally:
        os.remove(fname)

    clear()
    expect([B(0,1)])
