import pango
import gtk

import doc_format
from popup import Popup

MAX_HEIGHT=300

class DocPopup(Popup):
    
    """Class implementing a popup showing docs about an object"""
    
    __gsignals__ = {
        'size-request': 'override',
    }
    
    def __init__(self, fixed_height=False, fixed_width=False, max_height=MAX_HEIGHT):
        Popup.__init__(self)

        self.__fixed_height = fixed_height
        self.__fixed_width = fixed_width
        self.__max_height = max_height

        self.__font = pango.FontDescription("Sans 9")

        self.__view = gtk.TextView()
        self.__view.set_editable(False)
        self.__view.set_border_width(5)
        
        bg_color = gtk.gdk.Color(0xffff, 0xffff, 0xbfbf)
        self.__view.modify_base(gtk.STATE_NORMAL, bg_color)
        # The background color is used for the text view's border width
        self.__view.modify_bg(gtk.STATE_NORMAL, bg_color)
        
        self.__view.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color(0, 0, 0))
        self.__view.modify_font(self.__font)

        if False:
            sw = gtk.ScrolledWindow()
            self.add(sw)
            sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
            sw.add(self.__view)
        else:
            self.set_resizable(False)
            self.add(self.__view)
            
        buf = self.__view.get_buffer()
        self.__bold_tag = buf.create_tag(None, weight=pango.WEIGHT_BOLD)

        self.get_child().show_all()
        
        self.__target = None

    def set_target(self, target):
        """Set the object that the popup is showing documentation about"""
        
        if target is self.__target:
            return

        self.__target = target
        buf = self.__view.get_buffer()
        buf.delete(buf.get_start_iter(), buf.get_end_iter())

        if target != None:
            doc_format.insert_docs(buf, buf.get_start_iter(), target, self.__bold_tag)

    def do_size_request(self, request):
        child_width, child_height = self.child.size_request()

        bw = self.get_border_width()

        metrics = self.get_pango_context().get_metrics(self.__font)

        request.width = child_width + 2 * bw
        
        # fixed_width doesn't mean completely fixed, it means to put a floor on it so we don't bounce
        # the size too much
        if self.__fixed_width:
            request.width = max(request.width, metrics.get_approximate_char_width() * (90. / pango.SCALE))

        # We always want a maximum width so that faulty docs don't cause us to have widths many times
        # the width of the screen
        request.width = min(request.width, metrics.get_approximate_char_width() * (120. / pango.SCALE))

        if self.__fixed_height:
            request.height = self.__max_height
        else:
            request.height = child_height + 2 * bw
            if self.__max_height > 0:
                request.height = min(request.height, self.__max_height)

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
