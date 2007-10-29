#!/usr/bin/python
import gobject
import gtk
import traceback
import os
import re
from notebook import Notebook
from statement import Statement, ExecutionError
from worksheet import Worksheet
from custom_result import CustomResult

_verbose = False

_OP_INSERT = 0
_OP_DELETE = 1

class StatementChunk:
    def __init__(self, start=-1, end=-1, nr_start=-1):
        self.start = start
        self.end = end
        # this is the start index ignoring result chunks; we need this for
        # storing items in the undo ring
        self.nr_start = nr_start
        self.set_text(None)
        
        self.results = None

        self.error_message = None
        self.error_line = None
        self.error_offset = None
        
    def __repr__(self):
        return "StatementChunk(%d,%d,%s,%s,'%s')" % (self.start, self.end, self.needs_compile, self.needs_execute, self.text)

    def set_text(self, text):
        try:
            if text == self.text:
                return
        except AttributeError:
            pass
        
        self.text = text
        self.needs_compile = text != None
        self.needs_execute = False
        
        self.statement = None

    def mark_for_execute(self):
        if self.statement == None:
            return

        self.needs_execute = True

    def compile(self, worksheet):
        if self.statement != None:
            return
        
        self.needs_compile = False
        
        self.results = None

        self.error_message = None
        self.error_line = None
        self.error_offset = None
        
        try:
            self.statement = Statement(self.text, worksheet)
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
            self.error_message = "\n".join(traceback.format_tb(e.traceback)[2:]) + "\n" + str(e.cause)
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
        self.__error_tag = self.create_tag(foreground="#aa0000")
        self.__recompute_tag = self.create_tag(foreground="#888888")
        self.__comment_tag = self.create_tag(foreground="#00aa00")
        self.__lines = [""]
        self.__chunks = [BlankChunk(0,0, 0)]
        self.__modifying_results = False
        self.__applying_undo = False
        self.__user_action_count = 0

        self.__undo_stack = []
        self.__undo_position = 0
        
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
            text = "\n".join(filter(notnull, lines[0:statement_end + 1 - chunk_start]))

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

                changed = text != old_statement.text
                chunk = old_statement
            else:
                changed = True
                chunk = StatementChunk()

            if changed:
                changed_chunks.append(chunk)
                
            chunk.start = chunk_start
            chunk.end = statement_end
            chunk.set_text(text)
            self.__compute_nr_start(chunk)
            self.__remove_tag_from_chunk(self.__comment_tag, chunk)
            
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

    def __mark_rest_for_execute(self, start_line):
        for chunk in self.iterate_chunks(start_line):
            if isinstance(chunk, StatementChunk):
                chunk.mark_for_execute()

                result = self.__find_result(chunk)
                if result:
                    self.__apply_tag_to_chunk(self.__recompute_tag, result)
                        
                self.emit("chunk-status-changed", chunk)
                if result:
                    self.emit("chunk-status-changed", result)
    
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

            self.__mark_rest_for_execute(first_changed_line)
        elif entire_statements_deleted:
            # If the user deleted entire statements we need to mark subsequent chunks
            # as needing compilation even if all the remaining statements remained unchanged
            self.__mark_rest_for_execute(end_line + 1)
            
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
            line = chunk.end + 1
            chunk = self.__chunks[line]
            while chunk == None:
                line += 1
                chunk = self.__chunks[line]

    def do_begin_user_action(self):
        self.__user_action_count += 1
        
    def do_end_user_action(self):
        self.__user_action_count -= 1

    def __compute_nr_pos_from_iter(self, iter):
        line = iter.get_line()
        chunk = self.__chunks[line]
        return (line - chunk.start + chunk.nr_start, iter.get_line_offset())

    def __compute_nr_pos_from_line_offset(self, line, offset):
        chunk = self.__chunks[line]
        return (line - chunk.start + chunk.nr_start, offset)

    def __get_iter_at_nr_pos(self, nr_pos):
        nr_line, offset = nr_pos
        for chunk in self.iterate_chunks():
            if not isinstance(chunk, ResultChunk) and chunk.nr_start + (chunk.end - chunk.start) >= nr_line:
                line = chunk.start + nr_line - chunk.nr_start
                iter = self.get_iter_at_line(line)
                iter.set_line_offset(offset)

                return iter

        raise AssertionError("nr_pos pointed outside buffer")

    def do_insert_text(self, location, text, text_len):
        start_line = location.get_line()
        if self.__user_action_count > 0:
            if isinstance(self.__chunks[start_line], ResultChunk):
                return

        if _verbose:
            if not self.__modifying_results:
                print "Inserting '%s' at %s" % (text, (location.get_line(), location.get_line_offset()))

        start_pos = self.__compute_nr_pos_from_iter(location)
        
        gtk.TextBuffer.do_insert_text(self, location, text, text_len)
        end_line = location.get_line()
        end_offset = location.get_line_offset()

        if self.__modifying_results:
            return

        if self.__user_action_count > 0:
            self.__set_modified(True)

        result_fixup_state = self.__get_result_fixup_state(start_line, start_line)
            
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
        self.__append_undo_op((_OP_INSERT, start_pos, end_pos, text[0:text_len]))

        self.__fixup_results(result_fixup_state, [location])

        if _verbose:
            print "After insert, chunks are", self.__chunks

    def __delete_chunk(self, chunk, revalidate_iter1=None, revalidate_iter2=None):
        # revalidate_iter1 and revalidate_iter2 get moved to point to the location
        # of the deleted chunk and revalidated. This is useful only as part of the
        # workaround-hack in __fixup_results
        self.__modifying_results = True

        if revalidate_iter1 != None:
            i_start = revalidate_iter1
            i_start.set_line(chunk.start)
        else:
            i_start = self.get_iter_at_line(chunk.start)
        if revalidate_iter2 != None:
            i_end = revalidate_iter2
            i_end.set_line(chunk.end)
        else:
            i_end = self.get_iter_at_line(chunk.end)
        i_end.forward_line()
        if i_end.get_line() == chunk.end: # Last line of buffer
            i_end.forward_to_line_end()
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

    def __move_iter_to_mark(self, iter, mark):
        new = self.get_iter_at_mark(mark)
        iter.set_line(new.get_line())
        iter.set_line_index(new.get_line_index())

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

        # This hack is a workaround for being unable to assign iters by value in PyGtk, see
        #   http://bugzilla.gnome.org/show_bug.cgi?id=481715
        if len(revalidate_iters) > 0:
            revalidate_iter = revalidate_iters[0]
        else:
            revalidate_iter = None

        if len(revalidate_iters) > 1:
            raise Exception("I don't know how to keep more than one iter valid")

        if move_before:
            self.__delete_chunk(state.result_before, revalidate_iter1=revalidate_iter)
            self.insert_result(state.statement_before, revalidate_iter=revalidate_iter)

        if delete_after or move_after:
            self.__delete_chunk(state.result_after, revalidate_iter1=revalidate_iter)
            if move_after:
                self.insert_result(state.statement_after, revalidate_iter=revalidate_iter)

        for iter, mark in revalidate:
            self.__move_iter_to_mark(iter, mark)
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
                self.__delete_chunk(result_chunk, revalidate_iter1=start, revalidate_iter2=end)
                self.__modifying_results = False
                start_line -= 1 + result_chunk.end - result_chunk.start
                end_line -= 1 + result_chunk.end - result_chunk.start
                start.set_line(start_line)
                start.forward_to_line_end()
                end.set_line(end_line)
                end.set_line_offset(end_offset)
                
            if end.starts_line() and not start.starts_line() and isinstance(self.__chunks[end_line], ResultChunk):
                # Merging a ResultChunk onto the end of another chunk; just ignore this; we do have
                # have to be careful to avoid leaving end pointing to the same place as start, since
                # we'll then go into an infinite loop
                new_end = end.copy()
                
                new_end.backward_line()
                new_end.forward_to_line_end()

                if start.compare(new_end) == 0:
                    return

                end.backward_line()
                new_end.forward_to_line_end()
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

        self.__append_undo_op((_OP_DELETE, start_pos, end_pos, deleted_text))

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

        # We can only revalidate one iter due to PyGTK limitations; see comment in __fixup_results
        # It turns out it works to cheat and only revalidate the end iter
