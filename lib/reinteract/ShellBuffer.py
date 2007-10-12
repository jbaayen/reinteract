#!/usr/bin/python
import gobject
import gtk
import os
import re
from Statement import Statement

class StatementChunk:
    def __init__(self, start=-1, end=-1):
        self.start = start
        self.end = end
        self.changed = True
        self.text = None
        self.result = None
        self.statement = None
        
    def __repr__(self):
        return "StatementChunk(%d,%d,%s,'%s')" % (self.start, self.end, self.changed, self.text)

    def calculate(self, parent):
        self.statement = Statement(self.text, parent)
        self.result = self.statement.eval()

class BlankChunk:
    def __init__(self, start=-1, end=-1):
        self.start = start
        self.end = end
        
    def __repr__(self):
        return "BlankChunk(%d,%d)" % (self.start, self.end)
    
class CommentChunk:
    def __init__(self, start=-1, end=-1):
        self.start = start
        self.end = end
        
    def __repr__(self):
        return "CommentChunk(%d,%d)" % (self.start, self.end)
    
class ResultChunk:
    def __init__(self, start=-1, end=-1):
        self.start = start
        self.end = end
        
    def __repr__(self):
        return "ResultChunk(%d,%d,'%s')" % (self.start, self.end, self.text)
    
BLANK = re.compile(r'^\s*$')
COMMENT = re.compile(r'^\s*#')
CONTINUATION = re.compile(r'^\s+')

class ResultChunkFixupState:
    pass

