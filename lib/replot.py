# Copyright 2007, 2008 Owen Taylor
# Copyright 2008 Kai Willadsen
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import cairo
import pango
import gtk
import matplotlib
from matplotlib.figure import Figure
from matplotlib.backends.backend_cairo import RendererCairo, FigureCanvasCairo
import numpy

from reinteract.recorded_object import RecordedObject, default_filter
import reinteract.custom_result as custom_result

class _PlotResultCanvas(FigureCanvasCairo):
    def draw_event(*args):
        # Since we never change anything about the figure, the only time we
        # need to redraw is in response to an expose event, which we handle
        # ourselves
        pass

class PlotWidget(gtk.DrawingArea):
    __gsignals__ = {
        'parent-set': 'override',
        'screen-changed' : 'override',
        'button-press-event': 'override',
        'button-release-event': 'override',
        'expose-event': 'override',
        'size-allocate': 'override',
        'unrealize': 'override'
    }

    def __init__(self, result):
        gtk.DrawingArea.__init__(self)
        self.figure = Figure(facecolor='white', figsize=(6,4.5))
        self.canvas = _PlotResultCanvas(self.figure)

        self.axes = self.figure.add_subplot(111)

        self.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE)

        self.cached_contents = None
        self.parent_style_set_id = 0
        self.notify_resolution_id = 0

    def do_screen_changed(self, previous_screen):
        if self.get_screen():
            self.notify_resolution_id = \
                self.get_screen().connect("notify::resolution", self._on_notify_resolution)
            self.figure.set_dpi(self.get_screen().get_resolution())
        else:
            if self.notify_resolution_id > 0:
                previous_screen.handler_disconnect(self.notify_resolution_id)

    def do_parent_set(self, previous_parent):
        # We follow the parent GtkTextView text size.
        if self.parent:
            self.parent_style_set_id = \
                self.parent.connect("style-set", self._on_parent_style_set)
            self._sync_font_size()
        else:
            if self.parent_style_set_id > 0:
                previous_parent.handler_disconnect(self.parent_style_set_id)

    def _on_notify_resolution(self, screen, param_spec):
        self.figure.set_dpi(self.get_screen().get_resolution())

    def _on_parent_style_set(self, widget, previous_style):
        # New GtkStyle set on parent GtkTextView.
        self.cached_contents = None

        self._sync_font_size()

        self.queue_resize()

    def _sync_font_size(self):
        # Use the parent GtkTextView font size in matplotlib.
        matplotlib.rcParams['font.size'] = self.parent.style.font_desc.get_size() / pango.SCALE

    def do_expose_event(self, event):
        cr = self.window.cairo_create()

        if not self.cached_contents:
            self.cached_contents = cr.get_target().create_similar(cairo.CONTENT_COLOR,
                                                                  self.allocation.width, self.allocation.height)

            renderer = RendererCairo(self.figure.dpi)
            renderer.set_width_height(self.allocation.width, self.allocation.height)
            renderer.set_ctx_from_surface(self.cached_contents)

            self.figure.draw(renderer)

        # event.region is not bound: http://bugzilla.gnome.org/show_bug.cgi?id=487158
