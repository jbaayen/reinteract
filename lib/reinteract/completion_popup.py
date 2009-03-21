# Copyright 2007 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import gtk
import inspect

from popup import Popup
from doc_popup import DocPopup
from data_format import is_data_object
from shell_buffer import ADJUST_NONE

# Space between the line of text where the cursor is and the popup
VERTICAL_GAP = 5

# Size of the popup
WIDTH = 300
HEIGHT = 300

# If the user is just typing, the number of characters we require before
# we start suggesting completions
SPONTANEOUS_MIN_LENGTH = 3

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
        self.__tree.connect('row-activated', self.__on_row_activated)

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
        self.spontaneous = False
        self.showing = False

    def __update_completions(self, spontaneous=False):
        buf = self.__view.get_buffer()

        self.__in_change = True
        self.__tree_model.clear()
        line, offset = buf.iter_to_pos(buf.get_iter_at_mark(buf.get_insert()), adjust=ADJUST_NONE)
        if line == None:
            completions = []
        else:
            if spontaneous:
                min_length = SPONTANEOUS_MIN_LENGTH
            else:
                min_length = 0
            completions = buf.worksheet.find_completions(line, offset, min_length)
        for display, completion, obj in completions:
            self.__tree_model.append([display, completion, obj])

        if len(completions) > 0:
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

    def __insert_completion(self, iter):
        completion = self.__tree_model.get_value(iter, 1)
        obj = self.__tree_model.get_value(iter, 2)

        buf = self.__view.get_buffer()
        default_editable = self.__view.get_editable()

        buf.insert_interactive_at_cursor(completion, default_editable)
        if inspect.isclass(obj) or inspect.isroutine(obj):
            # Show the doc popup to give the user information about what arguments
            # are posssible/required
            self.__view.show_doc_popup()

            # Insert a () and put the cursor in the middle
            buf.insert_interactive_at_cursor('(', default_editable)
            insert = buf.get_iter_at_mark(buf.get_insert())
            mark_between_parens = buf.create_mark(None, insert, left_gravity=True)
            buf.insert_interactive_at_cursor(')', default_editable)
            iter = buf.get_iter_at_mark(mark_between_parens)
            self.__view.highlight_arg_region(iter, iter)
            buf.place_cursor(iter)
            buf.delete_mark(mark_between_parens)

    def __insert_selected(self):
        model, iter = self.__tree.get_selection().get_selected()
        self.__insert_completion(iter)
            
    def __on_selection_changed(self, selection):
        if not self.__in_change:
            self.__update_doc_popup()

    def __on_row_activated(self, view, path, column):
        self.__insert_completion(self.__tree_model.get_iter(path))
        self.popdown()

    def popup(self, spontaneous=False):
        """Pop up the completion popup.

        If there are no possibilities completion at the insert cursor
        location, the popup is not popped up. If there is exactly one
        possibility and the spontaneous parameter is not provided , then
        completion is done immediately to that one possibility.

        @param spontaneous set to True if we're popping this up as a result
           of editing, rather than because of an explicit key shortcut.

        """
        
        self.__update_completions(spontaneous=spontaneous)
        num_completions = len(self.__tree_model)
        if num_completions == 0:
            return
        elif num_completions == 1 and not spontaneous:
            self.__insert_selected()
            return
        
        self.__update_position()

        self.spontaneous = spontaneous

        if self.showing:
            return

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
        
        self.__update_completions(spontaneous=self.spontaneous)
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
