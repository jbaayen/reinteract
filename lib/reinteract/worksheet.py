# Copyright 2008-2009 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import sys

import gobject
import logging
import os
import re
from StringIO import StringIO

from change_range import ChangeRange
from chunks import *
from notebook import Notebook, NotebookFile
import reunicode
from statement import Statement
from thread_executor import ThreadExecutor
from undo_stack import UndoStack, InsertOp, DeleteOp

_debug = logging.getLogger("Worksheet").debug

_DEFINE_GLOBALS = compile("""
global reinteract_output
def reinteract_output(*args):
   __reinteract_statement.do_output(*args)
""", __name__, 'exec')

BLANK_RE = re.compile(r'^\s*$')
BLANK = 0
COMMENT_RE = re.compile(r'^\s*#')
COMMENT = 1
STATEMENT_START = 2
CONTINUATION_RE = re.compile(r'^(?:\s+|(?:else|elif|except|finally)[^A-Za-z0-9_])')
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
        # Chunk changed is emitted when the text or tokenization of a chunk
        # changes. Note that "changes" here specifically includes being
        # replaced by identical text, so if I have the two chunks
        #
        #  if
        #  if
        #
        # And I delete the from the first 'i' to the second f, the first
        # chunk is considered to change, even though it's text remains 'if'.
        # This is because text in a buffering that is shadowing us may
        # be tagged with fonts/styles.
        #
        'chunk-changed': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT)),
        'chunk-deleted': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        'chunk-status-changed': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        'chunk-results-changed': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        # This is only for the convenience of the undo stack; otherwise we ignore cursor position
        'place-cursor': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (int, int))
    }

    def __init__(self, notebook, edit_only=False):
        gobject.GObject.__init__(self)

        self.notebook = notebook
        self.edit_only = edit_only
        self.__file = None
        self.__filename = None
        self.__code_modified = False

        self.global_scope = {}
        notebook.setup_globals(self.global_scope)
        exec _DEFINE_GLOBALS in self.global_scope

        self.__lines = [""]
        self.__chunks = [BlankChunk(0,1)]

        # There's quite a bit of complexity knowing when a change to lines changes
        # adjacent chunks. We use a simple and slightly inefficient algorithm for this
        # and just scan everything that might have changed. But we don't want typing
        # within a line to cause an unlimited rescan, so we keep track if the only
        # changes we've made are inserting/deleting within a line without changing
        # that lines class
        self.__changes = ChangeRange()
        self.__scan_adjacent = False

        self.__changed_chunks = set()
        self.__deleted_chunks = set()
        self.__freeze_changes_count = 0
        self.__user_action_count = 0

        self.__undo_stack = UndoStack(self)

        notebook._add_worksheet(self)

    def do_import(self, name, globals, locals, fromlist, level):
        __import__(self, name, globals, locals, fromlist, level)

    def iterate_chunks(self, start_line=0, end_line=None):
        if end_line is None or end_line > len(self.__chunks):
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
            self.rescan()
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
                chunk.changes.clear()
                chunk.status_changed = False
                self.emit('chunk-inserted', chunk)
            elif not chunk.changes.empty():
                changed_lines = range(chunk.changes.start, chunk.changes.end)
                chunk.changes.clear()
                chunk.status_changed = False
                self.emit('chunk-changed', chunk, changed_lines)
            if isinstance(chunk, StatementChunk) and chunk.status_changed:
                chunk.status_changed = False
                self.emit('chunk-status-changed', chunk)
            if isinstance(chunk, StatementChunk) and chunk.results_changed:
                chunk.results_changed = False
                self.emit('chunk-results-changed', chunk)

    def __chunk_changed(self, chunk):
        self.__changed_chunks.add(chunk)

    def __mark_rest_for_execute(self, start_line):
        if self.state != NotebookFile.NEEDS_EXECUTE:
            self.__set_state(NotebookFile.NEEDS_EXECUTE)

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

    def __remove_chunk(self, chunk):
        try:
            self.__changed_chunks.remove(chunk)
        except KeyError:
            pass
        if not chunk.newly_inserted:
            self.__deleted_chunks.add(chunk)
        if isinstance(chunk, StatementChunk):
            self.__mark_rest_for_execute(chunk.end)

    def __adjust_or_create_chunk(self, start, end, line_class):
        if line_class == BLANK:
            klass = BlankChunk
        elif line_class == COMMENT:
            klass = CommentChunk
        else:
            klass = StatementChunk

        # Look for an existing chunk of the right type
        chunk = None
        for i in xrange(start, end):
            if isinstance(self.__chunks[i], klass):
                chunk = self.__chunks[i]
                break

        if chunk is not None:
            if chunk.end > end:
                # An old statement can only be turned into *one* new statement; once
                # we've used the chunk, we can't use it again
                self.__chunks[end:chunk.end] = (None for i in xrange(end, chunk.end))
        else:
            chunk = klass()

        chunk.set_range(start, end)
        for c in self.iterate_chunks(start, end):
            assert c.start >= start

            if c == chunk:
                pass
            elif c.end <= end:
                self.__remove_chunk(c)
            else:
                c.set_range(end, c.end)

        self.__chunks[start:end] = (chunk for i in xrange(start, end))

        return chunk

    def __assign_lines(self, chunk_start, lines, statement_end):
        if statement_end > chunk_start:
            chunk_lines = lines[0:statement_end - chunk_start]
            chunk = self.__adjust_or_create_chunk(chunk_start, statement_end, STATEMENT_START)
            chunk.set_lines(chunk_lines)

            if not chunk.changes.empty():
                self.__mark_changed_statement(chunk)

        start = statement_end
        prev_class = CONTINUATION # Doesn't matter, not blank/continuation
        for i in xrange(statement_end, chunk_start + len(lines)):
            line_class = calc_line_class(self.__lines[i])
            if line_class != prev_class and i > start:
                chunk = self.__adjust_or_create_chunk(start, i, prev_class)
                if not chunk.changes.empty():
                    self.__chunk_changed(chunk)
                start = i
            prev_class = line_class

        if chunk_start + len(lines) > start:
            chunk = self.__adjust_or_create_chunk(start, chunk_start + len(lines), prev_class)
            if not chunk.changes.empty():
                self.__chunk_changed(chunk)

    def rescan(self):
        """Update the division of the worksheet into chunks based on the current text.

        As the buffer is edited, the division of the buffer into chunks is updated
        blindly without attention to the details of the new text. Normally, we will
        rescan and figure out the real chunks at the end of a user operation, however
        it is occasionally useful to do this early, for example, if we want to use
        the tokenized representation of a statement for the second part of a user
        operation.

        """

        _debug("  Changed %s,%s (%s), scan_adjacent=%d", self.__changes.start, self.__changes.end, self.__changes.delta, self.__scan_adjacent)

        if self.__changes.empty():
            return

        if self.__scan_adjacent:
            rescan_start = self.__changes.start
            rescan_end = self.__changes.end

            while rescan_start > 0:
                rescan_start -= 1
                chunk = self.__chunks[rescan_start]
                if isinstance(chunk, StatementChunk):
                    rescan_start = chunk.start
                    break

            while rescan_end < len(self.__lines):
                chunk = self.__chunks[rescan_end]
                # The check for continuation line is needed because the first statement
                # in a buffer can start with a continuation line
                if isinstance(chunk, StatementChunk) and \
                        chunk.start == rescan_end and \
                        not CONTINUATION_RE.match(self.__lines[chunk.start]):
                    break
                rescan_end = chunk.end
        else:
            rescan_start = self.__changes.start
            rescan_end = self.__changes.end

        self.__changes.clear()
        self.__scan_adjacent = False

        if self.__chunks[rescan_start] is not None:
            rescan_start = self.__chunks[rescan_start].start;
        if self.__chunks[rescan_end - 1] is not None:
            rescan_end = self.__chunks[rescan_end - 1].end;

        _debug("  Rescanning lines %s-%s", rescan_start, rescan_end)

        chunk_start = rescan_start
        statement_end = rescan_start
        chunk_lines = []

        seen_start = False
        for line in xrange(rescan_start, rescan_end):
            line_text = self.__lines[line]

            line_class = calc_line_class(line_text)
            if line_class == BLANK:
                chunk_lines.append(line_text)
            elif line_class == COMMENT:
                chunk_lines.append(line_text)
            elif line_class == CONTINUATION and seen_start:
                chunk_lines.append(line_text)
                statement_end = line + 1
            else:
                seen_start = True
                if len(chunk_lines) > 0:
                    self.__assign_lines(chunk_start, chunk_lines, statement_end)
                chunk_start = line
                statement_end = line + 1
                chunk_lines = [line_text]

        self.__assign_lines(chunk_start, chunk_lines, statement_end)

    def __set_line(self, line, text):
        if self.__lines[line] is not None:
            old_class = calc_line_class(self.__lines[line])
        else:
            old_class = None
        self.__lines[line] = text
        if old_class != calc_line_class(text):
            self.__scan_adjacent = True
        self.__changes.change(line, line + 1)

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

    def __insert_lines(self, line, count, chunk):
        # Insert an integral number of lines into the given chunk at the given position
        # fixing up the chunk and the __chunks[]/__lines[] arrays

        self.__chunks[line:line] = (chunk for i in xrange(count))
        self.__lines[line:line] = (None for i in xrange(count))
        chunk.insert_lines(line, count)

        # Fix up the subsequent chunks
        for c in self.iterate_chunks(chunk.end):
            c.start += count
            c.end += count

        self.__changes.insert(line, count)
        self.__scan_adjacent = True
        self.__chunk_changed(chunk)
        self.emit('lines-inserted', line, line + count)

    def insert(self, line, offset, text):
        _debug("Inserting %r at %s,%s", text, line, offset)
        if len(text) == 0:
            return

        if self.state == NotebookFile.EXECUTING:
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
            # Change within a single line
            self.__set_line(line, left + text + right)
            chunk.change_line(line)
            end_line = line
            end_offset = offset + len(text)
        else:
            if offset == 0 and ends_with_new_line:
                # This is a pure insertion of an integral number of lines

                # At a chunk boundary, extend the chunk before, not the chunk after
                if line > 0 and chunk.start == line:
                    chunk = self.__chunks[line - 1]

                self.__insert_lines(line, count, chunk)
            else:
                if offset == 0:
                    self.__insert_lines(line, count, chunk)
                    chunk.change_line(line + count)
                else:
                    self.__insert_lines(line + 1, count, chunk)
                    chunk.change_line(line)

            # Now set the new text into the lines array
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

        self.__thaw_changes()
        self.__undo_stack.append_op(InsertOp((line, offset), (end_line, end_offset), text))

        if self.__user_action_count > 0 and not self.code_modified:
            self.code_modified = True

    def __delete_lines(self, start_line, end_line):
        # Delete an integral number of lines, fixing up the affected chunks
        # and the __chunks[]/__lines[] arrays

        if end_line == start_line: # No lines deleted
            return

        for chunk in self.iterate_chunks(start_line):
            if chunk.start >= end_line:
                chunk.start -= (end_line - start_line)
                chunk.end -= (end_line - start_line)
            elif chunk.start >= start_line:
                if chunk.end <= end_line:
                    self.__remove_chunk(chunk)
                else:
                    chunk.delete_lines(chunk.start, end_line)
                    self.__chunk_changed(chunk)
                    chunk.end -= chunk.start - start_line
                    chunk.start = start_line
            else:
                chunk.delete_lines(start_line, min(chunk.end, end_line))
                self.__chunk_changed(chunk)

        self.__lines[start_line:end_line] = ()
        self.__chunks[start_line:end_line] = ()

        self.__changes.delete_range(start_line, end_line)
        self.__scan_adjacent = True
        self.emit('lines-deleted', start_line, end_line)

    def delete_range(self, start_line, start_offset, end_line, end_offset):
        _debug("Deleting from %s,%s to %s,%s", start_line, start_offset, end_line, end_offset)

        if self.state == NotebookFile.EXECUTING:
            return

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
            chunk = self.__chunks[start_line]
            chunk.change_line(start_line)
            self.__chunk_changed(chunk)

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

    def module_changed(self, module_name):
        """Mark statements for execution after a change to the given module"""

        for chunk in self.iterate_chunks():
            if not isinstance(chunk, StatementChunk):
                continue
            if chunk.statement is None:
                continue

            imports = chunk.statement.imports
            if imports is None:
                continue

            for module, _ in imports:
                if module == module_name:
                    self.__mark_rest_for_execute(chunk.start)

    def calculate(self, wait=False):
        _debug("Calculating")

        self.__freeze_changes()

        parent = None
        have_error = False

        executor = None

        for chunk in self.iterate_chunks():
            if isinstance(chunk, StatementChunk):
                changed = False

                if chunk.needs_compile or chunk.needs_execute:
                    if not executor:
                        executor = ThreadExecutor(parent)

                if executor:
                    statement = chunk.get_statement(self)
                    executor.add_statement(statement)

                parent = chunk.statement

        if executor:
            if wait:
                loop = gobject.MainLoop()

            def on_statement_execution_state_changed(executor, statement):
                if (statement.state == Statement.COMPILE_ERROR or
                    statement.state == Statement.EXECUTE_ERROR or
                    statement.state == Statement.INTERRUPTED):
                    self.__executor_error = True

                statement.chunk.update_statement()

                if self.__freeze_changes_count == 0:
                    self.__freeze_changes()
                    self.__chunk_changed(statement.chunk)
                    self.__thaw_changes()
                else:
                    self.__chunk_changed(statement.chunk)

            def on_complete(executor):
                self.__executor = None
                self.__set_state(NotebookFile.ERROR if self.__executor_error else NotebookFile.EXECUTE_SUCCESS)
                if wait:
                    loop.quit()

            self.__executor = executor
            self.__executor_error = False
            self.__set_state(NotebookFile.EXECUTING)
            executor.connect('statement-executing', on_statement_execution_state_changed)
            executor.connect('statement-complete', on_statement_execution_state_changed)
            executor.connect('complete', on_complete)

            if executor.compile():
                executor.execute()
                if wait:
                    loop.run()
        else:
            # Nothing to execute, we could have been in a non-success state if statements were deleted
            # at the end of the file.
            self.__set_state(NotebookFile.EXECUTE_SUCCESS)

        self.__thaw_changes()

    def interrupt(self):
        if self.state == NotebookFile.EXECUTING:
            self.__executor.interrupt()

    def __get_last_scope(self, chunk):
        # Get the last result scope we have that precedes the specified chunk

        scope = None
        line = chunk.start - 1
        while line >= 0:
            previous_chunk = self.__chunks[line]

            # We intentionally don't check "needs_execute" ... if there is a result scope,
            # it's fair game for completion/help, even if it's old
            if isinstance(previous_chunk, StatementChunk) and previous_chunk.statement is not None and previous_chunk.statement.result_scope is not None:
                return previous_chunk.statement.result_scope
                break

            line = previous_chunk.start - 1

        return self.global_scope

    def find_completions(self, line, offset, min_length=0):
        """Returns a list of possible completions at the given position.

        Each element in the returned list is a tuple of (display_form,
        text_to_insert, object_completed_to)' where
        object_completed_to can be used to determine the type of the
        completion or get docs about it.

        @param min_length if supplied, the minimum length to require for an isolated
           name before we complete against the scope. This is useful if we are suggesting
           completions without the user explicitly requesting it.

        """

        chunk = self.__chunks[line]
        if not isinstance(chunk, StatementChunk) and not isinstance(chunk, BlankChunk):
            return []

        scope = self.__get_last_scope(chunk)

        if isinstance(chunk, StatementChunk):
            return chunk.tokenized.find_completions(line - chunk.start,
                                                    offset,
                                                    scope,
                                                    min_length=min_length)
        else:
            # A BlankChunk Create a dummy TokenizedStatement to get the completions
            # appropriate for the start of a line
            ts = TokenizedStatement()
            ts.set_lines([''])
            return ts.find_completions(0, 0, scope, min_length=min_length)

    def get_object_at_location(self, line, offset, include_adjacent=False):
        """Find the object at a particular location within the worksheet

        @param include_adjacent: if False, then location identifies a character in the worksheet. If True,
           then location identifies a position between characters, and symbols before or after that
           position are included.

        @returns: a tuple of (object, start_line, start_offset, end_line, end_offset) or (None, None, None, None, None)

        """

        chunk = self.__chunks[line]
        if not isinstance(chunk, StatementChunk):
            return None, None, None, None, None

        if chunk.statement is not None and chunk.statement.result_scope is not None:
            result_scope = chunk.statement.result_scope
        else:
            result_scope = None

        obj, start_line, start_index, end_line, end_index = \
            chunk.tokenized.get_object_at_location(line - chunk.start, offset,
                                                   self.__get_last_scope(chunk),
                                                   result_scope, include_adjacent)

        if obj is None:
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

            if isinstance(chunk, StatementChunk) and chunk.results is not None:
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

    def __set_state(self, new_state):
        if self.edit_only:
            return
        self.state = new_state
        if self.__file:
            self.__file.state = new_state

    def __set_filename(self, filename):
        if filename == self.__filename:
            return

        if self.__file:
            self.__file.worksheet = None
            self.__file.modified = False
            self.__file.active = False

        self.__filename = filename
        if filename:
            self.__file = self.notebook.file_for_absolute_path(self.__filename)
            if self.__file:
                self.__file.worksheet = self
                self.__file.active = True
                self.__file.modified = self.__code_modified
        else:
            self.__file = None

    def __get_filename(self):
        return self.__filename

    filename = gobject.property(getter=__get_filename, setter=__set_filename, type=str, default=None)

    @gobject.property
    def file(self):
        return self.__file

    def __set_code_modified(self, code_modified):
        if code_modified == self.__code_modified:
            return

        self.__code_modified = code_modified
        if self.__file:
            self.__file.modified = code_modified

    def __get_code_modified(self):
        return self.__code_modified

    code_modified = gobject.property(getter=__get_code_modified, setter=__set_code_modified, type=bool, default=False)
    state = gobject.property(type=int, default=NotebookFile.EXECUTE_SUCCESS)

    def __set_filename_and_modified(self, filename, modified):
        self.freeze_notify()
        self.filename = filename
        self.code_modified = modified
        self.thaw_notify()

    def load(self, filename, escape=False):
        """Load a file from disk into the worksheet. Can raise IOError if the
        file cannot be read, and reunicode.ConversionError if the file contains
        invalid characters. (reunicode.ConversionError will not be raised if
        escape is True)

        @param filename the file to load
        @param escape if true, invalid byte and character sequences in the input
           will be converted into \\x<nn> and \\u<nnnn> escape sequences.

        """
        f = open(filename)
        text = f.read()
        f.close()

        self.__do_clear()
        self.insert(0, 0, reunicode.decode(text, escape=escape))
        # A bit of a hack - we assume that if escape was passed we *did* escape.
        # this is the way that things work currently - first the GUI loads with
        # escape=False, and if that fails, prompts the user and loads with escape=True
        self.__set_filename_and_modified(filename, escape)
        self.__undo_stack.clear()

    def save(self, filename=None):
        if filename is None:
            if self.__filename is None:
                raise ValueError("No current or specified filename")

            filename = self.__filename

        if not self.code_modified and filename == self.__filename:
            return

        filename_changed = filename != self.__filename

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
                f.write(line.encode("utf8"))

            f.close()
            # Windows can't save over an existing filename; we might want to check os.name to
            # see if we have to do this, but it's unlikely that the unlink will succeed and
            # the rename fail, so I think it's 'atomic' enough this way.
            if os.path.exists(filename):
                os.unlink(filename)
            os.rename(tmpname, filename)
            success = True

            # Need to refresh the notebook before saving so that we find the NotebookFile
            # properly in __set_filename_and_modified
            if filename_changed:
                self.notebook.refresh()
            self.__set_filename_and_modified(filename, False)
            if self.notebook.info:
                self.notebook.info.update_last_modified()
        finally:
            if not success:
                f.close()
                try:
                    os.remove(tmpname)
                except:
                    pass

    def close(self):
        if self.__file:
            self.__file.worksheet = None
            self.__file.modified = False
            self.__file.state = NotebookFile.NONE
            self.__file.active = False

        self.notebook._remove_worksheet(self)

