import gtk

# Space between the line of text where the cursor is and the popup
VERTICAL_GAP = 5

# Size of the popup
WIDTH = 300
HEIGHT = 300

class CompletionPopup(gtk.Window):
    
    """Class implementing a completion popup for ShellView

    This class encapsulates the user interface logic for completion
    popups. The actual code to determine possible completions lives in
    tokenized_statement.py. 
    
    """
    
    __gsignals__ = {
        'expose-event': 'override',
    }
    
    def __init__(self, view):
        gtk.Window.__init__(self, gtk.WINDOW_POPUP)
        self.__view = view

        sw = gtk.ScrolledWindow()
        self.add(sw)

        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.set_border_width(1)
        
        self.__tree_model = gtk.ListStore(str, str)
        self.__tree = gtk.TreeView(self.__tree_model)
        self.__tree.set_headers_visible(False)
        
        cell = gtk.CellRendererText()
        column = gtk.TreeViewColumn(None, cell, text=0)
        self.__tree.append_column(column)

        sw.add(self.__tree)
        sw.show_all()

        self.set_default_size(WIDTH, HEIGHT)

        # A small amount of background shows between the scrollbar and the list;
        # which looks ugly if it is the only gray thing in the window, so change
        # the window background to white
        self.modify_bg(gtk.STATE_NORMAL, gtk.gdk.Color(65535, 65535, 65535))

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

    def __update_completions(self):
        buf = self.__view.get_buffer()

        self.__tree_model.clear()
        for display, completion in buf.find_completions():
            self.__tree_model.append([display, completion])
        
        self.__tree.set_cursor(0)

    def __update_position(self):
        buf = self.__view.get_buffer()

        insert = buf.get_iter_at_mark(buf.get_insert())

        cursor_rect = self.__view.get_iter_location(insert)
        cursor_rect.x, cursor_rect.y = self.__view.buffer_to_window_coords(gtk.TEXT_WINDOW_TEXT, cursor_rect.x, cursor_rect.y)

        window = self.__view.get_window(gtk.TEXT_WINDOW_LEFT)
        window_x, window_y = window.get_origin()
        cursor_rect.x += window_x
        cursor_rect.y += window_y
        
        x = cursor_rect.x
        y = cursor_rect.y + cursor_rect.height + VERTICAL_GAP

        # If the popup would go off the screen, pop it up above instead; should we
        # reverse the direction of the items here, as for a menu? I think that would
        # be more confusing than not doing so.
        if y + HEIGHT > window.get_screen().get_height():
            y = cursor_rect.y - VERTICAL_GAP - HEIGHT
        
        self.move(x, y)

    def __insert_selected(self):
        model, iter = self.__tree.get_selection().get_selected()
        completion = model.get_value(iter, 1)

        self.__view.get_buffer().insert_interactive_at_cursor(completion, True)
            
    def popup(self):
        """Pop up the completion popup.

        If there are no possibilities completion at the insert cursor
        location, the popup is not popped up. If there is exactly one
        possibility, then completion is done immediately to that one
        possibility.

        """
        
        if self.showing:
            return
        
        self.__update_completions()
        if len(self.__tree_model) < 2:
            if len(self.__tree_model) == 0:
                return
            self.__insert_selected()
            return
        
        self.__update_position()

        self.show()
        
        # Send a synthetic focus in so that the TreeView thinks it is
        # focused
        focus_in = gtk.gdk.Event(gtk.gdk.FOCUS_CHANGE)
        focus_in.window = self.window
        focus_in.in_ = True
        self.event(focus_in)

        self.showing = True

    def update(self):
        """Update the completion popup after the cursor is moved, or text is inserted.

        If there are no completion possibilities at the cursor when this is called,
        the popup is popped down.

        """
        
        if not self.showing:
            return
        
        self.__update_completions()
        if len(self.__tree_model) == 0:
            self.popdown()
            return
        
        self.__update_position()
        
    def popdown(self):
        """Hide the completion if it is currently showing"""

        if not self.showing:
            return
        
        self.showing = False
        self.hide()

    def on_key_press_event(self, event):
        """Do key press handling while the popup is active.

        Returns True if the key press is handled, False otherwise.

        """
        
        if event.keyval == gtk.keysyms.Escape:
            self.popdown()
            return True
        elif event.keyval in (gtk.keysyms.KP_Enter, gtk.keysyms.Return):
            self.__insert_selected()
            self.popdown()
            return True
        # These keys are forwarded to the popup to move the selected row
        elif event.keyval in (gtk.keysyms.Up, gtk.keysyms.KP_Up,
                              gtk.keysyms.Down, gtk.keysyms.KP_Down,
                              gtk.keysyms.Page_Up, gtk.keysyms.KP_Page_Up,
                              gtk.keysyms.Page_Down, gtk.keysyms.KP_Page_Down):
            self.event(event)
            return True

        return False

    
    
