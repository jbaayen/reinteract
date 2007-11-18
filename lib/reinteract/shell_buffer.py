#!/usr/bin/python
import gobject
import gtk
import traceback
import os
import re
from notebook import Notebook
from statement import Statement, ExecutionError, WarningResult
from worksheet import Worksheet
from custom_result import CustomResult
import tokenize
from tokenized_statement import TokenizedStatement
from undo_stack import UndoStack, InsertOp, DeleteOp

# See comment in iter_copy_from.py
try:
    gtk.TextIter.copy_from
    def _copy_iter(dest, src):
        dest.copy_from(src)
except AttributeError:
    from iter_copy_from import iter_copy_from as _copy_iter
        
_verbose = False

class StatementChunk:
    def __init__(self, start=-1, end=-1, nr_start=-1):
        self.start = start
        self.end = end
        # this is the start index ignoring result chunks; we need this for
        # storing items in the undo stack
        self.nr_start = nr_start
        self.tokenized = TokenizedStatement()
        
        self.needs_compile = False
        self.needs_execute = False
        self.statement = None
        
        self.results = None

        self.error_message = None
        self.error_line = None
        self.error_offset = None
        
    def __repr__(self):
        return "StatementChunk(%d,%d,%s,%s,'%s')" % (self.start, self.end, self.needs_compile, self.needs_execute, self.tokenized.get_text())

    def set_lines(self, lines):
        changed_lines = self.tokenized.set_lines(lines)
        if changed_lines == []:
            return changed_lines
        
        self.needs_compile = True
        self.needs_execute = False
        
        self.statement = None

        return changed_lines

    def mark_for_execute(self):
        if self.statement == None or self.needs_execute:
            return False
        else:
            self.needs_execute = True
            return True

    def compile(self, worksheet):
        if self.statement != None:
            return
        
        self.needs_compile = False
        
        self.results = None

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

    def execute(self, parent):
        assert(self.statement != None)
        
        self.needs_compile = False
        self.needs_execute = False
        
        self.error_message = None
        self.error_line = None
        self.error_offset = None
        
        try:
            self.statement.set_parent(parent)
            self.statement.execute()
            self.results = self.statement.results
        except ExecutionError, e:
            self.error_message = "\n".join(traceback.format_tb(e.traceback)[2:]) + "\n".join(traceback.format_exception_only(e.type, e.value))
            if self.error_message.endswith("\n"):
                self.error_message = self.error_message[0:-1]
                
            self.error_line = e.traceback.tb_frame.f_lineno
            self.error_offset = None
            
class BlankChunk:
    def __init__(self, start=-1, end=-1, nr_start=-1):
        self.start = start
        self.end = end
        self.nr_start = nr_start
        
    def __repr__(self):
        return "BlankChunk(%d,%d)" % (self.start, self.end)
    
class CommentChunk:
    def __init__(self, start=-1, end=-1, nr_start=-1):
        self.start = start
        self.end = end
        self.nr_start = nr_start
        
    def __repr__(self):
        return "CommentChunk(%d,%d)" % (self.start, self.end)
    
class ResultChunk:
    def __init__(self, start=-1, end=-1, nr_start=-1):
        self.start = start
        self.end = end
        self.nr_start = nr_start
        
    def __repr__(self):
        return "ResultChunk(%d,%d)" % (self.start, self.end)
    
BLANK = re.compile(r'^\s*$')
COMMENT = re.compile(r'^\s*#')
CONTINUATION = re.compile(r'^\s+')

class ResultChunkFixupState:
    pass

