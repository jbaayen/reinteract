#!/usr/bin/python
import gtk
from shell_buffer import ShellBuffer, StatementChunk, ResultChunk

class ShellView(gtk.TextView):
    __gsignals__ = {
        'realize': 'override',
        'expose-event': 'override'
   }
        
    def __init__(self, buf=None):
        if buf == None:
            buf = ShellBuffer()

        buf.connect('chunk-status-changed', self.on_chunk_status_changed)
            
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

    def on_chunk_status_changed(self, buf, chunk):
        (start_y, start_height) = self.get_line_yrange(buf.get_iter_at_line(chunk.start))
        (end_y, end_height) = self.get_line_yrange(buf.get_iter_at_line(chunk.end))

        (_, window_y) = self.buffer_to_window_coords(gtk.TEXT_WINDOW_LEFT, 0, start_y)
        
        self.get_window(gtk.TEXT_WINDOW_LEFT).invalidate_rect((0, window_y, 10, end_y + end_height - start_y), False)