######################################################################

if __name__ == '__main__': #pragma: no cover
    if "-d" in sys.argv:
        logging.basicConfig(level=logging.DEBUG, format="DEBUG: %(message)s")

    gobject.threads_init()

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
        worksheet.calculate(wait=True)

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

    # Test deleting part of a BlankChunk
    clear()
    insert(0, 0, "if True\n:    pass\n    \n")
    delete(2, 4, 3, 0)

    # Check that tracking of changes works properly when there
    # is an insertion or deletion before the change
    clear()
    insert(0, 0, "1\n2")
    worksheet.begin_user_action()
    insert(1, 0, "#")
    insert(0, 0, "0\n")
    worksheet.end_user_action()
    expect_text("0\n1\n#2")
    expect([S(0,1), S(1,2), C(2,3)])
    worksheet.begin_user_action()
    delete(2, 0, 2, 1)
    delete(0, 0, 1, 0)
    worksheet.end_user_action()
    expect([S(0,1), S(1,2)])

    # Basic tokenization of valid python
    clear()
    insert(0, 0, "1\n\n#2\ndef a():\n  3")
    expect([S(0,1), B(1,2), C(2,3), S(3,5)])

    clear()
    expect([B(0,1)])

    # Multiple consecutive blank lines
    clear()
    insert(0, 0, "1")
    insert(0, 1, "\n")
    expect([S(0,1),B(1,2)])
    insert(1, 0, "\n")
    expect([S(0,1),B(1,3)])

    # Continuation lines at the beginning
    clear()
    insert(0, 0, "# Something\n   pass")
    expect([C(0,1), S(1,2)])
    delete(0, 0, 1, 0)
    expect([S(0,1)])

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
    expect_log([CD(), CI(0,1)])
    calculate()
    expect_log([CSC(0,1), CRC(0,1)])

    insert(0, 0, "#")
    expect_log([CD(), CI(0,1)])

    # Deleting a chunk with results
    clear()
    insert(0, 0, "1\n2")
    calculate()
    expect([S(0,1),S(1,2)])
    expect_results([['1'],['2']])
    clear_log()
    delete(0, 0, 0, 1)
    expect([B(0,1),S(1,2)])
    expect_log([CD(), CI(0,1), CSC(1,2)])

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

    # Shortening the last chunk in the buffer
    clear()
    insert(0, 0, "def a():\n    x = 1\n    return 1")
    delete(1, 0, 2, 0)
    expect([S(0, 2)])

    # Inserting a statement above a continuation line at the start of the buffer
    clear()
    insert(0, 0, "#def a(x):\n    return x")
    delete(0, 0, 0, 1)
    expect([S(0,2)])

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

    # Test that changes that substitute text with identical
    # text counts as changes

    # New text
    clear()
    insert(0, 0, "if")
    clear_log()
    worksheet.begin_user_action()
    delete(0, 1, 0, 2)
    insert(0, 1, "f")
    worksheet.end_user_action()
    expect([S(0,1)])
    expect_log([CC(0,1,[0])])

    # Text from elsewhere in the buffer
    clear()
    insert(0, 0, "if\nif")
    clear_log()
    delete(0, 1, 1, 1)
    expect([S(0,1)])
    expect_log([CD(), CC(0,1,[0])])

    # Test that commenting out a line marks subsequent lines for recalculation
    clear()

    insert(0, 0, "a = 1\na = 2\na")
    calculate()
    insert(1, 0, "#")
    assert worksheet.get_chunk(2).needs_execute

    # Test that we don't send out ::chunk-deleted signal for chunks for
    # which we never sent a ::chunk-inserted signal

    clear()

    insert(0, 0, "[1]")
    clear_log()
    worksheet.begin_user_action()
    insert(0, 2, "\n")
    worksheet.rescan()
    insert(1, 0, "    ")
    worksheet.end_user_action()
    expect_log([CC(0,2,[0,1])])

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
    calculate()
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
    calculate()

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
        calculate()

        expect_text(SAVE_TEST)
        expect([S(0,1), S(1,2), C(2,3), B(3,4), S(4,5)])
        expect_results([[], ['1'], None, None, []])
    finally:
        os.remove(fname)

    clear()
    expect([B(0,1)])