class ShellBuffer(gtk.TextBuffer, Worksheet):
    __gsignals__ = {
        'begin-user-action': 'override',
        'end-user-action': 'override',
        'insert-text': 'override',
        'delete-range': 'override',
        'chunk-status-changed':  (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        'add-custom-result':  (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT)),
        'pair-location-changed': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT)),

        # It would be more GObject to make these properties, but we'll wait on that until
        # decent property support lands:
        #
        #  http://blogs.gnome.org/johan/2007/04/30/simplified-gobject-properties/
        #
        'filename-changed':  (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        # Clumsy naming is because GtkTextBuffer already has a modified flag, but that would
        # include changes to the results
        'code-modified-changed':  (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
    }

    def __init__(self, notebook):
        gtk.TextBuffer.__init__(self)
        Worksheet.__init__(self, notebook)

        self.__red_tag = self.create_tag(foreground="red")
        self.__result_tag = self.create_tag(family="monospace", style="italic", wrap_mode=gtk.WRAP_WORD, editable=False)
        # Order here is significant ... we want the recompute tag to have higher priority, so
        # define it second
        self.__warning_tag = self.create_tag(foreground="#aa8800")
        self.__error_tag = self.create_tag(foreground="#aa0000")
        self.__recompute_tag = self.create_tag(foreground="#888888")
        self.__comment_tag = self.create_tag(foreground="#3f7f5f")

        punctuation_tag = None

        self.__fontify_tags = {
            tokenize.TOKEN_KEYWORD      : self.create_tag(foreground="#7f0055", weight=600),
            tokenize.TOKEN_NAME         : None,
            tokenize.TOKEN_COMMENT      : self.__comment_tag,
            tokenize.TOKEN_BUILTIN_CONSTANT : self.create_tag(foreground="#55007f"),
            tokenize.TOKEN_STRING       : self.create_tag(foreground="#00aa00"),
            tokenize.TOKEN_PUNCTUATION  : punctuation_tag,
            tokenize.TOKEN_CONTINUATION : punctuation_tag,
            tokenize.TOKEN_LPAREN       : punctuation_tag,
            tokenize.TOKEN_RPAREN       : punctuation_tag,
            tokenize.TOKEN_LSQB         : punctuation_tag,
            tokenize.TOKEN_RSQB         : punctuation_tag,
            tokenize.TOKEN_LBRACE       : punctuation_tag,
            tokenize.TOKEN_RBRACE       : punctuation_tag,
            tokenize.TOKEN_BACKQUOTE    : punctuation_tag,
            tokenize.TOKEN_COLON        : punctuation_tag,
            tokenize.TOKEN_NUMBER       : None,
            tokenize.TOKEN_JUNK         : self.create_tag(underline="error"),
        }
        
        self.__lines = [""]
        self.__chunks = [BlankChunk(0,0, 0)]
        self.__modifying_results = False
        self.__applying_undo = False
        self.__user_action_count = 0

        self.__have_pair = False
        self.__pair_mark = self.create_mark(None, self.get_start_iter(), True)

        self.__undo_stack = UndoStack(self)
        
        self.filename = None
        self.code_modified = False

    def __compute_nr_start(self, chunk):
        if chunk.start == 0:
            chunk.nr_start = 0
        else:
            chunk_before = self.__chunks[chunk.start - 1]
            if isinstance(chunk_before, ResultChunk):
                chunk.nr_start = chunk_before.nr_start
            else:
                chunk.nr_start = chunk_before.nr_start + (1 + chunk_before.end - chunk_before.start)
    
    def __assign_lines(self, chunk_start, lines, statement_end):
        changed_chunks = []
        
        if statement_end >= chunk_start:
            def notnull(l): return l != None
            chunk_lines = filter(notnull, lines[0:statement_end + 1 - chunk_start])

            old_statement = None
            for i in xrange(chunk_start, statement_end + 1):
                if isinstance(self.__chunks[i], StatementChunk):
                    old_statement = self.__chunks[i]
                    break
                
            if old_statement != None:
                # An old statement can only be turned into *one* new statement; this
                # prevents us getting fooled if we split a statement
                for i in xrange(old_statement.start, old_statement.end + 1):
                    self.__chunks[i] = None

                chunk = old_statement
                old_needs_compile = chunk.needs_compile
                changed_lines = chunk.set_lines(chunk_lines)
                changed = chunk.needs_compile != old_needs_compile

                # If we moved the statement with respect to the buffer, then the we
                # need to refontify, even if the old statement didn't change
                if old_statement.start != chunk_start:
                    changed_lines = range(0, 1 + statement_end - chunk_start)
            else:
                chunk = StatementChunk()
                changed_lines = chunk.set_lines(chunk_lines)
                changed = True

            if changed:
                changed_chunks.append(chunk)
                
            chunk.start = chunk_start
            chunk.end = statement_end
            self.__compute_nr_start(chunk)
            self.__fontify_statement_lines(chunk, changed_lines)
            
            for i in xrange(chunk_start, statement_end + 1):
                self.__chunks[i] = chunk
                self.__lines[i] = lines[i - chunk_start]

        for i in xrange(statement_end + 1, chunk_start + len(lines)):
            line = lines[i - chunk_start]

            if i > 0:
                chunk = self.__chunks[i - 1]
            else:
                chunk = None

            if line == None:
                # a ResultChunk Must be in the before-start portion, nothing needs doing
                pass
            elif BLANK.match(line):
                if not isinstance(chunk, BlankChunk):
                    chunk = BlankChunk()
                    chunk.start = i
                    self.__compute_nr_start(chunk)
                chunk.end = i
                self.__chunks[i] = chunk
                self.__lines[i] = lines[i - chunk_start]
            elif COMMENT.match(line):
                if not isinstance(chunk, CommentChunk):
                    chunk = CommentChunk()
                    chunk.start = i
                    self.__compute_nr_start(chunk)
                chunk.end = i
                self.__chunks[i] = chunk
                self.__lines[i] = lines[i - chunk_start]
                # This is O(n^2) inefficient
                self.__apply_tag_to_chunk(self.__comment_tag, chunk)
        
        return changed_chunks

    def __mark_chunk_changed(self, chunk):
        result = self.__find_result(chunk)
        if result:
            self.__apply_tag_to_chunk(self.__recompute_tag, result)
            
        self.emit("chunk-status-changed", chunk)
        if result:
            self.emit("chunk-status-changed", result)
                
    def __mark_rest_for_execute(self, changed_chunks, start_line):

        changed_chunks = set(changed_chunks)
        for chunk in self.iterate_chunks(start_line):
            if chunk in changed_chunks:
                self.__mark_chunk_changed(chunk)
            elif isinstance(chunk, StatementChunk):
                if chunk.mark_for_execute():
                    self.__mark_chunk_changed(chunk)
                            
    def __rescan(self, start_line, end_line, entire_statements_deleted=False):
        rescan_start = start_line
        while rescan_start > 0:
            if rescan_start < start_line:
                new_text = old_text = self.__lines[rescan_start]
            else:
                old_text = self.__lines[rescan_start]
                i = self.get_iter_at_line(rescan_start)
                i_end = i.copy()
                if not i_end.ends_line():
                    i_end.forward_to_line_end()
                new_text = self.get_slice(i, i_end)

            if old_text == None or BLANK.match(old_text) or COMMENT.match(old_text) or CONTINUATION.match(old_text) or \
               new_text == None or BLANK.match(new_text) or COMMENT.match(new_text) or CONTINUATION.match(new_text):
                rescan_start -= 1
            else:
                break

        # If previous contents of the modified range ended within a statement, then we need to rescan all of it;
        # since we may have already deleted all of the statement lines within the modified range, we detect
        # this case by seeing if the line *after* our range is a continuation line.
        rescan_end = end_line
        while rescan_end + 1 < len(self.__chunks):
            if isinstance(self.__chunks[rescan_end + 1], StatementChunk) and self.__chunks[rescan_end + 1].start != rescan_end + 1:
                rescan_end += 1
            else:
                break

        chunk_start = rescan_start
        statement_end = rescan_start - 1
        chunk_lines = []

        line = rescan_start
        i = self.get_iter_at_line(rescan_start)

        changed_chunks = []

        for line in xrange(rescan_start, rescan_end + 1):
            if line < start_line:
                line_text = self.__lines[line]
            else:
                i_end = i.copy()
                if not i_end.ends_line():
                    i_end.forward_to_line_end()
                line_text = self.get_slice(i, i_end)

            if line_text == None:
                chunk_lines.append(line_text)
            elif BLANK.match(line_text):
                chunk_lines.append(line_text)
            elif COMMENT.match(line_text):
                chunk_lines.append(line_text)
            elif CONTINUATION.match(line_text):
                chunk_lines.append(line_text)
                statement_end = line
            else:
                changed_chunks.extend(self.__assign_lines(chunk_start, chunk_lines, statement_end))
                chunk_start = line
                statement_end = line
                chunk_lines = [line_text]
            
            i.forward_line()

        changed_chunks.extend(self.__assign_lines(chunk_start, chunk_lines, statement_end))
        if len(changed_chunks) > 0:
            # The the chunks in changed_chunks are already marked as needing recompilation; we
            # need to emit signals and also mark those chunks and all subsequent chunks as
            # needing reexecution
            first_changed_line = changed_chunks[0].start
            for chunk in changed_chunks:
                if chunk.start < first_changed_line:
                    first_changed_line = chunk.start

            self.__mark_rest_for_execute(changed_chunks, first_changed_line)
        elif entire_statements_deleted:
            # If the user deleted entire statements we need to mark subsequent chunks
            # as needing compilation even if all the remaining statements remained unchanged
            self.__mark_rest_for_execute(changed_chunks, end_line + 1)
            
    def iterate_chunks(self, start_line=0, end_line=None):
        if end_line == None or end_line >= len(self.__chunks):
            end_line = len(self.__chunks) - 1
        if start_line >= len(self.__chunks) or end_line < start_line:
            return

        chunk = self.__chunks[start_line]
        while chunk == None and start_line < end_line:
            start_line += 1
            chunk = self.__chunks[start_line]

        if chunk == None:
            return
        
        last_chunk = self.__chunks[end_line]
        while last_chunk == None:
            end_line -= 1
            last_chunk = self.__chunks[end_line]

        while True:
            yield chunk
            if chunk == last_chunk:
                break
            try:
                line = chunk.end + 1
                chunk = self.__chunks[line]
                while chunk == None:
                    line += 1
                    chunk = self.__chunks[line]
            except IndexError:
                # This happens if the last chunk was removed; just
                # proceeding to the end of the buffer isn't always
                # going to be right, but it is right in the case
                # where we are iterating the whole buffer, which
                # is what happens for calculate()
                return

    def iterate_text(self, start=None, end=None):
        result = ""

        if start == None:
            start = self.get_start_iter()
        if end == None:
            end = self.get_end_iter()
            
        start_chunk = self.__chunks[start.get_line()]
        end_chunk = self.__chunks[end.get_line()]

        # special case .. if start/end are in the same chunk, get the text
        # between them, even if the chunk is a ResultChunk.
        if start_chunk == end_chunk:
            yield self.get_slice(start, end)
            return
        
        chunk = start_chunk
        iter = self.get_iter_at_line(chunk.start)

        while True:
            next_line = chunk.end + 1
            if next_line < len(self.__chunks):
                next_chunk = self.__chunks[chunk.end + 1]
                
                next = iter.copy()
                while next.get_line() <= chunk.end:
                    next.forward_line()
            else:
                next_chunk = None
                next = iter.copy()
                next.forward_to_end()

            # Special case .... if the last chunk is a ResultChunk, then we don't
            # want to include the new line from the previous line
            if isinstance(next_chunk, ResultChunk) and next_chunk.end + 1 == len(self.__chunks):
                next.backward_line()
                if not next.ends_line():
                    next.forward_to_line_end()
                next_chunk = None
                
            if not isinstance(chunk, ResultChunk):
                chunk_start, chunk_end = iter, next
                if chunk == start_chunk:
                    chunk_start = start
                else:
                    chunk_start = iter
                    
                if chunk == end_chunk:
                    chunk_end = end
                else:
                    chunk_end = next
                
                yield self.get_slice(chunk_start, chunk_end)

            iter = next
            line = next_line
            if chunk == end_chunk or next_chunk == None:
                break
            else:
                chunk = next_chunk

    def get_public_text(self, start=None, end=None):
        return "".join(self.iterate_text(start, end))
            
    def do_begin_user_action(self):
        self.__user_action_count += 1
        self.__undo_stack.begin_user_action()
        
    def do_end_user_action(self):
        self.__user_action_count -= 1
        self.__undo_stack.end_user_action()

    def __compute_nr_pos_from_chunk_offset(self, chunk, line, offset):
        if isinstance(chunk, ResultChunk):
            prev_chunk = self.__chunks[chunk.start - 1]
            iter = self.get_iter_at_line(prev_chunk.end)
            if not iter.ends_line():
                iter.forward_to_line_end()
            return (prev_chunk.end - prev_chunk.start + prev_chunk.nr_start, iter.get_line_offset(), 1)
        else:
            return (line - chunk.start + chunk.nr_start, offset)
        
    def __compute_nr_pos_from_iter(self, iter):
        line = iter.get_line()
        chunk = self.__chunks[line]
        return self.__compute_nr_pos_from_chunk_offset(chunk, line, iter.get_line_offset())

    def __compute_nr_pos_from_line_offset(self, line, offset):
        return self.__compute_nr_pos_from_chunk_offset(self.__chunks[line], line, offset)

    def _get_iter_at_nr_pos(self, nr_pos):
        if len(nr_pos) == 2:
            nr_line, offset = nr_pos
            in_result = False
        else:
            nr_line, offset, in_result = nr_pos
            
        for chunk in self.iterate_chunks():
            if not isinstance(chunk, ResultChunk) and chunk.nr_start + (chunk.end - chunk.start) >= nr_line:
                line = chunk.start + nr_line - chunk.nr_start
                iter = self.get_iter_at_line(line)
                iter.set_line_offset(offset)

                if in_result and chunk.end + 1 < len(self.__chunks):
                    next_chunk = self.__chunks[chunk.end + 1]
                    if isinstance(next_chunk, ResultChunk):
                        iter = self.get_iter_at_line(next_chunk.end)
                        if not iter.ends_line():
                            iter.forward_to_line_end()

                return iter

        raise AssertionError("nr_pos pointed outside buffer")


    def __insert_blank_line_after(self, chunk_before, location, separator):
        start_pos = self.__compute_nr_pos_from_iter(location)
    
        self.__modifying_results = True
        gtk.TextBuffer.do_insert_text(self, location, separator, len(separator))
        self.__modifying_results = False

        new_chunk = BlankChunk(chunk_before.end + 1, chunk_before.end + 1, chunk_before.nr_start)
        self.__chunks[chunk_before.end + 1:chunk_before.end + 1] = [new_chunk]
        self.__lines[chunk_before.end + 1:chunk_before.end + 1] = [""]

        for chunk in self.iterate_chunks(new_chunk.end + 1):
            chunk.start += 1     
            chunk.end += 1
            chunk.nr_start += 1

        end_pos = self.__compute_nr_pos_from_iter(location)
        self.__undo_stack.append_op(InsertOp(start_pos, end_pos, separator))
    
    def do_insert_text(self, location, text, text_len):
        start_line = location.get_line()
        start_offset = location.get_line_offset()
        is_pure_insert = False
        if self.__user_action_count > 0:
            current_chunk = self.__chunks[start_line]
            if isinstance(current_chunk, ResultChunk):
                # The only thing that's valid to do with a ResultChunk is insert
                # a newline at the end to get another line after it
                if not (start_line == current_chunk.end and location.ends_line()):
                    return
                # FIXME: PS
                if not (text.startswith("\r") or text.startswith("\n")):
                    return

                start_line += 1
                is_pure_insert = True

        if _verbose:
            if not self.__modifying_results:
                print "Inserting '%s' at %s" % (text, (location.get_line(), location.get_line_offset()))

        if not self.__modifying_results:
            start_pos = self.__compute_nr_pos_from_iter(location)
        
        gtk.TextBuffer.do_insert_text(self, location, text, text_len)
        end_line = location.get_line()
        end_offset = location.get_line_offset()

        if self.__modifying_results:
            return

        if self.__user_action_count > 0:
            self.__set_modified(True)

        result_fixup_state = self.__get_result_fixup_state(start_line, start_line)

        if is_pure_insert:
            self.__chunks[start_line:start_line] = [None for i in xrange(start_line, end_line + 1)]
            self.__lines[start_line:start_line] = [None for i in xrange(start_line, end_line + 1)]
            
            for chunk in self.iterate_chunks(end_line + 1):
                if chunk.start >= start_line:
                    chunk.start += (1 + end_line - start_line)
                    chunk.nr_start += (1 + end_line - start_line)
                if chunk.end >= start_line:
                    chunk.end += (1 + end_line - start_line)
        else:
            # If we are inserting at the beginning of a line, then the insert moves the
            # old chunk down, or leaves it in place, so insert new lines at the start position.
            # If we insert elsewhere it either splits the chunk (and we consider
            # that leaving the old chunk at the start) or inserts stuff after the chunk,
            # so insert new lines after the start position.
            if start_offset == 0:
                self.__chunks[start_line:start_line] = [None for i in xrange(start_line, end_line)]
                self.__lines[start_line:start_line] = [None for i in xrange(start_line, end_line)]
                
                for chunk in self.iterate_chunks(start_line):
                    if chunk.start >= start_line:
                        chunk.start += (end_line - start_line)
                        chunk.nr_start += (end_line - start_line)
                    if chunk.end >= start_line:
                        chunk.end += (end_line - start_line)
            else:
                self.__chunks[start_line + 1:start_line + 1] = [None for i in xrange(start_line, end_line)]
                self.__lines[start_line + 1:start_line + 1] = [None for i in xrange(start_line, end_line)]

                for chunk in self.iterate_chunks(start_line):
                    if chunk.start > start_line:
                        chunk.start += (end_line - start_line)
                        chunk.nr_start += (end_line - start_line)
                    if chunk.end > start_line:
                        chunk.end += (end_line - start_line)

        self.__rescan(start_line, end_line)

        end_pos = self.__compute_nr_pos_from_line_offset(end_line, end_offset)
        self.__undo_stack.append_op(InsertOp(start_pos, end_pos, text[0:text_len]))

        self.__fixup_results(result_fixup_state, [location])
        self.__calculate_pair_location()

        if _verbose:
            print "After insert, chunks are", self.__chunks

    def __delete_chunk(self, chunk):
        self.__modifying_results = True

        i_start = self.get_iter_at_line(chunk.start)
        i_end = self.get_iter_at_line(chunk.end)
        i_end.forward_line()
        if i_end.get_line() == chunk.end:
            # Last line of buffer, need to delete the chunk and not
            # leave a trailing newline
            if not i_end.ends_line():
                i_end.forward_to_line_end()
            i_start.backward_line()
            if not i_start.ends_line():
                i_start.forward_to_line_end()
        self.delete(i_start, i_end)
        
        self.__chunks[chunk.start:chunk.end + 1] = []
        self.__lines[chunk.start:chunk.end + 1] = []

        n_deleted = chunk.end + 1 - chunk.start
        if isinstance(chunk, ResultChunk):
            n_nr_deleted = 0
        else:
            n_deleted = n_nr_deleted

        # Overlapping chunks can occur temporarily when inserting
        # or deleting text merges two adjacent statements with a ResultChunk in between, so iterate
        # all chunks, not just the ones after the deleted chunk
        for c in self.iterate_chunks():
            if c.end >= chunk.end:
                c.end -= n_deleted
            elif c.end >= chunk.start:
                c.end = chunk.start - 1

            if c.start >= chunk.end:
                c.start -= n_deleted
                c.nr_start -= n_nr_deleted
        
        self.__modifying_results = False

    def __find_result(self, statement):
        for chunk in self.iterate_chunks(statement.end + 1):
            if isinstance(chunk, ResultChunk):
                return chunk
            elif isinstance(chunk, StatementChunk):
                return None
        
    def __find_statement_for_result(self, result_chunk):
        line = result_chunk.start - 1
        while line >= 0:
            if isinstance(self.__chunks[line], StatementChunk):
                return self.__chunks[line]
        raise AssertionError("Result with no corresponding statement")
        
    def __get_result_fixup_state(self, first_modified_line, last_modified_line):
        state = ResultChunkFixupState()

        state.statement_before = None
        state.result_before = None
        for i in xrange(first_modified_line - 1, -1, -1):
            if isinstance(self.__chunks[i], ResultChunk):
                state.result_before = self.__chunks[i]
            elif isinstance(self.__chunks[i], StatementChunk):
                if state.result_before != None:
                    state.statement_before = self.__chunks[i]
                break

        state.statement_after = None
        state.result_after = None

        for i in xrange(last_modified_line + 1, len(self.__chunks)):
            if isinstance(self.__chunks[i], ResultChunk):
                state.result_after = self.__chunks[i]
                for j in xrange(i - 1, -1, -1):
                    if isinstance(self.__chunks[j], StatementChunk):
                        state.statement_after = self.__chunks[j]
                        assert state.statement_after.results != None or state.statement_after.error_message != None
                        break
            elif isinstance(self.__chunks[i], StatementChunk) and self.__chunks[i].start == i:
                break

        return state

    def __fixup_results(self, state, revalidate_iters):
        move_before = False
        delete_after = False
        move_after = False
        
        if state.result_before != None:
            # If lines were added into the StatementChunk that produced the ResultChunk above the edited segment,
            # then the ResultChunk needs to be moved after the newly inserted lines
            if state.statement_before.end > state.result_before.start:
                move_before = True

        if state.result_after != None:
            # If the StatementChunk that produced the ResultChunk after the edited segment was deleted, then the
            # ResultChunk needs to be deleted as well
            if self.__chunks[state.statement_after.start] != state.statement_after:
                delete_after = True
            else:
                # If another StatementChunk was inserted between the StatementChunk and the ResultChunk, then we
                # need to move the ResultChunk above that statement
                for i in xrange(state.statement_after.end + 1, state.result_after.start):
                    if self.__chunks[i] != state.statement_after and isinstance(self.__chunks[i], StatementChunk):
                        move_after = True

        if not (move_before or delete_after or move_after):
            return

        if _verbose:
            print "Result fixups: move_before=%s, delete_after=%s, move_after=%s" % (move_before, delete_after, move_after)

        revalidate = map(lambda iter: (iter, self.create_mark(None, iter, True)), revalidate_iters)

        if move_before:
            self.__delete_chunk(state.result_before)
            self.insert_result(state.statement_before)

        if delete_after or move_after:
            self.__delete_chunk(state.result_after)
            if move_after:
                self.insert_result(state.statement_after)

        for iter, mark in revalidate:
            _copy_iter(iter, self.get_iter_at_mark(mark))
            self.delete_mark(mark)
        
    def do_delete_range(self, start, end):
        #
        # Note that there is a bug in GTK+ versions prior to 2.12.2, where it doesn't work
        # if a ::delete-range handler deletes stuff outside it's requested range. (No crash,
        # gtk_text_buffer_delete_interactive() just leaves some editable text undeleleted.)
        # See: http://bugzilla.gnome.org/show_bug.cgi?id=491207
        #
        # The only workaround I can think of right now would be to stop using not-editable
        # tags on results, and implement the editability ourselves in ::insert-text
        # and ::delete-range, but a) that's a lot of work to rewrite that way b) it will make
        # the text view give worse feedback. So, I'm just leaving the problem for now,
        # (and have committed the fix to GTK+)
        #
        if _verbose:
            if not self.__modifying_results:
                print "Request to delete range %s" % (((start.get_line(), start.get_line_offset()), (end.get_line(), end.get_line_offset())),)
        start_line = start.get_line()
        end_line = end.get_line()

        restore_result_statement = None

        # Prevent the user from doing deletes that would merge a ResultChunk chunk with another chunk
        if self.__user_action_count > 0 and not self.__modifying_results:
            if start.ends_line() and isinstance(self.__chunks[start_line], ResultChunk):
                # Merging another chunk onto the end of a ResultChunk; e.g., hitting delete at the
                # start of a line with a ResultChunk before it. We don't want to actually ignore this,
                # since otherwise if you split a line, you can't join it back up, instead we actually
                # have to do what the user wanted to do ... join the two lines.
                #
                # We delete the result chunk, and if everything still looks sane at the very end,
                # we insert it back; this is not unified with the __fixup_results() codepaths, since
                # A) There's no insert analogue B) That's complicated enough as it is. But if we
                # have problems, we might want to reconsider whether there is some unified way to
                # do both. Maybe we should just delete all possibly affected ResultChunks and add
                # them all back at the end?
                #
                result_chunk = self.__chunks[start_line]
                restore_result_statement = self.__find_statement_for_result(result_chunk)
                end_offset = end.get_line_offset()
                self.__modifying_results = True
                self.__delete_chunk(result_chunk)
                self.__modifying_results = False
                start_line -= 1 + result_chunk.end - result_chunk.start
                end_line -= 1 + result_chunk.end - result_chunk.start
                _copy_iter(start, self.get_iter_at_line(start_line))
                if not start.ends_line():
                    start.forward_to_line_end()
                _copy_iter(end, self.get_iter_at_line_offset(end_line, end_offset))
                
            if end.starts_line() and not start.starts_line() and isinstance(self.__chunks[end_line], ResultChunk):
                # Merging a ResultChunk onto the end of another chunk; just ignore this; we do have
                # have to be careful to avoid leaving end pointing to the same place as start, since
                # we'll then go into an infinite loop
                new_end = end.copy()
                
                new_end.backward_line()
                if not new_end.ends_line():
                    new_end.forward_to_line_end()

                if start.compare(new_end) == 0:
                    return

                end.backward_line()
                if not end.ends_line():
                    end.forward_to_line_end()
                end_line -= 1
                
        if start.starts_line() and end.starts_line():
            (first_deleted_line, last_deleted_line) = (start_line, end_line - 1)
            (new_start, new_end) = (start_line, start_line - 1) # empty
            last_modified_line = end_line - 1
        elif start.starts_line():
            if start_line == end_line:
                (first_deleted_line, last_deleted_line) = (start_line, start_line - 1) # empty
                (new_start, new_end) = (start_line, start_line)
                last_modified_line = start_line
            else:
                (first_deleted_line, last_deleted_line) = (start_line, end_line - 1)
                (new_start, new_end) = (start_line, start_line)
                last_modified_line = end_line
        else:
            (first_deleted_line, last_deleted_line) = (start_line + 1, end_line)
            (new_start, new_end) = (start_line, start_line)
            last_modified_line = end_line

        if _verbose:
            if not self.__modifying_results:
                print "Deleting range %s" % (((start.get_line(), start.get_line_offset()), (end.get_line(), end.get_line_offset())),)
                print "first_deleted_line=%d, last_deleted_line=%d, new_start=%d, new_end=%d, last_modified_line=%d" % (first_deleted_line, last_deleted_line, new_start, new_end, last_modified_line)

        start_pos = self.__compute_nr_pos_from_iter(start)
        end_pos = self.__compute_nr_pos_from_iter(end)
        deleted_text = self.get_slice(start, end)
        gtk.TextBuffer.do_delete_range(self, start, end)

        if self.__modifying_results:
            return

        if self.__user_action_count > 0:
            self.__set_modified(True)

        self.__undo_stack.append_op(DeleteOp(start_pos, end_pos, deleted_text))

        result_fixup_state = self.__get_result_fixup_state(new_start, last_modified_line)

        entire_statements_deleted = False
        n_nr_deleted = 0
        for chunk in self.iterate_chunks(first_deleted_line, last_deleted_line):
            if isinstance(chunk, StatementChunk) and chunk.start >= first_deleted_line and chunk.end <= last_deleted_line:
                entire_statements_deleted = True
                
            if not isinstance(chunk, ResultChunk):
                n_nr_deleted += 1 + min(last_deleted_line, chunk.end) - max(first_deleted_line, chunk.start)

        n_deleted = 1 + last_deleted_line - first_deleted_line
        self.__chunks[first_deleted_line:last_deleted_line + 1] = []
        self.__lines[first_deleted_line:last_deleted_line + 1] = []

        for chunk in self.iterate_chunks():
            if chunk.end >= last_deleted_line:
                chunk.end -= n_deleted;
            elif chunk.end >= first_deleted_line:
                chunk.end = first_deleted_line - 1
                
            if chunk.start >= last_deleted_line:
                chunk.start -= n_deleted
                chunk.nr_start -= n_nr_deleted

        self.__rescan(new_start, new_end, entire_statements_deleted=entire_statements_deleted)

        self.__fixup_results(result_fixup_state, [start, end])

        if restore_result_statement != None and \
                self.__chunks[restore_result_statement.start] == restore_result_statement and \
                self.__find_result(restore_result_statement) == None:
            start_mark = self.create_mark(None, start, True)
            end_mark = self.create_mark(None, end, True)
            result_chunk = self.insert_result(restore_result_statement)
            _copy_iter(start, self.get_iter_at_mark(start_mark))
            self.delete_mark(start_mark)
            _copy_iter(end, self.get_iter_at_mark(end_mark))
            self.delete_mark(end_mark)

            # If the cursor ended up in or after the restored result chunk,
            # we need to move it before
            insert = self.get_iter_at_mark(self.get_insert())
            if insert.get_line() >= result_chunk.start:
                insert.set_line(result_chunk.start - 1)
                if not insert.ends_line():
                    insert.forward_to_line_end()
                self.place_cursor(insert)

        self.__calculate_pair_location()
        
        if _verbose:
            print "After delete, chunks are", self.__chunks

    def calculate(self):
        parent = None
        have_error = False
        for chunk in self.iterate_chunks():
            if isinstance(chunk, StatementChunk):
                changed = False
                if chunk.needs_compile or (chunk.needs_execute and not have_error):
                    old_result = self.__find_result(chunk)
                    if old_result:
                        self.__delete_chunk(old_result)

                if chunk.needs_compile:
                    changed = True
                    chunk.compile(self)
                    if chunk.error_message != None:
                        self.insert_result(chunk)

                if chunk.needs_execute and not have_error:
                    changed = True
                    chunk.execute(parent)
                    if chunk.error_message != None:
                        self.insert_result(chunk)
                    elif len(chunk.results) > 0:
                        self.insert_result(chunk)

                if chunk.error_message != None:
                    have_error = True

                if changed:
                    self.emit("chunk-status-changed", chunk)

                parent = chunk.statement

        if _verbose:
            print "After calculate, chunks are", self.__chunks

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

    def get_pair_location(self):
        if self.__have_pair:
            return self.get_iter_at_mark(self.__pair_mark)
        else:
            return None

    def __calculate_pair_location(self):
        location = self.get_iter_at_mark(self.get_insert())

        # GTK+-2.10 has fractionally-more-efficient buffer.get_has_selection()
        selection_bound = self.get_iter_at_mark(self.get_selection_bound())
        if location.compare(selection_bound) != 0:
            self.__set_pair_location(None)
            return

        location = self.get_iter_at_mark(self.get_insert())
        
        line = location.get_line()
        chunk = self.__chunks[line]
        if not isinstance(chunk, StatementChunk):
            self.__set_pair_location(None)
            return

        if location.starts_line():
            self.__set_pair_location(None)
            return

        previous = location.copy()
        previous.backward_char()
        pair_line, pair_start = chunk.tokenized.get_pair_location(line - chunk.start, previous.get_line_index())

        if pair_line == None:
            self.__set_pair_location(None)
            return

        pair_iter = self.get_iter_at_line_index(chunk.start + pair_line, pair_start)
        self.__set_pair_location(pair_iter)

    def do_mark_set(self, location, mark):
        try:
            gtk.TextBuffer.do_mark_set(self, location, mark)
        except NotImplementedError:
            # the default handler for ::mark-set was added in GTK+-2.10
            pass

        if mark != self.get_insert() and mark != self.get_selection_bound():
            return

        self.__calculate_pair_location()
        
    def get_chunk(self, line_index):
        return self.__chunks[line_index]

    def undo(self):
        self.__undo_stack.undo()

    def redo(self):
        self.__undo_stack.redo()
        
    def __get_chunk_bounds(self, chunk):
        start = self.get_iter_at_line(chunk.start)
        end = self.get_iter_at_line(chunk.end)
        if not end.ends_line():
            end.forward_to_line_end()
        return start, end

    def copy_as_doctests(self, clipboard):
        bounds = self.get_selection_bounds()
        if bounds == ():
            start, end = self.get_iter_at_mark(self.get_insert())
        else:
            start, end = bounds

        result = ""
        for chunk in self.iterate_chunks(start.get_line(), end.get_line()):
            chunk_text = self.get_text(*self.__get_chunk_bounds(chunk))
            
            if isinstance(chunk, ResultChunk) or isinstance(chunk, BlankChunk):
                if chunk.end == len(self.__chunks) - 1:
                    result += chunk_text
                else:
                    result += chunk_text + "\n"
            else:
                first = True
                for line in chunk_text.split("\n"):
                    if isinstance(chunk, StatementChunk) and not first:
                        result += "... " + line + "\n"
                    else:
                        result += ">>> " + line + "\n"
                    first = False

        clipboard.set_text(result)
                
    def __fontify_statement_lines(self, chunk, changed_lines):
        iter = self.get_iter_at_line(chunk.start)
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
                
    def __apply_tag_to_chunk(self, tag, chunk):
        start, end = self.__get_chunk_bounds(chunk)
        self.apply_tag(tag, start, end)

    def __remove_tag_from_chunk(self, tag, chunk):
        start, end = self.__get_chunk_bounds(chunk)
        self.remove_tag(tag, start, end)
    
    def insert_result(self, chunk):
        self.__modifying_results = True
        location = self.get_iter_at_line(chunk.end)
        if not location.ends_line():
            location.forward_to_line_end()

        if chunk.error_message:
            results = [ chunk.error_message ]
        else:
            results = chunk.results

        # We don't want to move the insert cursor in the common case of
        # inserting a result right at the insert cursor
        if location.compare(self.get_iter_at_mark(self.get_insert())) == 0:
            saved_insert = self.create_mark(None, location, True)
        else:
            saved_insert = None

        for result in results:
            if isinstance(result, basestring):
                self.insert(location, "\n" + result)
            elif isinstance(result, WarningResult):
                start_mark = self.create_mark(None, location, True)
                self.insert(location, "\n" + result.message)
                start = self.get_iter_at_mark(start_mark)
                self.delete_mark(start_mark)
                self.apply_tag(self.__warning_tag, start, location)
            elif isinstance(result, CustomResult):
                self.insert(location, "\n")
                anchor = self.create_child_anchor(location)
                self.emit("add-custom-result", result, anchor)
            
        self.__modifying_results = False
        n_inserted = location.get_line() - chunk.end

        result_chunk = ResultChunk(chunk.end + 1, chunk.end + n_inserted)
        self.__compute_nr_start(result_chunk)
        self.__chunks[chunk.end + 1:chunk.end + 1] = [result_chunk for i in xrange(0, n_inserted)]
        self.__lines[chunk.end + 1:chunk.end + 1] = [None for i in xrange(0, n_inserted)]

        self.__apply_tag_to_chunk(self.__result_tag, result_chunk)

        if chunk.error_message:
            self.__apply_tag_to_chunk(self.__error_tag, result_chunk)
        
        for chunk in self.iterate_chunks(result_chunk.end + 1):
            chunk.start += n_inserted
            chunk.end += n_inserted

        if saved_insert != None:
            self.place_cursor(self.get_iter_at_mark(saved_insert))
            self.delete_mark(saved_insert)

        return result_chunk

    def __set_filename_and_modified(self, filename, modified):
        filename_changed = filename != self.filename
        modified_changed = modified != self.code_modified

        if not (filename_changed or modified_changed):
            return
        
        self.filename = filename
        self.code_modified = modified

        if filename_changed:
            self.emit('filename-changed')

        if modified_changed:
            self.emit('code-modified-changed')

    def __set_modified(self, modified):
        if modified == self.code_modified:
            return

        self.code_modified = modified
        self.emit('code-modified-changed')

    def __do_clear(self):
        # This is actually working pretty much coincidentally, since the Delete
        # code wasn't really written with non-interactive deletes in mind, and
        # when there are ResultChunk present, a non-interactive delete will
        # use ranges including them. But the logic happens to work out.
        
        self.delete(self.get_start_iter(), self.get_end_iter())        

    def clear(self):
        self.__do_clear()
        self.__set_filename_and_modified(None, False)

        # This prevents redoing New, but we need some more work to enable that
        self.__undo_stack.clear()

    def load(self, filename):
        f = open(filename)
        text = f.read()
        f.close()
        
        self.__do_clear()
        self.__set_filename_and_modified(filename, False)
        self.insert(self.get_start_iter(), text)
        self.__undo_stack.clear()

    def save(self, filename=None):
        if filename == None:
            if self.filename == None:
                raise ValueError("No current or specified filename")

            filename = self.filename

        # TODO: The atomic-save implementation here is Unix-specific and won't work on Windows
        tmpname = filename + ".tmp"

        # We use binary mode, since we don't want to munge line endings to the system default
        # on a load-save cycle
        f = open(tmpname, "wb")

        success = False
        try:
            for chunk_text in self.iterate_text():
                f.write(chunk_text)
            
            f.close()
            os.rename(tmpname, filename)
            success = True

            self.__set_filename_and_modified(filename, False)
        finally:
            if not success:
                f.close()
                os.remove(tmpname)

if __name__ == '__main__':
    S = StatementChunk
    B = BlankChunk
    C = CommentChunk
    R = ResultChunk

    def compare(l1, l2):
        if len(l1) != len(l2):
            return False

        for i in xrange(0, len(l1)):
            e1 = l1[i]
            e2 = l2[i]

            if type(e1) != type(e2) or e1.start != e2.start or e1.end != e2.end:
                return False

        return True

    buffer = ShellBuffer(Notebook())

    def validate_nr_start():
        n_nr = 0
        for chunk in buffer.iterate_chunks():
            if chunk.nr_start != n_nr:
                raise AssertionError("nr_start for chunk %s should have been %d but is %d" % (chunk, n_nr, chunk.nr_start))
            assert(chunk.nr_start == n_nr)
            if not isinstance(chunk, ResultChunk):
                n_nr += 1 + chunk.end - chunk.start
                
    def expect(expected):
        chunks = [ x for x in buffer.iterate_chunks() ]
        if not compare(chunks, expected):
            raise AssertionError("\nGot:\n   %s\nExpected:\n   %s" % (chunks, expected))
        validate_nr_start()

    def expect_text(expected, start_line=None, start_offset=None, end_line=None, end_offset=None):
        if start_offset != None:
            i = buffer.get_iter_at_line_offset(start_line, start_offset)
        else:
            i = None
            
        if end_offset != None:
            j = buffer.get_iter_at_line_offset(end_line, end_offset)
        else:
            j = None
        
        text = buffer.get_public_text(i, j)
        if (text != expected):
            raise AssertionError("\nGot:\n   '%s'\nExpected:\n   '%s'" % (text, expected))

    def insert(line, offset, text):
        i = buffer.get_iter_at_line_offset(line, offset)
        buffer.insert_interactive(i, text, True)

    def delete(start_line, start_offset, end_line, end_offset):
        i = buffer.get_iter_at_line_offset(start_line, start_offset)
        j = buffer.get_iter_at_line_offset(end_line, end_offset)
        buffer.delete_interactive(i, j, True)

    def clear():
        buffer.clear()

    # Basic operation
    insert(0, 0, "1\n\n#2\ndef a():\n  3")
    expect([S(0,0), B(1,1), C(2,2), S(3,4)])

    clear()
    expect([B(0,0)])

    # Turning a statement into a continuation line
    insert(0, 0, "1 \\\n+ 2\n")
    insert(1, 0, " ")
    expect([S(0,1), B(2,2)])

    # Calculation resulting in result chunks
    insert(2, 0, "3\n")
    buffer.calculate()
    expect([S(0,1), R(2,2), S(3,3), R(4,4), B(5,5)])

    # Check that splitting a statement with a delete results in the
    # result chunk being moved to the last line of the first half
    delete(1, 0, 1, 1)
    expect([S(0,0), R(1,1), S(2,2), S(3,3), R(4,4), B(5,5)])

    # Editing a continuation line, while leaving it a continuation
    clear()
    
    insert(0, 0, "1\\\n  + 2\\\n  + 3")
    delete(1, 0, 1, 1)
    expect([S(0,2)])

    # Editing a line with an existing error chunk to fix the error
    clear()
    
    insert(0, 0, "a\na=2")
    buffer.calculate()
    
    insert(0, 0, "2")
    delete(0, 1, 0, 2)
    buffer.calculate()
    expect([S(0,0), R(1,1), S(2,2)])

    # Deleting an entire continuation line
    clear()
    
    insert(0, 0, "for i in (1,2):\n    print i\n    print i + 1\n")
    expect([S(0,2), B(3,3)])
    delete(1, 0, 2, 0)
    expect([S(0,1), B(2,2)])

    # Test an attempt to join a ResultChunk onto a previous chunk; should ignore
    clear()

    insert(0, 0, "1\n");
    buffer.calculate()
    expect([S(0,0), R(1,1), B(2,2)])
    delete(0, 1, 1, 0)
    expect_text("1\n");

    # Test an attempt to join a chunk onto a previous ResultChunk, should move
    # the ResultChunk and do the modification
    clear()
    
    insert(0, 0, "1\n2\n");
    buffer.calculate()
    expect([S(0,0), R(1,1), S(2,2), R(3,3), B(4,4)])
    delete(1, 1, 2, 0)
    expect([S(0,0), R(1,1), B(2,2)])
    expect_text("12\n");

    # Test inserting random text inside a result chunk, should ignore
    clear()
    
    insert(0, 0, "1\n2");
    buffer.calculate()
    expect([S(0,0), R(1,1), S(2,2), R(3,3)])
    insert(1, 0, "foo")
    expect_text("1\n2");
    expect([S(0,0), R(1,1), S(2,2), R(3,3)])

    # Test inserting a newline at the end of a result chunk, should create
    # a new line
    insert(1, 1, "\n")
    expect_text("1\n\n2");
    expect([S(0,0), R(1,1), B(2,2), S(3,3), R(4,4)])

    # Same, at the end of the buffer
    insert(4, 1, "\n")
    expect_text("1\n\n2\n");
    expect([S(0,0), R(1,1), B(2,2), S(3,3), R(4,4), B(5,5)])

    # Try undoing these insertions
    buffer.undo()
    expect_text("1\n\n2");
    expect([S(0,0), R(1,1), B(2,2), S(3,3), R(4,4)])

    buffer.undo()
    expect_text("1\n2");
    expect([S(0,0), R(1,1), S(2,2), R(3,3)])
    
    # Calculation resulting in a multi-line result change
    clear()
    
    insert(0, 0, "for i in range(0, 10): print i")
    buffer.calculate()
    expect([S(0, 0), R(1, 10)])

    # Test deleting a range containing both results and statements

    clear()
    
    insert(0, 0, "1\n2\n3\n4\n")
    buffer.calculate()
    expect([S(0,0), R(1,1), S(2,2), R(3,3), S(4,4), R(5,5), S(6,6), R(7,7), B(8,8)])

    delete(2, 0, 5, 0)
    expect([S(0,0), R(1,1), S(2,2), R(3,3), B(4,4)])

    # Inserting an entire new statement in the middle
    insert(2, 0, "2.5\n")
    expect([S(0,0), R(1,1), S(2,2), S(3,3), R(4,4), B(5,5)])
    buffer.calculate()
    expect([S(0,0), R(1,1), S(2,2), R(3, 3), S(4, 4), R(5,5), B(6,6)])

    # Check that inserting a blank line at the beginning of a statement leaves
    # the result behind
    insert(2, 0, "\n")
    expect([S(0,0), R(1,1), B(2,2), S(3,3), R(4,4), S(5,5), R(6,6), B(7,7)])

    # Test deleting a range including a result and joining two statements
    clear()
    insert(0, 0, "12\n34")
    buffer.calculate()
    delete(0, 1, 2, 1)
    expect_text("14")

    # Undo tests
    clear()

    insert(0, 0, "1")
    buffer.undo()
    expect_text("")
    buffer.redo()
    expect_text("1")

    # Undoing insertion of a newline
    clear()

    insert(0, 0, "1 ")
    insert(0, 1, "\n")
    buffer.calculate()
    buffer.undo()
    expect_text("1 ")

    # Test the "pruning" behavior of modifications after undos
    clear()
    
    insert(0, 0, "1")
    buffer.undo()
    expect_text("")
    insert(0, 0, "2")
    buffer.redo() # does nothing
    expect_text("2")
    insert(0, 0, "2\n")

    # Test coalescing consecutive inserts
    clear()
    
    insert(0, 0, "1")
    insert(0, 1, "2")
    buffer.undo()
    expect_text("")

    # Test grouping of multiple undos by user actions
    clear()

    insert(0, 0, "1")
    buffer.begin_user_action()
    delete(0, 0, 0, 1)
    insert(0, 0, "2")
    buffer.end_user_action()
    buffer.undo()
    expect_text("1")
    buffer.redo()
    expect_text("2")

    # Make sure that coalescing doesn't coalesce one user action with
    # only part of another
    clear()

    insert(0, 0, "1")
    buffer.begin_user_action()
    insert(0, 1, "2")
    delete(0, 0, 0, 1)
    buffer.end_user_action()
    buffer.undo()
    expect_text("1")
    buffer.redo()
    expect_text("2")
    
    # Test an undo of an insert that caused insertion of result chunks
    clear()

    insert(0, 0, "2\n")
    expect([S(0,0), B(1,1)])
    buffer.calculate()
    expect([S(0,0), R(1,1), B(2,2)])
    insert(0, 0, "1\n")
    buffer.calculate()
    buffer.undo()
    expect([S(0,0), R(1,1), B(2,2)])
    expect_text("2\n")

    # Tests of get_public_text()
    clear()
    insert(0, 0, "12\n34\n56")
    buffer.calculate()

    expect_text("12\n34\n56", 0, 0, 5, 2)
    expect_text("4\n5", 2, 1, 4, 1)

    # within a single result get_public_text() *does* include the text of the result
    expect_text("1", 1, 0, 1, 1)

    #
    # Try writing to a file, and reading it back
    #
    import tempfile, os

    clear()
    expect([B(0,0)])

    SAVE_TEST = """a = 1
a
# A comment

b = 2"""

    insert(0, 0, SAVE_TEST)
    buffer.calculate()
    
    handle, fname = tempfile.mkstemp(".txt", "shell_buffer")
    os.close(handle)
    
    try:
        buffer.save(fname)
        f = open(fname, "r")
        saved = f.read()
        f.close()

        if saved != SAVE_TEST:
            raise AssertionError("Got '%s', expected '%s'", saved, SAVE_TEST)

        buffer.load(fname)
        buffer.calculate()

        expect([S(0,0), S(1,1), R(2,2), C(3,3), B(4,4), S(5,5)])
    finally:
        os.remove(fname)

    clear()
    expect([B(0,0)])