#        self.__fixup_results(result_fixup_state, [start, end])
        self.__fixup_results(result_fixup_state, [end])

        if restore_result_statement != None and \
                self.__chunks[restore_result_statement.start] == restore_result_statement and \
                self.__find_result(restore_result_statement) == None:
            # As above, we can only revalidate the end iter
            mark = self.create_mark(None, end, True)
            self.insert_result(restore_result_statement, revalidate_iter=end)
            self.__move_iter_to_mark(end, mark)
            self.delete_mark(mark)

        if _verbose:
            print "After delete, chunks are", self.__chunks
            print "After delete, end is at ", ((end.get_line(), end.get_offset()),)

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

    def undo(self):
        if self.__undo_position == 0:
            return

        self.__applying_undo = True
        try:
            self.__undo_position -= 1
            op = self.__undo_stack[self.__undo_position]
            if op[0] == _OP_INSERT:
                start = self.__get_iter_at_nr_pos(op[1])
                end = self.__get_iter_at_nr_pos(op[2])
                self.delete_interactive(start, end, True)
            elif op[0] == _OP_DELETE:
                start = self.__get_iter_at_nr_pos(op[1])
                self.insert_interactive(start, op[3], len(op[3]), True)
        finally:
            self.__applying_undo = False

    def redo(self):
        if self.__undo_position == len(self.__undo_stack):
            return

        self.__applying_undo = True
        try:
            self.__undo_position += 1
            op = self.__undo_stack[self.__undo_position - 1]
            if op[0] == _OP_INSERT:
                start = self.__get_iter_at_nr_pos(op[1])
                self.insert_interactive(start, op[3], len(op[3]), True)
            elif op[0] == _OP_DELETE:
                start = self.__get_iter_at_nr_pos(op[1])
                end = self.__get_iter_at_nr_pos(op[2])
                self.delete_interactive(start, end, True)
        finally:
            self.__applying_undo = False
            
    def __append_undo_op(self, op):
        if self.__applying_undo:
            return
        
        if self.__undo_position < len(self.__undo_stack):
            self.__undo_stack[self.__undo_position:] = []
        self.__undo_stack.append(op)
        self.__undo_position += 1
        
    def clear_undo_stack(self):
        self.__undo_stack = []
        self.__undo_position = 0

    def get_chunk(self, line_index):
        return self.__chunks[line_index]

    def __apply_tag_to_chunk(self, tag, chunk):
        start = self.get_iter_at_line(chunk.start)
        end = self.get_iter_at_line(chunk.end)
        end.forward_to_line_end()
        self.apply_tag(tag, start,end)
    
    def __remove_tag_from_chunk(self, tag, chunk):
        start = self.get_iter_at_line(chunk.start)
        end = self.get_iter_at_line(chunk.end)
        end.forward_to_line_end()
        self.remove_tag(tag, start,end)
    
    def insert_result(self, chunk, revalidate_iter=None):
        # revalidate_iter gets move to point to the end of the inserted result and revalidated.
        # This is useful only as part of the workaround-hack in __fixup_results
        self.__modifying_results = True
        if revalidate_iter != None:
            location = revalidate_iter
            location.set_line(chunk.end)
        else:
            location = self.get_iter_at_line(chunk.end)
        location.forward_to_line_end()

        if chunk.error_message:
            results = [ chunk.error_message ]
        else:
            results = chunk.results

        for result in results:
            if isinstance(result, basestring):
                self.insert(location, "\n" + result)
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
        self.clear_undo_stack()

    def load(self, filename):
        f = open(filename)
        text = f.read()
        f.close()
        
        self.__do_clear()
        self.__set_filename_and_modified(filename, False)
        self.insert(self.get_start_iter(), text)
        self.clear_undo_stack()

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
            iter = self.get_start_iter()
            for chunk in self.iterate_chunks():
                next = iter.copy()
                while next.get_line() <= chunk.end:
                    if not next.forward_line(): # at end of buffer
                        break

                if not isinstance(chunk, ResultChunk):
                    chunk_text = self.get_slice(iter, next)
                    f.write(chunk_text)

                iter = next
            
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

    def expect_text(expected):
        text = ""
        iter = buffer.get_start_iter()
        for chunk in buffer.iterate_chunks():
            next = iter.copy()
            while next.get_line() <= chunk.end:
                if not next.forward_line(): # at end of buffer
                    break

            if not isinstance(chunk, ResultChunk):
                chunk_text = buffer.get_slice(iter, next)
                text += chunk_text

            iter = next

        if (text != expected):
            raise AssertionError("\nGot:\n   '%s'\nExpected:\n   '%s'" % (text, expected))

    def insert(line, offset, text):
        i = buffer.get_iter_at_line(line)
        i.set_line_offset(offset)
        buffer.insert_interactive(i, text, True)

    def delete(start_line, start_offset, end_line, end_offset):
        i = buffer.get_iter_at_line(start_line)
        i.set_line_offset(start_offset)
        j = buffer.get_iter_at_line(end_line)
        j.set_line_offset(end_offset)
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

    # Undo tests
    clear()

    insert(0, 0, "1")
    buffer.undo()
    expect_text("")
    buffer.redo()
    expect_text("1")

    # Undoing insertion of a newline
    clear()

    insert(0, 0, "1")
    insert(0, 1, "\n")
    buffer.calculate()
    buffer.undo()
    expect_text("1")

    # Test the "pruning" behavior of modifications after undos
    clear()
    
    insert(0, 0, "1")
    buffer.undo()
    expect_text("")
    insert(0, 0, "2")
    buffer.redo() # does nothing
    expect_text("2")
    insert(0, 0, "2\n")
    
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
