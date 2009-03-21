# Copyright 2007, 2008 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import traceback

from change_range import ChangeRange
from statement import Statement, WarningResult
from tokenized_statement import TokenizedStatement;

class Chunk(object):

    """
    A chunk is a series of consecutive lines in a Worksheet treated as a unit.
    The Chunk class is a base class for different types of chunks. It contains
    basic functionality for tracking a [start,end) range, and tracking what
    lines withinthe chunk have changed.
    """

    def __init__(self, start=-1, end=-1):
        self.start = start
        self.end = end
        self.changes = ChangeRange()
        self.newly_inserted = True

    def set_range(self, start, end):
        if start < self.start:
            self.changes.insert(0, self.start - start)
            self.start = start
        if end > self.end:
            self.changes.insert(self.end -self.start, self.start - start)
            self.end = end
        if start > self.start:
            self.changes.delete_range(0, start - self.start)
            self.start = start
        if end < self.end:
            self.changes.delete_range(end - self.start, self.end - self.start)
            self.end = end

    def change_line(self, line):
        self.changes.change(line - self.start, line + 1 - self.start)

    def change_lines(self, start, end):
        self.changes.change(start - self.start, end - self.start)

    def insert_lines(self, pos, count):
        self.changes.insert(pos - self.start, count)
        self.end += count

    def delete_lines(self, start, end):
        self.changes.delete_range(start - self.start, end - self.start)
        # Note: deleting everything gives [end,end], which is legitimate
        # but maybe a little surprising. Doesn't matter for us.
        if start == self.start:
            self.start = end
        else:
            self.end -= (end - start)

class StatementChunk(Chunk):

    """
    StatementChunk represents a series of lines making up a single unit of Python
    code. (Roughly, but perhaps not exactly corresponding to a statement in the
    Python grammar. A StatementChunk might contain text that isn't compilable at all.)

    In addition to the basic range-tracking capabilities of the base class, the
    StatementChunk class holds a tokenized representation of the code, information
    about the status of the chunk (needs_compile, needs_execute), and after compilation
    and/or execution, the resulting results or errors.
    """

    def __init__(self, start=-1, end=-1):
        Chunk.__init__(self, start, end)
        self.tokenized = TokenizedStatement()

        self.status_changed = False
        self.results_changed = False

        self.executing = False
        self.needs_compile = False
        self.needs_execute = False
        self.statement = None

        self.results = None

        self.error_message = None
        self.error_line = None
        self.error_offset = None

    def __repr__(self):
        return "StatementChunk(%d,%d,%r,%r,%r)" % (self.start, self.end, self.needs_compile, self.needs_execute, self.tokenized.get_text())

    def set_lines(self, lines):
        range = self.tokenized.set_lines(lines)
        if range == None:
            return False

        if range[0] != range[1]: # non-empty range ... empty=truncation
            self.change_lines(self.start + range[0], self.start + range[1])

        if not self.needs_compile:
            self.needs_compile = True
            self.status_changed = True
        self.needs_execute = False

        self.statement = None

        return True

    def mark_for_execute(self):
        if self.statement != None and not self.needs_execute:
            self.statement.mark_for_execute()
            self.needs_execute = True
            self.status_changed = True
            return True
        else:
            return False

    def get_statement(self, worksheet):
        if not self.statement:
            self.statement = Statement(self.tokenized.get_text(), worksheet)
            self.statement.chunk = self

        return self.statement

    def update_statement(self):
        self.status_changed = True

        if self.statement.state == Statement.COMPILE_SUCCESS:
            self.needs_compile = False
            self.needs_execute = True
        elif self.statement.state == Statement.EXECUTING:
            self.executing = True
        elif self.statement.state == Statement.EXECUTE_SUCCESS:
            self.executing = False
            self.needs_compile = False
            self.needs_execute = False
            if self.results != self.statement.results:
                self.results_changed = True
            self.results = self.statement.results
            self.error_message = None
            self.error_line = None
            self.error_offset = None
        elif self.statement.state == Statement.COMPILE_ERROR:
            self.needs_compile = True
            self.needs_execute = True
            self.error_message = self.statement.error_message
            self.error_line = self.statement.error_line
            self.error_offset = self.statement.error_offset
            self.results = None
            self.results_changed = True
        elif self.statement.state == Statement.EXECUTE_ERROR:
            self.executing = False
            self.needs_compile = False
            self.needs_execute = True
            self.error_message = self.statement.error_message
            self.error_line = self.statement.error_line
            self.error_offset = self.statement.error_offset
            self.results = None
            self.results_changed = True
        elif self.statement.state == Statement.INTERRUPTED:
            self.executing = False
            self.needs_compile = False
            self.needs_execute = True
            self.error_message = "Interrupted"
            self.error_line = None
            self.error_offset = None
            self.results = None
            self.results_changed = True
        else:
            # NEW/EXECUTING should not be hit here
            raise AssertionError("Unexpected state in Chunk.update_statement()")

class BlankChunk(Chunk):

    """
    BlankChunk represents a series of consecutive blank lines.
    """

    def __init__(self, start=-1, end=-1):
        Chunk.__init__(self, start, end)

    def __repr__(self):
        return "BlankChunk(%d,%d)" % (self.start, self.end)

class CommentChunk(Chunk):

    """
    CommentChunk represents a series of consecutive comment lines.
    """

    def __init__(self, start=-1, end=-1):
        Chunk.__init__(self, start, end)

    def __repr__(self):
        return "CommentChunk(%d,%d)" % (self.start, self.end)
