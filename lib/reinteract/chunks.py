import traceback

from change_range import ChangeRange
from statement import Statement, ExecutionError, WarningResult
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
        if end == self.end:
            self.end = start
        elif start == self.start:
            self.start = end

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
            self.needs_execute = True
            self.status_changed = True
            return True
        else:
            return False

    def compile(self, worksheet):
        if self.statement != None:
            return

        self.needs_compile = False
        self.status_changed = True

        if self.results != None:
            self.results = None
            self.results_changed = True

        self.error_message = None
        self.error_line = None
        self.error_offset = None

        try:
            self.statement = Statement(self.tokenized.get_text(), worksheet)
            self.needs_execute = True
        except SyntaxError, e:
            self.error_message = e.msg
            self.error_line = e.lineno
            self.error_offset = e.offset
            self.results_changed = True
        except UnsupportedSyntaxError, e:
            self.error_message = e.value
            self.results_changed = True

    def execute(self, parent):
        assert(self.statement != None)

        self.needs_compile = False
        self.needs_execute = False
        self.status_changed = True

        self.error_message = None
        self.error_line = None
        self.error_offset = None

        try:
            self.statement.set_parent(parent)
            self.statement.execute()
            if self.results != self.statement.results:
                self.results_changed = True
            self.results = self.statement.results
        except ExecutionError, e:
            self.error_message = "\n".join(traceback.format_tb(e.traceback)[2:]) + "\n".join(traceback.format_exception_only(e.type, e.value))
            if self.error_message.endswith("\n"):
                self.error_message = self.error_message[0:-1]

            self.error_line = e.traceback.tb_frame.f_lineno
            self.error_offset = None
            self.results_changed = True
            self.results = None

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
