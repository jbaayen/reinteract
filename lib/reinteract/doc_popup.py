import doc_format
import pango
import gtk

# Space between a window the popup is "next to" and the popup
HORIZONTAL_GAP = 5

class DocPopup(gtk.Window):
    
    """Class implementing a popup showing docs about an object"""
    
    __gsignals__ = {
        'expose-event': 'override',
    }
    
    def __init__(self):
        gtk.Window.__init__(self, gtk.WINDOW_POPUP)

        self.set_default_size(300, 300)

        self.__view = gtk.TextView()
        self.__view.set_editable(False)
        self.__view.modify_font(pango.FontDescription("Sans 9"))
        self.__view.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color(0xffff, 0xffff, 0xbfbf))
        self.__view.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color(0, 0, 0))

        if False:
            sw = gtk.ScrolledWindow()
            self.add(sw)
            sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
            sw.add(self.__view)
        else:
            self.set_border_width(1)
            self.set_size_request(-1, 300)
            self.add(self.__view)
            
        buf = self.__view.get_buffer()
        self.__bold_tag = buf.create_tag(None, weight=pango.WEIGHT_BOLD)

        self.get_child().show_all()
        
        self.__target = None
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

    def set_target(self, target):
        """Set the object that the popup is showing documentation about"""
        
        if target is self.__target:
            return

        self.__target = target
        buf = self.__view.get_buffer()
        buf.delete(buf.get_start_iter(), buf.get_end_iter())

        if target != None:
            doc_format.insert_docs(buf, buf.get_start_iter(), target, self.__bold_tag)

    def position_next_to_window(self, window):
        """Position the popup so that it is immediately to the right of the specified window

        This only works properly if the window is undecorated, since we don't take the
        decorations into account.

        """
        
        x, y = window.window.get_origin()
        width, height = window.window.get_size()

        self.move(x + width + HORIZONTAL_GAP, y)
        
    def popup(self):
        """Show the popup"""
        
        if self.showing:
            return

        self.show()
        self.showing = True

    def popdown(self):
        """Hide the popup"""
        
        if not self.showing:
            return

        self.showing = False
        self.hide()