#        gdk_context = gtk.gdk.CairoContext(renderer.ctx)
#        gdk_context.region(event.region)
#        gdk_context.clip()

        cr.set_source_surface(self.cached_contents, 0, 0)
        cr.paint()

    def do_size_allocate(self, allocation):
        if allocation.width != self.allocation.width or allocation.height != self.allocation.height:
            self.cached_contents = None

        gtk.DrawingArea.do_size_allocate(self, allocation)

    def do_unrealize(self):
        gtk.DrawingArea.do_unrealize(self)

        self.cached_contents = None

    def do_button_press_event(self, event):
        if event.button == 3:
            custom_result.show_menu(self, event, save_callback=self.__save)
            return True
        else:
            return True

    def do_button_release_event(self, event):
        return True

    def do_realize(self):
        gtk.DrawingArea.do_realize(self)
        cursor = gtk.gdk.Cursor(gtk.gdk.LEFT_PTR)
        self.window.set_cursor(cursor)

    def do_size_request(self, requisition):
        try:
            # matplotlib < 0.98
            requisition.width = self.figure.bbox.width()
            requisition.height = self.figure.bbox.height()
        except TypeError:
            # matplotlib >= 0.98
            requisition.width = self.figure.bbox.width
            requisition.height = self.figure.bbox.height


    def __save(self, filename):
        # The save/restore here was added to matplotlib's after 0.90. We duplicate
        # it for compatibility with older versions. (The code would need modification
        # for 0.98 and newer, which is the reason for the particular version in the
        # check)

        version = [int(x) for x in matplotlib.__version__.split('.')]
        need_save = version[:2] < [0, 98]
        if need_save:
            orig_dpi = self.figure.dpi.get()
            orig_facecolor = self.figure.get_facecolor()
            orig_edgecolor = self.figure.get_edgecolor()

        try:
            self.canvas.print_figure(filename)
        finally:
            if need_save:
                self.figure.dpi.set(orig_dpi)
                self.figure.set_facecolor(orig_facecolor)
                self.figure.set_edgecolor(orig_edgecolor)
                self.figure.set_canvas(self.canvas)

    def print_widget(self, print_context, render=True):
        # Set printer dpi.
        orig_dpi = self.figure.get_dpi()
        self.figure.set_dpi(print_context.get_dpi_x())

        # Don't draw the frame, please.
        self.figure.set_frameon(False)

        # Get dimensions.
        width, height = self.figure.bbox.width, self.figure.bbox.height

        # Render to cairo context (if given).
        if render:
            cr = print_context.get_cairo_context()

            cr.save()
            cr.translate(*cr.get_current_point())

            renderer = RendererCairo(self.figure.dpi)
            renderer.set_width_height(width, height)
            if hasattr(renderer, 'gc'):
                # matplotlib-0.99 and newer
                renderer.gc.ctx = cr
            else:
                # matplotlib-0.98

                # RendererCairo.new_gc() does a restore to get the context back
                # to its original state after changes
                cr.save()
                renderer.ctx = cr

            self.figure.draw(renderer)

            if not hasattr(renderer, 'gc'):
                # matplotlib-0.98
                # Reverse the save() we did before drawing
                cr.restore()

            cr.restore()

        # Restore original settings.
        self.figure.set_frameon(True)
        self.figure.set_dpi(orig_dpi)

        # Return dimensions to caller.
        return width, height

#    def do_size_allocate(self, allocation):
#        gtk.DrawingArea.do_size_allocate(self, allocation)
#
#        dpi = self.figure.dpi.get()
#        self.figure.set_size_inches (allocation.width / dpi, allocation.height / dpi)

def _validate_args(args):
    #
    # The matplotlib argument parsing is a little wonky
    #
    #  plot(x, y, 'fmt', y2)
    #  plot(x1, y2, x2, y2, 'fmt', y3)
    #
    # Are valid, but
    #
    #  plot(x, y, y2)
    #
    # is not. We just duplicate the algorithm here
    #
    l = len(args)
    i = 0
    while True:
        xi = None
        yi = None
        formati = None

        remaining = l - i
        if remaining == 0:
            break
        elif remaining == 1:
            yi = i
            i += 1
        # The 'remaining != 3 and' encapsulates the wonkyness referred to above
        elif remaining == 2 or (remaining != 3 and not isinstance(args[i + 2], basestring)):
            # plot(...., x, y [, ....])
            xi = i
            yi = i + 1
            i += 2
        else:
            # plot(....., x, y, format [, ...])
            xi = i
            yi = i + 1
            formati = i + 2
            i += 3

        if xi is not None:
            arg = args[xi]
            if isinstance(arg, numpy.ndarray):
                xshape = arg.shape
            elif isinstance(arg, list):
                # Not supporting nested python lists here
                xshape = (len(arg),)
            else:
                raise TypeError("Expected numpy array or list for argument %d" % (xi + 1))
        else:
            xshape = None

        # y isn't optional, pretend it is to preserve code symmetry

        if yi is not None:
            arg = args[yi]
            if isinstance(arg, numpy.ndarray):
                yshape = arg.shape
            elif isinstance(arg, list):
                # Not supporting nested python lists here
                yshape = (len(arg),)
            else:
                raise TypeError("Expected numpy array or list for argument %d" % (yi + 1))
        else:
            yshape = None

        if xshape is not None and yshape is not None and xshape != yshape:
            raise TypeError("Shapes of arguments %d and %d aren't compatible" % ((xi + 1), (yi + 1)))

        if formati is not None and not isinstance(args[formati], basestring):
            raise TypeError("Expected format string for argument %d" % (formati + 1))

class Axes(RecordedObject, custom_result.CustomResult):
    def _check_plot(self, name, args, kwargs, spec):
        _validate_args(args)

    def create_widget(self):
        widget = PlotWidget(self)
        self._replay(widget.axes)
        return widget

def filter_method(baseclass, name):
    if not default_filter(baseclass, name):
        return False
    if name.startswith('get_'):
        return False
    if name == 'create_widget':
        return False
    return True

Axes._set_target_class(matplotlib.axes.Axes, filter_method)


def plot(*args, **kwargs):
    axes = Axes()
    axes.plot(*args, **kwargs)
    return axes

def imshow(*args, **kwargs):
    axes = Axes()
    axes.imshow(*args, **kwargs)
    return axes
