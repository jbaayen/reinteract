# Copyright 2007 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import pango
import gtk

import data_format
import doc_format
from global_settings import global_settings
from popup import Popup

MAX_HEIGHT = 300
PADDING = 5

# Size of fonts in the doc popup relative to normal application font size
FONT_SCALE = 0.9

class DocPopup(Popup):
    
    """Class implementing a popup showing docs about an object"""
    
    __gsignals__ = {
        'destroy': 'override',
        'size-request': 'override',
        'size-allocate': 'override',
        'map': 'override',
        'style-set': 'override'
    }

    #
    # There are basically three modes to the popup:
    #
    # - Enough space for the text (also used when can_focus=False)
    # - Needs vertical scrollbar, not focused (shows 'Press F2 for focus at the bottom)
    # - Needs vertical scrollbar, focused (has scrollbar)
    #
    # Trying to deal with all these different modes by using scrolled windows
    # and vboxes would make it really hard to get the details right. Instead we
    # get the ultimate control by overriding the container methods of gtk.Window
    # and doing everything ourself. See:
    #
    #  - The calls to __set_parent() in __init__
    #  - The overrides of do_map(), do_forall(), do_size_request(), do_size_allocate()
    #
    
    def __init__(self, fixed_height=False, fixed_width=False, max_height=MAX_HEIGHT, can_focus=True):
        Popup.__init__(self)

        self.__fixed_height = fixed_height
        self.__fixed_width = fixed_width
        self.__max_height = max_height
        self.__can_focus = can_focus

        self.__view = gtk.TextView()
        self.__view.set_editable(False)
        
        bg_color = gtk.gdk.Color(0xffff, 0xffff, 0xbfbf)
        self.__view.modify_base(gtk.STATE_NORMAL, bg_color)
        self.modify_bg(gtk.STATE_NORMAL, bg_color)
        
        self.__view.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color(0, 0, 0))
        self.__view.set_parent(self)
        self.__view.show()
        self.__view.grab_focus()

        self.__font_is_custom_connection = global_settings.connect('notify::doc-tooltip-font-is-custom', self.__update_font)
        self.__font_name_connection = global_settings.connect('notify::doc-tooltip-font-name', self.__update_font)
        self.__update_font()

        self.__scrollbar = gtk.VScrollbar()
        self.__scrollbar.set_parent(self)
        self.__scrollbar.show()
        self.__view.emit('set-scroll-adjustments', None, self.__scrollbar.get_adjustment())

        self.__vscrolled = False

        self.set_resizable(False)
            
        buf = self.__view.get_buffer()
        self.__bold_tag = buf.create_tag(None, weight=pango.WEIGHT_BOLD)
        self.__heading_type_tag = buf.create_tag(None, weight=pango.WEIGHT_BOLD, pixels_below_lines=5)
        self.__inline_type_tag = self.__bold_tag
        self.__value_tag = buf.create_tag(None, family="monospace")

        self.__target = None
        self.focused = False

    def __update_font(self, *args):
        if global_settings.doc_tooltip_font_is_custom:
            self.__font = pango.FontDescription(global_settings.doc_tooltip_font_name)
        else:
            self.__font = self.get_style().font_desc
            # We round the scaled font size to an integer point size, because fonts may
            # (or may not be) set up to look better at integer point sizes
            new_size = 1024 * int(FONT_SCALE * self.__font.get_size() / 1024)
            self.__font.set_size(new_size)

        self.__view.modify_font(self.__font)

    def set_target(self, target):
        """Set the object that the popup is showing documentation about"""
        
        if target is self.__target:
            return

        self.__target = target
        buf = self.__view.get_buffer()
        buf.delete(buf.get_start_iter(), buf.get_end_iter())

        if target != None:
            if data_format.is_data_object(target):
                data_format.insert_formatted(buf, buf.get_start_iter(), target, self.__heading_type_tag, self.__inline_type_tag, self.__value_tag)
            else:
                doc_format.insert_docs(buf, buf.get_start_iter(), target, self.__bold_tag)

            buf.place_cursor(buf.get_start_iter())

        self.__scrollbar.get_adjustment().set_value(0.)

    def do_destroy(self):
        global_settings.disconnect(self.__font_is_custom_connection)
        global_settings.disconnect(self.__font_name_connection)

    def do_size_request(self, request):
        view_width, view_height = self.__view.size_request()

        bw = self.get_border_width()

        request.height = view_height + 2 * (bw + PADDING)
        self.__vscrolled = self.__max_height > 0 and request.height > self.__max_height
        self.__scrollbar.set_child_visible(self.focused and self.__vscrolled)
        
        if self.__fixed_height:
            request.height = self.__max_height
        else:
            if self.__max_height > 0 and request.height > self.__max_height:
                request.height = self.__max_height

        request.width = view_width + 2 * (bw + PADDING)
        if self.focused and self.__vscrolled:
            scrollbar_width, _ = self.__scrollbar.size_request()
            request.width += scrollbar_width
        
        # fixed_width doesn't mean completely fixed, it means to put a floor on it so we don't bounce
        # the size too much
        metrics = self.get_pango_context().get_metrics(self.__font)
        if self.__fixed_width:
            request.width = max(request.width, metrics.get_approximate_char_width() * (90. / pango.SCALE))

        # We always want a maximum width so that faulty docs don't cause us to have widths many times
        # the width of the screen
        request.width = min(request.width, metrics.get_approximate_char_width() * (120. / pango.SCALE))

    def __create_f2_layout(self):
        return self.create_pango_layout("Press 'F2' for focus")

    def do_size_allocate(self, allocation):
        self.allocation = allocation

        if self.focused and self.__vscrolled:
            scrollbar_width, _ = self.__scrollbar.size_request()
        else:
            scrollbar_width = 0
        
        bw = self.get_border_width()

        child_allocation = gtk.gdk.Rectangle()
        child_allocation.x = bw + PADDING
        child_allocation.width = allocation.width - 2 * (bw + PADDING) - scrollbar_width

        if self.__vscrolled and self.__can_focus:
            if not self.focused:
                layout = self.__create_f2_layout()
                _, height = layout.get_pixel_size()
                child_allocation.y = bw + PADDING
                child_allocation.height = allocation.height - 2 * bw - PADDING - height
            else:
                child_allocation.y = bw
                child_allocation.height = allocation.height - 2 * bw
        else:
            child_allocation.y = bw + PADDING
            child_allocation.height = allocation.height - 2 * (bw + PADDING)

        self.__view.size_allocate(child_allocation)

        if self.focused and self.__vscrolled:
            child_allocation.x = allocation.width - scrollbar_width - 1
            child_allocation.y = 1
            child_allocation.width = scrollbar_width
            child_allocation.height = allocation.height - 2
            self.__scrollbar.size_allocate(child_allocation)

    def do_expose_event(self, event):
        Popup.do_expose_event(self, event)
        if self.__can_focus and not self.focused and self.__vscrolled:
            layout = self.__create_f2_layout()
            width, height = layout.get_pixel_size()
            cr = event.window.cairo_create()
            cr.set_source_rgb(0., 0., 0.)
            cr.rectangle(0, self.allocation.height - height, self.allocation.width, 1)
            cr.fill()
            cr.move_to(self.allocation.width - width - 5, self.allocation.height - height)
            cr.show_layout(layout)

    def do_forall(self, include_internals, func, data):
        if include_internals:
            func(self.__view, data)
            func(self.__scrollbar, data)

    def do_map(self):
        Popup.do_map(self)
        
        self.__view.map()
        if self.focused and self.__vscrolled:
            self.__scrollbar.map()

    def do_style_set(self, old_style):
        # Calling update_font() from the ::style-set handler on the view would
        # trigger an infinite loop, but it's fine to do it from the handler on
        # the toplevel window
        self.__update_font()

    def __show(self, focus):
        if self.showing:
            if focus:
                self.focus()
            return

        # We want to avoid:
        #
        #  - get the size for the popup without validating the TextView
        #  - allocate at that size, queuing a resize because the
        #    gtk_text_view_size_allocate() flushes the "first validate idle"
        #  - popup small
        #  - resize larger
        #
        # So before we show the popup at all, we allocate the TextView
        # at a large size so it can figure out how big it really wants
        # to be, and queue a resize at that size. Then we go ahead and
        # show the window.
        self.__view.size_request()
        self.__view.size_allocate(gtk.gdk.Rectangle(0, 0, 10000, 1000))
        self.__view.queue_resize()

        if focus:
            # changing the focus state can change our requisition by showing
            # the scrollbar. We set the focused flag first so we show at the
            # right size.
            self.focused = True
            self.queue_resize()
        self.show()
        if focus:
            self.focus()
        self.showing = True

    def popup(self):
        """Show the popup"""

        self.__show(focus=False)

    def popup_focused(self):
        """Show the popup initially focused"""

        self.__show(focus=True)

    def popdown(self):
        """Hide the popup"""
        
        if not self.showing:
            return

        self.showing = False
        if self.focused:
            self.focused = False
            self.queue_resize()
        self.hide()

    def focus(self):
        assert self.__can_focus

        Popup.focus(self)
        if self.showing:
            self.queue_resize()

    def on_key_press_event(self, event):
        """Do key press handling while the popup is focused.

        Returns True if the key press is handled, False otherwise.

        """

        if event.keyval == gtk.keysyms.Escape:
            self.popdown()
            return True
        else:
            return self.event(event)

if __name__ == "__main__": # INTERACTIVE
    import re
    
    popup = DocPopup()
    popup.set_target(re)
    popup.popup()

    popup = DocPopup()
    popup.set_target(re)
    popup.move(0, 325)
    popup.popup_focused()
    
    popup = DocPopup(can_focus=False)
    popup.set_target(re)
    popup.move(0, 650)
    popup.popup()
    
    popup = DocPopup()
    popup.set_target(range(200))
    popup.move(500, 0)
    popup.popup_focused()
    
    gtk.main()
