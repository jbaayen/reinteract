#!/usr/bin/python
import gobject
import gtk
import re

class StatementChunk:
    def __init__(self, start=-1, end=-1):
        self.start = start
        self.end = end
        self.changed = True
        self.text = None
        
    def __repr__(self):
        return "StatementChunk(%d,%d,%s,'%s')" % (self.start, self.end, self.changed, self.text)

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
        return "ResultChunk(%d,%d)" % (self.start, self.end)
    
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
            
        chunk_start = rescan_start
        statement_end = rescan_start - 1
        chunk_lines = []

        line = rescan_start
        i = self.get_iter_at_line(rescan_start)

        changed_chunks = []

        for line in xrange(rescan_start, end_line + 1):
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
        for chunk in changed_chunks:
            self.emit("chunk-status-changed", chunk)
            
    def iterate_chunks(self, start_line=0, end_line=None):
        if end_line == None:
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
        # revalidate_iter1 and revalidate_iter2 get validated to point to the location
        # of the deleted chunk. This is useful only as part of the workaround-hack in
        # __fixup_results
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

    def __get_result_fixup_state(self, first_modified_line, last_modified_line):
        state = ResultChunkFixupState()

        state.first_modified_line = first_modified_line
        state.statement_before = None
        state.statement_before_text = None
        state.result_before = None
        for i in xrange(first_modified_line - 1, -1, -1):
            if isinstance(self.__chunks[i], StatementChunk):
                # If the statement before continues into the modified region, there can be
                # no intervening Result chunk, and no fixup is needed
                if self.__chunks[i].end >= first_modified_line:
                    break
                
                state.statement_before = self.__chunks[i]
                state.statement_before_text = self.__chunks[i].text
                
                if isinstance(self.__chunks[state.statement_before.end + 1], ResultChunk):
                    state.result_before = self.__chunks[state.statement_before.end + 1]
                    break

        state.last_statement = None
        state.result_after = None
        if isinstance(self.__chunks[last_modified_line], StatementChunk):
            line_after = self.__chunks[last_modified_line].end + 1
            if line_after < len(self.__chunks) and isinstance(self.__chunks[line_after], ResultChunk):
                state.last_statement = self.__chunks[last_modified_line]
                state.result_after = self.__chunks[line_after]

        return state

    def __fixup_results(self, state, revalidate_iters):
        # If we merged new text into the previous statement, then we need to delete
        # the result for the previous statement
        delete_before = state.result_before != None and state.statement_before.text != state.statement_before_text
        
        # If the statement that had a result after the deleted segment is now gone
        # then we need to delete that result
        if state.last_statement != None:
            if state.last_statement.end < state.first_modified_line:
                test_line = state.last_statement.end
            else:
                test_line = state.first_modified_line

            delete_after = self.__chunks[test_line] != state.last_statement
        else:
            delete_after = False
                
        
        if not (delete_before or delete_after):
            return
        
        revalidate = map(lambda iter: (iter, self.create_mark(None, iter, True)), revalidate_iters)

        # This hack is a workaround for being unable to assign iters by value in PyGtk, see
        #   http://bugzilla.gnome.org/show_bug.cgi?id=481715
        if len(revalidate_iters) > 0:
            revalidate_iter1 = revalidate_iters[0]
        else:
            revalidate_iter1 = None

        if len(revalidate_iters) > 1:
            revalidate_iter2 = revalidate_iters[1]
        else:
            revalidate_iter2 = None

        if len(revalidate_iters) > 2:
            raise Exception("I don't know how to keep more than two iters valid")

        if delete_before:
            self.__delete_chunk(state.result_before, revalidate_iter1=revalidate_iter1, revalidate_iter2=revalidate_iter2)

        if delete_after:
            self.__delete_chunk(state.result_after, revalidate_iter1=revalidate_iter1, revalidate_iter2=revalidate_iter2)

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

        self.__fixup_results(result_fixup_state, [start, end])
        
        print "After delete, chunks are", self.__chunks
        
    def calculate(self):
        for chunk in self.iterate_chunks():
            if isinstance(chunk, StatementChunk) and chunk.changed:
                chunk.changed = False
                self.insert_result(chunk, "Result")
                
                self.emit("chunk-status-changed", chunk)

        print "After calculate, chunks are", self.__chunks

    def get_chunk(self, line_index):
        return self.__chunks[line_index]

    def insert_result(self, chunk, text):
        self.__modifying_results = True
        location = self.get_iter_at_line(chunk.end)
        location.forward_to_line_end()
            
        self.insert(location, "\n" + text)
        self.__modifying_results = False
        n_inserted = location.get_line() - chunk.end
        self.apply_tag(self.__result_tag, self.get_iter_at_line(chunk.end + 1), location)

        result_chunk = ResultChunk(chunk.end + 1, chunk.end + n_inserted)
        self.__chunks[chunk.end + 1:chunk.end + 1] = [result_chunk for i in xrange(0, n_inserted)]
        self.__lines[chunk.end + 1:chunk.end + 1] = [None for i in xrange(0, n_inserted)]
        
        for chunk in self.iterate_chunks(result_chunk.end + 1):
            chunk.start += n_inserted
            chunk.end += n_inserted

class ShellView(gtk.TextView):
    __gsignals__ = {
        'expose-event': 'override'
   }
        
    def __init__(self, buffer=None):
        if buffer == None:
            buffer = ShellBuffer()

        buffer.connect('chunk-status-changed', self.on_chunk_status_changed)
            
        gtk.TextView.__init__(self, buffer)
        self.set_border_window_size(gtk.TEXT_WINDOW_LEFT, 10)

    def do_expose_event(self, event):
        if event.window != self.get_window(gtk.TEXT_WINDOW_LEFT):
            return gtk.TextView.do_expose_event(self, event)

        (_, start_y) = self.window_to_buffer_coords(gtk.TEXT_WINDOW_LEFT, 0, event.area.y)
        (start_line, _) = self.get_line_at_y(start_y)
        
        (_, end_y) = self.window_to_buffer_coords(gtk.TEXT_WINDOW_LEFT, 0, event.area.y + event.area.height - 1)
        (end_line, _) = self.get_line_at_y(end_y)
        
        line_index = start_line.get_line()
            
        cr = event.window.cairo_create()
        cr.set_source_rgb(1, 0, 0)

        buffer = self.get_buffer()
        while start_line.compare(end_line) <= 0:
            chunk = buffer.get_chunk(line_index)
            if isinstance(chunk, StatementChunk) and chunk.changed:
                (y, height) = self.get_line_yrange(start_line)

                (_, window_y) = self.buffer_to_window_coords(gtk.TEXT_WINDOW_LEFT, 0, y)
                cr.rectangle(event.area.x, window_y, event.area.width, height)
                cr.fill()
            
            if not start_line.forward_line():
                break
            line_index += 1
        
        return False

    def on_chunk_status_changed(self, buffer, chunk):
        buffer = self.get_buffer()
        
        (start_y, start_height) = self.get_line_yrange(buffer.get_iter_at_line(chunk.start))
        (end_y, end_height) = self.get_line_yrange(buffer.get_iter_at_line(chunk.end))

        (_, window_y) = self.buffer_to_window_coords(gtk.TEXT_WINDOW_LEFT, 0, start_y)
        
        self.get_window(gtk.TEXT_WINDOW_LEFT).invalidate_rect((0, window_y, 10, end_y + end_height - start_y), False)
