#!/usr/bin/python
import gtk
from ShellBuffer import ShellBuffer, StatementChunk

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