class ShellBuffer(gtk.TextBuffer):
    __gsignals__ = {
        'begin-user-action': 'override',
        'end-user-action': 'override',
        'insert-text': 'override',
        'delete-range': 'override',
        'chunk-status-changed':  (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
    }

    def __init__(self):
        gtk.TextBuffer.__init__(self)

        self.__red_tag = self.create_tag(foreground="red")
        self.__result_tag = self.create_tag(foreground="gray", editable=False)
        self.__lines = [""]
        self.__chunks = [BlankChunk(0,0)]
        self.__modifying_results = False
        self.__user_action_count = 0
        
        self.filename = None

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

                changed = not old_statement.changed and text != old_statement.text
                old_statement.changed = old_statement.changed or changed
                chunk = old_statement
            else:
                changed = True
                chunk = StatementChunk()

            if changed:
                changed_chunks.append(chunk)
                
            chunk.start = chunk_start
            chunk.end = statement_end
            chunk.text = text
            
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
                chunk.end = i
                self.__chunks[i] = chunk
                self.__lines[i] = lines[i - chunk_start]
            elif COMMENT.match(line):
                if not isinstance(chunk, CommentChunk):
                    chunk = CommentChunk()
                    chunk.start = i
                chunk.end = i
                self.__chunks[i] = chunk
                self.__lines[i] = lines[i - chunk_start]
        
        return changed_chunks
            
    def __rescan(self, start_line, end_line):
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

        # If we end on a statement, then any line in that statement might get merged into a previous statement,
        # so we need to rescan all of it
        rescan_end = end_line
        while rescan_end + 1 < len(self.__chunks):
            if isinstance(self.__chunks[rescan_end + 1], StatementChunk) and self.__chunks[rescan_end + 1].end != rescan_end + 1:
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
            # changed_chunks is the chunks whose text has changed, but actually, we need to
            # recalculate those chunks and all subsequent chunks in the buffer
            first_changed_line = changed_chunks[0].start
            for chunk in changed_chunks:
                if chunk.start < first_changed_line:
                    first_changed_line = chunk.start
                    
                for chunk in self.iterate_chunks(first_changed_line):
                    if isinstance(chunk, StatementChunk):
                        chunk.changed = True
                        self.emit("chunk-status-changed", chunk)
                        
            
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
        
    def do_insert_text(self, location, text, text_len):
        start_line = location.get_line()
        if self.__user_action_count > 0:
            if isinstance(self.__chunks[start_line], ResultChunk):
                return
            
        if not self.__modifying_results:
            print "Inserting '%s' at %s" % (text, (location.get_line(), location.get_line_offset()))

        gtk.TextBuffer.do_insert_text(self, location, text, text_len)
        end_line = location.get_line()

        if self.__modifying_results:
            return

        result_fixup_state = self.__get_result_fixup_state(start_line, start_line)
            
        self.__chunks[start_line + 1:start_line + 1] = [None for i in xrange(start_line, end_line)]
        self.__lines[start_line + 1:start_line + 1] = [None for i in xrange(start_line, end_line)]

        for chunk in self.iterate_chunks(start_line):
            if chunk.start > start_line:
                chunk.start += (end_line - start_line)
            if chunk.end > start_line:
                chunk.end += (end_line - start_line)
            
        self.__rescan(start_line, end_line)

        self.__fixup_results(result_fixup_state, [location])

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
        
        self.__modifying_results = False

    def __find_result(self, statement):
        for chunk in self.iterate_chunks(statement.end + 1):
            if isinstance(chunk, ResultChunk):
                return chunk
            elif isinstance(chunk, StatementChunk):
                return None
        
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
            new = self.get_iter_at_mark(mark)
            iter.set_line(new.get_line())
            iter.set_line_index(new.get_line_index())
            self.delete_mark(mark)
        
    def do_delete_range(self, start, end):
        start_line = start.get_line()
        end_line = end.get_line()

        # Prevent the user from doing deletes that would merge a ResultChunk chunk into a statement
        if self.__user_action_count > 0 and not self.__modifying_results:
            if start.ends_line() and isinstance(self.__chunks[start_line], ResultChunk):
                start.forward_line()
                start_line += 1
            if end.starts_line() and not start.starts_line() and isinstance(self.__chunks[end_line], ResultChunk):
                end.backward_line()
                end.forward_to_line_end()
                end_line -= 1

            if start.compare(end) == 0:
                return
                
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

        if not self.__modifying_results:
            print "Deleting range %s" % (((start.get_line(), start.get_line_offset()), (end.get_line(), end.get_line_offset())),)
            print "first_deleted_line=%d, last_deleted_line=%d, new_start=%d, new_end=%d, last_modified_line=%d" % (first_deleted_line, last_deleted_line, new_start, new_end, last_modified_line)
        
        gtk.TextBuffer.do_delete_range(self, start, end)

        if self.__modifying_results:
            return

        result_fixup_state = self.__get_result_fixup_state(new_start, last_modified_line)

        self.__chunks[first_deleted_line:last_deleted_line + 1] = []
        self.__lines[first_deleted_line:last_deleted_line + 1] = []
        n_deleted = 1 + last_deleted_line - first_deleted_line

        for chunk in self.iterate_chunks(0, new_start - 1):
            if chunk.end >= last_deleted_line:
                chunk.end -= n_deleted;
            elif chunk.end >= first_deleted_line:
                chunk.end = first_deleted_line - 1

        for chunk in self.iterate_chunks(new_end + 1):
            if chunk.start >= last_deleted_line:
                chunk.start -= n_deleted
            if chunk.end >= last_deleted_line:
                chunk.end -= n_deleted

        self.__rescan(new_start, new_end)

        # We can only revalidate one iter due to PyGTK limitations; see comment in __fixup_results
        # It turns out it works to cheat and only revalidate the end iter
#        self.__fixup_results(result_fixup_state, [start, end])
        self.__fixup_results(result_fixup_state, [end])
        
        print "After delete, chunks are", self.__chunks
        
    def calculate(self):
        parent = None
        have_change = False
        for chunk in self.iterate_chunks():
            if isinstance(chunk, StatementChunk):
                if have_change or chunk.changed:
                    chunk.changed = False
                    old_result = self.__find_result(chunk)
                    if old_result:
                        self.__delete_chunk(old_result)

                    chunk.calculate(parent)
                    if chunk.result != None:
                        self.insert_result(chunk)
                
                    self.emit("chunk-status-changed", chunk)

                parent = chunk.statement

        print "After calculate, chunks are", self.__chunks

    def get_chunk(self, line_index):
        return self.__chunks[line_index]

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
            
        self.insert(location, "\n" + chunk.result)
        self.__modifying_results = False
        n_inserted = location.get_line() - chunk.end
        self.apply_tag(self.__result_tag, self.get_iter_at_line(chunk.end + 1), location)

        result_chunk = ResultChunk(chunk.end + 1, chunk.end + n_inserted)
        result_chunk.text = chunk.result
        self.__chunks[chunk.end + 1:chunk.end + 1] = [result_chunk for i in xrange(0, n_inserted)]
        self.__lines[chunk.end + 1:chunk.end + 1] = [None for i in xrange(0, n_inserted)]
        
        for chunk in self.iterate_chunks(result_chunk.end + 1):
            chunk.start += n_inserted
            chunk.end += n_inserted

    def clear(self):
        # This is actually working pretty much coincidentally, since the Delete
        # code wasn't really written with non-interactive deletes in mind, and
        # when there are ResultChunk present, a non-interactive delete will
        # use ranges including them. But the logic happens to work out.
        
        self.delete(self.get_start_iter(), self.get_end_iter())        
        self.filename = None

    def load(self, filename):
        f = open(filename)
        text = f.read()
        f.close()
        
        self.clear()
        self.insert(self.get_start_iter(), text)

        self.filename = filename

    def save(self, filename=None):
        if filename == None:
            if self.filename == None:
                raise ValueError("No currnet or specified filename")

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

            self.filename = filename
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

    buffer = ShellBuffer()

    def expect(expected):
        chunks = [ x for x in buffer.iterate_chunks() ]
        if not compare(chunks, expected):
            raise AssertionError("Got:\n   %s\nExpected:\n   %s" % (chunks, expected))

    def insert(line, offset, text):
        i = buffer.get_iter_at_line(line)
        i.set_line_offset(offset)
        buffer.insert(i, text)

    def delete(start_line, start_offset, end_line, end_offset):
        i = buffer.get_iter_at_line(start_line)
        i.set_line_offset(start_offset)
        j = buffer.get_iter_at_line(end_line)
        j.set_line_offset(end_offset)
        buffer.delete_interactive(i, j, True)

    # Basic operation
    insert(0, 0, "1\n\n#2\ndef a():\n  3")
    expect([S(0,0), B(1,1), C(2,2), S(3,4)])

    buffer.clear()
    expect([B(0,0)])

    # Turning a statement into a continuation line
    insert(0, 0, "1 \\\n+ 2\n")
    insert(1, 0, " ")
    expect([S(0,1), B(2,2)])

    # Calculation resulting in result chunks
    insert(2, 0, "3\n")
    buffer.calculate()
    expect([S(0,1), R(2,2), S(3,3), R(4,4), B(5,5)])

    # Check that splitting a statement with an insert results in the
    # result chunk being moved to the last line of the first half
    delete(1, 0, 1, 1)
    expect([S(0,0), R(1,1), S(2,2), S(3,3), R(4,4), B(5,5)])

    #
    # Try writing to a file, and reading it back
    #
    import tempfile, os

    buffer.clear()
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

    buffer.clear()
    expect([B(0,0)])
