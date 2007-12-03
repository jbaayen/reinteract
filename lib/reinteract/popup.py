import gtk

# Space between a window the popup is "next to" and the popup
HORIZONTAL_GAP = 5

# Space between the line of text where the cursor is and the popup
VERTICAL_GAP = 5

class Popup(gtk.Window):
    
    """Base class for various popups"""
    
    __gsignals__ = {
        'expose-event': 'override',
    }
    
    def __init__(self):
        gtk.Window.__init__(self, gtk.WINDOW_POPUP)
        self.set_border_width(1)

        self.showing = False

    def do_expose_event(self, event):
        gtk.Window.do_expose_event(self, event)

        # Draw a black rectangle around the popup
        cr = event.window.cairo_create()
        cr.set_line_width(1)
        cr.set_source_rgb(0., 0., 0.)
        cr.rectangle(0.5, 0.5, self.allocation.width - 1, self.allocation.height - 1)
        cr.stroke()
        
        return False

    def position_at_location(self, view, location):
        """Position the popup relative to a location within a gtk.TextView"""
        
        buf = view.get_buffer()

        cursor_rect = view.get_iter_location(location)
        cursor_rect.x, cursor_rect.y = view.buffer_to_window_coords(gtk.TEXT_WINDOW_TEXT, cursor_rect.x, cursor_rect.y)

        window = view.get_window(gtk.TEXT_WINDOW_TEXT)
        window_x, window_y = window.get_origin()
        cursor_rect.x += window_x
        cursor_rect.y += window_y
        
        x = cursor_rect.x
        y = cursor_rect.y + cursor_rect.height + VERTICAL_GAP

        _, height = self.get_size_request()

        # If the popup would go off the screen, pop it up above instead; should we
        # reverse the direction of the items here, as for a menu? I think that would
        # be more confusing than not doing so.
        if y + height > window.get_screen().get_height():
            y = cursor_rect.y - VERTICAL_GAP - height

        # If we are already showing, at the right vertical position, move to the left
        # if necessary, but not to the right. This behavior is desirable for
        # the completion popup as we type extra characters
        if self.showing:
            old_x, old_y = self.window.get_position()
            if y == old_y or x >= old_x:
                return
        self.move(x, y)

    def position_next_to_window(self, window):
        """Position the popup so that it is immediately to the right of the specified window

        This only works properly if the window is undecorated, since we don't take the
        decorations into account.

        """
        
        x, y = window.window.get_origin()
        width, height = window.window.get_size()

        self.move(x + width + HORIZONTAL_GAP, y)


    
