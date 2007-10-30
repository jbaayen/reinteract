#!/usr/bin/python
import gtk
import re
from shell_buffer import ShellBuffer, StatementChunk, ResultChunk, CommentChunk, BlankChunk

class ShellView(gtk.TextView):
    __gsignals__ = {
        'backspace' : 'override',
        'expose-event': 'override',
        'key-press-event': 'override',
        'realize': 'override'
   }
        
    def __init__(self, buf):
        buf.connect('chunk-status-changed', self.on_chunk_status_changed)
        buf.connect('add-custom-result', self.on_add_custom_result)
            
        gtk.TextView.__init__(self, buf)
        self.set_border_window_size(gtk.TEXT_WINDOW_LEFT, 10)

    def paint_chunk(self, cr, area, chunk, fill_color, outline_color):
        buf = self.get_buffer()
        
        (y, _) = self.get_line_yrange(buf.get_iter_at_line(chunk.start))
        (end_y, end_height) = self.get_line_yrange(buf.get_iter_at_line(chunk.end))
        height = end_y + end_height - y
        
        (_, window_y) = self.buffer_to_window_coords(gtk.TEXT_WINDOW_LEFT, 0, y)
        cr.rectangle(area.x, window_y, area.width, height)
        cr.set_source_rgb(*fill_color)
        cr.fill()
                
        cr.rectangle(0.5, window_y + 0.5, 10 - 1, height - 1)
        cr.set_source_rgb(*outline_color)
        cr.set_line_width(1)
        cr.stroke()

    def do_realize(self):
        gtk.TextView.do_realize(self)

        self.get_window(gtk.TEXT_WINDOW_LEFT).set_background(self.style.white)

    def do_expose_event(self, event):
        if event.window != self.get_window(gtk.TEXT_WINDOW_LEFT):
            return gtk.TextView.do_expose_event(self, event)

        (_, start_y) = self.window_to_buffer_coords(gtk.TEXT_WINDOW_LEFT, 0, event.area.y)
        (start_line, _) = self.get_line_at_y(start_y)
        
        (_, end_y) = self.window_to_buffer_coords(gtk.TEXT_WINDOW_LEFT, 0, event.area.y + event.area.height - 1)
        (end_line, _) = self.get_line_at_y(end_y)

        buf = self.get_buffer()

        cr = event.window.cairo_create()
        
        for chunk in buf.iterate_chunks(start_line.get_line(), end_line.get_line()):
            if isinstance(chunk, StatementChunk):
                if chunk.error_message != None:
                    self.paint_chunk(cr, event.area, chunk, (1, 0, 0), (0.5, 0, 0))
                elif chunk.needs_compile:
                    self.paint_chunk(cr, event.area, chunk, (1, 1, 0), (0.5, 0.5, 0))
                elif chunk.needs_execute:
                    self.paint_chunk(cr, event.area, chunk, (1, 0, 1), (0.5, 0.5, 0))
                else:
                    self.paint_chunk(cr, event.area, chunk, (0, 0, 1), (0, 0, 0.5))
                
        return False

    def __get_line_text(self, iter):
        start = iter.copy()
        start.set_line_index(0)
        end = iter.copy()
        end.forward_to_line_end()
        
        return start.get_slice(end)
    
    # This is likely overengineered, since we're going to try as hard as possible not to
    # have tabs in our worksheets
    def __count_indent(self, text):
        indent = 0
        for c in text:
            if c == ' ':
                indent += 1
            elif c == '\t':
                indent += 8 - (indent % 8)
            else:
                break

        return indent

    def __find_outdent(self, iter):
        buf = self.get_buffer()
        line = iter.get_line()

        current_indent = self.__count_indent(self.__get_line_text(iter))

        previous_line = iter.copy()
        while  line > 0:
            line -= 1
            previous_line.backward_line()
            if not isinstance(buf.get_chunk(line), ResultChunk):
                line_text = self.__get_line_text(previous_line)
                
                indent = self.__count_indent(line_text)
                if indent < current_indent:
                    indent_text = re.match(r"^[\t ]*", line_text).group(0)
                        
                    return indent_text
                
        return ""

    def __find_default_indent(self, iter):
        buf = self.get_buffer()
        line = iter.get_line()

        previous_line = iter.copy()
        while  line > 0:
            line -= 1
            previous_line.backward_line()
            if not isinstance(buf.get_chunk(line), ResultChunk):
                line_text = self.__get_line_text(previous_line)
                
                indent = self.__count_indent(line_text)
                indent_text = re.match(r"^[\t ]*", line_text).group(0)

                if line_text.endswith(":") and not re.match(r"^\s*#", line_text):
                    indent_text += "    "
                        
                return indent_text
                
        return ""

    def __reindent_line(self, iter, indent_text):
        buf = self.get_buffer()

        line_text = self.__get_line_text(iter)
        prefix = re.match(r"^[\t ]*", line_text).group(0)

        diff = self.__count_indent(indent_text) - self.__count_indent(prefix)
        if diff == 0:
            return 0

        common_len = 0
        for a, b in zip(prefix, indent_text):
            if a != b:
                break
            common_len += 1
    
        start = iter.copy()
        start.set_line_offset(common_len)
        end = iter.copy()
        end.set_line_offset(len(prefix))

        # Nitpicky-detail. If the selection starts at the start of the line, and we are
        # inserting white-space there, then the whitespace should be *inside* the selection
        mark_to_start = None
        if common_len == 0 and buf.get_has_selection():
            mark = buf.get_insert()
            if buf.get_iter_at_mark(mark).compare(start) == 0:
                mark_to_start = mark
                
            mark = buf.get_selection_bound()
            if buf.get_iter_at_mark(mark).compare(start) == 0:
                mark_to_start = mark
        
        buf.delete(start, end)
        buf.insert(end, indent_text[common_len:])

        if mark_to_start != None:
            start.set_line_offset(0)
            buf.move_mark(mark_to_start, start)

        return diff

    def __reindent_selection(self, outdent):
        buf = self.get_buffer()

        bounds = buf.get_selection_bounds()
        if bounds == ():
            insert_mark = buf.get_insert()
            bounds = buf.get_iter_at_mark(insert_mark), buf.get_iter_at_mark(insert_mark)
        start, end = bounds

        line = start.get_line()
        end_line = end.get_line()
        if end.starts_line() and end.compare(start) > 0:
            end_line -= 1

        current_chunk = buf.get_chunk(line)
        while isinstance(current_chunk, ResultChunk):
            line += 1
            if line > end_line:
                return
            current_chunk = buf.get_chunk(line)

        iter = buf.get_iter_at_line(line)

        if outdent:
            indent_text = self.__find_outdent(iter)
        else:
            indent_text = self.__find_default_indent(iter)

        diff = self.__reindent_line(iter, indent_text)
        while True:
            line += 1
            if line > end_line:
                return

            current_chunk = buf.get_chunk(line)
            while isinstance(current_chunk, ResultChunk):
                line += 1
                if line > end_line:
                    return
                current_chunk = buf.get_chunk(line)

            iter = buf.get_iter_at_line(line)
            current_indent = self.__count_indent(self.__get_line_text(iter))
            self.__reindent_line(iter, max(0, " " * (current_indent + diff)))
    
    def do_key_press_event(self, event):
        buf = self.get_buffer()
        
        if event.keyval in (gtk.keysyms.KP_Enter, gtk.keysyms.Return):

            increase_indent = False
            insert = buf.get_iter_at_mark(buf.get_insert())

            line = insert.get_line()
            current_chunk = buf.get_chunk(line)

            # Inserting return inside a ResultChunk would normally do nothing
            # but we want to make it insert a line after the chunk
            if isinstance(current_chunk, ResultChunk) and not buf.get_has_selection():
                iter = buf.get_iter_at_line(current_chunk.end)
                if not iter.ends_line():
                    iter.forward_to_line_end()

                buf.insert_interactive(iter, "\n", True)
                buf.place_cursor(iter)
                
                return True

            gtk.TextView.do_key_press_event(self, event)

            insert = buf.get_iter_at_mark(buf.get_insert())
            
            if not isinstance(current_chunk, ResultChunk):
                self.__reindent_line(insert, self.__find_default_indent(insert))
                
            if isinstance(current_chunk, CommentChunk) and line > 0 and isinstance(buf.get_chunk(line - 1), CommentChunk):
                self.get_buffer().insert_interactive_at_cursor("# ", -1)
                
            return True
        elif event.keyval in (gtk.keysyms.Tab, gtk.keysyms.KP_Tab) and event.state & gtk.gdk.CONTROL_MASK == 0:
            self.__reindent_selection(outdent=False)
            return True
        elif event.keyval == gtk.keysyms.ISO_Left_Tab and event.state & gtk.gdk.CONTROL_MASK == 0:
            self.__reindent_selection(outdent=True)
            return True
        elif event.keyval in (gtk.keysyms.z, gtk.keysyms.Z) and \
                (event.state & gtk.gdk.CONTROL_MASK) != 0 and \
                (event.state & gtk.gdk.SHIFT_MASK) == 0:
            buf.undo()
        # This is the gedit/gtksourceview binding to cause your hands to fall off
        elif event.keyval in (gtk.keysyms.z, gtk.keysyms.Z) and \
                (event.state & gtk.gdk.CONTROL_MASK) != 0 and \
                (event.state & gtk.gdk.SHIFT_MASK) != 0:
            buf.redo()
        # This is the familiar binding (Eclipse, etc). Firefox supports both
        elif event.keyval in (gtk.keysyms.y, gtk.keysyms.Y) and event.state & gtk.gdk.CONTROL_MASK != 0:
            buf.redo()
        
        return gtk.TextView.do_key_press_event(self, event)

    def do_backspace(self):
        buf = self.get_buffer()
        
        insert = buf.get_iter_at_mark(buf.get_insert())
        line = insert.get_line()
        
        current_chunk = buf.get_chunk(line)
        if isinstance(current_chunk, StatementChunk) or isinstance(current_chunk, BlankChunk):
            line_start = insert.copy()
            line_start.set_line_offset(0)
            line_text = line_start.get_slice(insert)

            if re.match(r"^[\t ]+$", line_text):
                self.__reindent_line(insert, self.__find_outdent(insert))
                return
                       
        return gtk.TextView.do_backspace(self)

    def on_chunk_status_changed(self, buf, chunk):
        (start_y, start_height) = self.get_line_yrange(buf.get_iter_at_line(chunk.start))
        (end_y, end_height) = self.get_line_yrange(buf.get_iter_at_line(chunk.end))

        (_, window_y) = self.buffer_to_window_coords(gtk.TEXT_WINDOW_LEFT, 0, start_y)

        if self.window:
            self.get_window(gtk.TEXT_WINDOW_LEFT).invalidate_rect((0, window_y, 10, end_y + end_height - start_y), False)

    def on_add_custom_result(self, buf, result, anchor):
        widget = result.create_widget()
        widget.show()
        self.add_child_at_anchor(widget, anchor)
