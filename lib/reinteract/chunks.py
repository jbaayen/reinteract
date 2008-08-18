import traceback

from statement import Statement, ExecutionError, WarningResult
from tokenized_statement import TokenizedStatement;

class StatementChunk:
    def __init__(self, start=-1, end=-1):
        self.start = start
        self.end = end
        # This is a count maintained by the buffer as to how many lines reference
        # the statement; it's used to determine when we are deleting a chunk
        # from the buffer
        self.line_count = 0
        self.tokenized = TokenizedStatement()

        self.changed_lines = None
        self.status_changed = False
        self.results_changed = False
        self.newly_inserted = True

        self.needs_compile = False
        self.needs_execute = False
        self.statement = None

        self.results = None

        self.error_message = None
        self.error_line = None
        self.error_offset = None

    def __repr__(self):
        return "StatementChunk(%d,%d,%r,%r,'%r')" % (self.start, self.end, self.needs_compile, self.needs_execute, self.tokenized.get_text())

    def set_lines(self, lines):
        changed_lines = self.tokenized.set_lines(lines)
        if changed_lines == None:
            return False

        if self.changed_lines == None:
            self.changed_lines = set(changed_lines)
        else:
            self.changed_lines.update(changed_lines)

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

class BlankChunk:
    def __init__(self, start=-1, end=-1):
        self.start = start
        self.end = end
        self.line_count = 0

    def __repr__(self):
        return "BlankChunk(%d,%d)" % (self.start, self.end)

class CommentChunk:
    def __init__(self, start=-1, end=-1):
        self.start = start
        self.end = end
        self.line_count = 0

    def __repr__(self):
        return "CommentChunk(%d,%d)" % (self.start, self.end)
