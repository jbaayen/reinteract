# Copyright 2007 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################
#
# This file is about banging the IPC mechanisms of GtkTextView ... cut-and-paste,
# middle-button-paste and DND into submission. Submission here means, in particular,
# not including ResultChunk text in the result.
#
# The dependency of this on ShellView/ShellBuffer is slim ... we use a single
# method buffer.get_public_text() to get a range of text without the results.
# We also do RTTI in one case on ShellBuffer to detect cut-and-paste between
# two ShellBuffers.
#
# Ideally there would eventually be mechanisms in GtkTextBuffer to make this all
# easy... all we really want to do is provide a callback for "get IPC text", but
# it's not clear how that would interact with all the (for this useless)
# complexity that's been added there for custom serialization formats.
#

import cairo
import gtk

from shell_buffer import ShellBuffer

class _IPCSanitizer(object):
    def __init__(self, view):
        self.view = view

        self.drag_start_position = None

        view.connect('cut-clipboard', self.on_cut_clipboard)
        view.connect('copy-clipboard', self.on_copy_clipboard)

        view.connect('button-press-event', self.on_button_press_event)
        view.connect('button-release-event', self.on_button_release_event)
        view.connect('motion-notify-event', self.on_motion_notify_event)

        view.connect('drag-data-get', self.on_drag_data_get)
        
        view.connect('drag-begin', self.on_drag_begin)

    # Cut and copy are the easy parts; we just override the action signals on the view,
    # and instead of doing all the complex copy-tags, serialize, in-process-special-case, etc,
    # stuff that the
    # that the GtkTextView
        
    def on_cut_clipboard(self, view):
        view.stop_emission('cut-clipboard')

        buf = view.get_buffer()

        bounds = buf.get_selection_bounds()
        if bounds == ():
            return

        start, end = bounds
        view.get_clipboard(gtk.gdk.SELECTION_CLIPBOARD).set_text(buf.get_public_text(*bounds))
        buf.delete_interactive(start, end, view.get_editable())

    def on_copy_clipboard(self, view):
        view.stop_emission('copy-clipboard')
        
        buf = view.get_buffer()

        bounds = buf.get_selection_bounds()
        if bounds == ():
            return

        view.get_clipboard(gtk.gdk.SELECTION_CLIPBOARD).set_text(buf.get_public_text(*bounds))

    def __get_iter_at_event(self, event):
        x, y = self.view.window_to_buffer_coords(gtk.TEXT_WINDOW_TEXT, int(event.x), int(event.y))
        return self.view.get_iter_at_location(x, y)

    def on_button_press_event(self, view, event):
        if event.type != gtk.gdk.BUTTON_PRESS or event.window != self.view.get_window(gtk.TEXT_WINDOW_TEXT):
            return False
        
        if event.button == 1:
            # DND tracking. See comment in on_motion_event
            location = self.__get_iter_at_event(event)
            
            bounds = view.get_buffer().get_selection_bounds()
            if bounds != () and location.in_range(*bounds):
                self.drag_start_position = (event.x, event.y)
        elif event.button == 2:
            # The middle-button paste is the part of this that gives us the most headaches,
            # since if we stole ownership of the "PRIMARY" clipboard from the buffer, it would
            # deselect. And there's no way to intercept the request for the text of the clipboard.
            # So, we just do as well as we can and fix middle-pasting from another (or the same)
            # ShellBuffer.
            #
            clipboard = view.get_clipboard(gtk.gdk.SELECTION_PRIMARY)
            owner = clipboard.get_owner()
            
            if isinstance(owner, ShellBuffer):
                buf = view.get_buffer()
                
                bounds = owner.get_selection_bounds()
                if bounds == ():
                    return True
                
                location = self.__get_iter_at_event(event)

                buf.insert_interactive(location,
                                       owner.get_public_text(*bounds),
                                       view.get_editable())

                return True

        return False

    def on_button_release_event(self, view, event):
        if event.window != self.view.get_window(gtk.TEXT_WINDOW_TEXT):
            return False

        if event.button == 1:
            # DND tracking. See comment in on_motion_event
            self.drag_start_position = None

        return False

    def on_motion_notify_event(self, view, event):
        if event.window != self.view.get_window(gtk.TEXT_WINDOW_TEXT):
            return False

        if self.drag_start_position != None:
            # We need to call gtk_drag_begin() ourselves so that we can provide the correct
            # target list. To do that, we duplicate the drag-and-logic, and just before the
            # text view would start the drag, we jump in and do it ourselves
            #
            start_x, start_y = self.drag_start_position
            if view.drag_check_threshold(int(start_x), int(start_y), int(event.x), int(event.y)):
                buf = view.get_buffer()
                
                bounds = buf.get_selection_bounds()
        
                # Synthesize a release event so GtkTextView doesn't start dragging on it's own
                release_event = gtk.gdk.Event(gtk.gdk.BUTTON_RELEASE)
                release_event.x = start_x
                release_event.y = start_y
                release_event.button = 1
                release_event.window = event.window
                
                view.event(release_event)
                
                # but then we need to reselect, since the button release deselected
                if bounds != ():
                    buf.select_range(*bounds)

                targets = gtk.target_list_add_text_targets()
                view.drag_begin(targets, gtk.gdk.ACTION_COPY | gtk.gdk.ACTION_MOVE, 1, event)
                return True

    def on_drag_begin(self, view, context):
        # Since we are calling drag_begin ourselves, we also need to do the drag icon
        # icon creation. Well, OK, we could just go with the default drag icon....
        #
        # Since we are doing it ourselves, we take the advantage to do a bit better
        # than the standard version: we don't wrap the lines, since that is wrong for
        # code,  and (pure show-off) we fade out the text if we need to truncate it
        # The standard version goes to some effort to show both ends of the DND-region
        # which we don't try to duplicate.
        #
        MAX_WIDTH = 300
        MAX_HEIGHT = 225
        GRADIENT_SIZE = 25
        BORDER_SIZE = 5
        
        buf = view.get_buffer()
        
        bounds = buf.get_selection_bounds()
        if bounds == ():
            return

        text = buf.get_public_text(*bounds)

        layout = view.create_pango_layout(text)
        width, height = layout.get_pixel_size()

        pixmap_width = min(width, MAX_WIDTH) + BORDER_SIZE * 2 + 1 * 2
        pixmap_height = min(height, MAX_HEIGHT) + BORDER_SIZE * 2 + 1 * 2

        pixmap = gtk.gdk.Pixmap(view.get_window(gtk.TEXT_WINDOW_TEXT),
                                pixmap_width, pixmap_height)

        # White background
        cr = pixmap.cairo_create()
        cr.set_source_rgb(1., 1., 1.)
        cr.paint()

        # Black outline
        cr.set_source_rgb(0., 0., 0.,)
        cr.rectangle(0.5, 0.5, pixmap_width - 1, pixmap_height - 1)
        cr.set_line_width(1)
        cr.stroke()

        # And the text
        cr.move_to(BORDER_SIZE + 1, BORDER_SIZE + 1)
        cr.show_layout(layout)

        # Pure show-off... fade out the text if it runs out of the region
        if width > MAX_WIDTH:
            pattern = cairo.LinearGradient(pixmap_width - GRADIENT_SIZE - 1, 0, pixmap_width - 1, 0)
            pattern.add_color_stop_rgba(0., 1., 1., 1., 0.)
            pattern.add_color_stop_rgba(1., 1., 1., 1., 1.)

            cr.set_source(pattern)

            cr.rectangle(pixmap_width - GRADIENT_SIZE - 1, 1, GRADIENT_SIZE, pixmap_height - 2)
            cr.fill()

        if height > MAX_HEIGHT:
            pattern = cairo.LinearGradient(0, pixmap_height - GRADIENT_SIZE - 1, 0, pixmap_height - 1)
            pattern.add_color_stop_rgba(0., 1., 1., 1., 0.)
            pattern.add_color_stop_rgba(1., 1., 1., 1., 1.)

            cr.set_source(pattern)

            cr.rectangle(1, pixmap_height - GRADIENT_SIZE - 1, pixmap_width - 2, GRADIENT_SIZE)
            cr.fill()

        # Bug in pygtk ... it doesn't support None for the mask, so we have to create a solid mask
        #  http://bugzilla.gnome.org/show_bug.cgi?id=497781

        mask = gtk.gdk.Pixmap(view.get_window(gtk.TEXT_WINDOW_TEXT),
                              pixmap_width, pixmap_height, 1) # depth 1 == bitmap
        cr = mask.cairo_create()
        cr.set_source_rgb(1., 1., 1.)
        cr.paint()

        context.set_icon_pixmap(pixmap.get_colormap(), pixmap, mask, 0, 0)

    def on_drag_data_get(self, view, context, selection_data, info, time):
        # More straightforward than the rest of the DND handling, when drag target asks
        # for the text, just serve up the text in the selection as plain text
        #
        view.stop_emission('drag-data-get')

        buf = view.get_buffer()

        bounds = buf.get_selection_bounds()
        if bounds == ():
            return True

        selection_data.set_text(buf.get_public_text(*bounds))

def sanitize_view(view):
    # Attach our object to the view
    _IPCSanitizer(view)
