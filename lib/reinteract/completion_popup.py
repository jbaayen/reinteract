import gtk

from popup import Popup
from doc_popup import DocPopup
from data_format import is_data_object
from shell_buffer import ADJUST_NONE

# Space between the line of text where the cursor is and the popup
VERTICAL_GAP = 5

# Size of the popup
WIDTH = 300
HEIGHT = 300

class CompletionPopup(Popup):
    
    """Class implementing a completion popup for ShellView

    This class encapsulates the user interface logic for completion
    popups. The actual code to determine possible completions lives in
    tokenized_statement.py. 
    
    """
    
    def __init__(self, view):
        Popup.__init__(self)
        self.set_size_request(WIDTH, HEIGHT)
        
        self.__view = view

        sw = gtk.ScrolledWindow()
        self.add(sw)

        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        
        self.__tree_model = gtk.ListStore(str, str, object)
        self.__tree = gtk.TreeView(self.__tree_model)
        self.__tree.set_headers_visible(False)
        
        self.__tree.get_selection().connect('changed', self.__on_selection_changed)

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

        self.__doc_popup= DocPopup(fixed_width=True, fixed_height=True, max_height=HEIGHT, can_focus=False)

        self._in_change = False
        self.showing = False

    def __update_completions(self):
        buf = self.__view.get_buffer()

        self.__in_change = True
        self.__tree_model.clear()
        line, offset = buf.iter_to_pos(buf.get_iter_at_mark(buf.get_insert()), adjust=ADJUST_NONE)
        if line == None:
            completions = []
        else:
            completions = buf.worksheet.find_completions(line, offset)
        for display, completion, obj in completions:
            self.__tree_model.append([display, completion, obj])
        
        self.__tree.set_cursor(0)
        self.__in_change = False
        self.__update_doc_popup()

    def __update_position(self):
        buf = self.__view.get_buffer()
        
        self.position_at_location(self.__view,
                                  buf.get_iter_at_mark(buf.get_insert()))

    def __update_doc_popup(self):
        if not self.showing:
            self.__doc_popup.popdown()
            return

        model, iter = self.__tree.get_selection().get_selected()
        if not iter:
            self.__doc_popup.popdown()
            return

        obj = model.get_value(iter, 2)

        # Long term it would be nice to preview the value of the
        # object, but it's distracting to show the class docs on int
        # for every integer constant, etc, which is what the DocPopup
        # does currently.
        if (obj == None or is_data_object(obj)):
            self.__doc_popup.popdown()
            return
        
        self.__doc_popup.set_target(obj)
        self.__doc_popup.popup()

    def __insert_selected(self):
        model, iter = self.__tree.get_selection().get_selected()
        completion = model.get_value(iter, 1)

        self.__view.get_buffer().insert_interactive_at_cursor(completion, True)
            
    def __on_selection_changed(self, selection):
        if not self.__in_change:
            self.__update_doc_popup()
        
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
        self.showing = True

        self.__doc_popup.position_next_to_window(self)
        self.__update_doc_popup()

        self.focus()

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
        self.focused = False
        
        if self.__doc_popup.showing:
            self.__doc_popup.popdown()
        
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
