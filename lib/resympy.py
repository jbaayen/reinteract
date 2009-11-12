import gtk
import pango
import cairo

try:
    import lasem
except ImportError:
    raise ImportError("Could not import module 'lasem'. " \
                      "Please install pylasem from http://github.com/jbaayen/pylasem")

try:
    import sympy
except ImportError:
    raise ImportError("Could not import module 'sympy'. " \
                      "Please install sympy from http://sympy.org.")

from reinteract.custom_result import CustomResult
from replot import Axes

class SympyRenderer(gtk.EventBox):
    __gsignals__ = {
        'parent-set': 'override',
        'screen-changed' : 'override',
        'button-press-event': 'override',
        'button-release-event': 'override',
        'expose-event': 'override',
        'size-allocate': 'override',
        'unrealize': 'override'
    }

    margin_top = 3
    margin_left = 0
    margin_right = 3
    margin_bottom = 3

    def __init__(self, result):
        # Gtk widget setup.
        gtk.EventBox.__init__(self)

        self.set_visible_window(False)

        self.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK)

        self.cached_contents = None
        self.parent_style_set_id = 0
        self.notify_resolution_id = 0

        # Construct Lasem document and view.
        self.result = result
        tex = sympy.latex(self.result, inline=False, itex=True)
        self.doc = lasem.mathml_document_new_from_itex(tex, len(tex))

        self.view = self.doc.create_view()

    def do_screen_changed(self, previous_screen):
        if self.get_screen():
            self.notify_resolution_id = \
                self.get_screen().connect("notify::resolution", self._on_notify_resolution)
            self._sync_document_dpi()
        else:
            if self.notify_resolution_id > 0:
                previous_screen.handler_disconnect(self.notify_resolution_id)

    def do_parent_set(self, previous_parent):
        # We follow the parent GtkTextView text size.
        if self.parent:
            self.parent_style_set_id = \
                self.parent.connect("style-set", self._on_parent_style_set)
            self._sync_document_style()
        else:
            if self.parent_style_set_id > 0:
                previous_parent.handler_disconnect(self.parent_style_set_id)

    def _on_notify_resolution(self, screen, param_spec):
        self._sync_document_dpi()

    def _on_parent_style_set(self, widget, previous_style):
        # New GtkStyle set on parent GtkTextView.
        self.cached_contents = None

        self._sync_document_style()

        self.queue_resize()

    def _sync_document_dpi(self):
        # Set Lasem document DPI according to the current GdkScreen.
        dpi = self.get_screen().get_resolution()
        self.doc.set_resolution(dpi)

    def _sync_document_style(self):
        # Update the style of the Lasem document to match the GtkStyle of the parent GtkTextView.
        text_color = self.parent.style.text[gtk.STATE_NORMAL]
        font_desc = self.parent.style.font_desc

        root_element = self.doc.get_root_element()

        style = root_element.get_default_style()

        style.set_math_size_pt(font_desc.get_size() / pango.SCALE)
        style.set_math_family(font_desc.get_family())
        style.set_math_color(text_color.red / 65535.0, text_color.green / 65535.0, text_color.blue / 65535.0, 1.0)

        root_element.set_default_style(style)

    def do_expose_event(self, event):
        cr = self.window.cairo_create()

        if not self.cached_contents:
            self.cached_contents = cr.get_target().create_similar(cairo.CONTENT_COLOR_ALPHA,
                                                                  self.allocation.width, self.allocation.height)

            self.view.set_cairo(cairo.Context(self.cached_contents))
            self.view.render(self.margin_left, self.margin_top)

        cr.set_source_surface(self.cached_contents, self.allocation.x, self.allocation.y)
        cr.paint()

    def do_size_allocate(self, allocation):
        if allocation.width != self.allocation.width or allocation.height != self.allocation.height:
            self.cached_contents = None

        gtk.EventBox.do_size_allocate(self, allocation)

    def do_unrealize(self):
        gtk.EventBox.do_unrealize(self)

        self.cached_contents = None

    def do_button_press_event(self, event):
        if event.button == 3:
            self._show_menu(event)

        return True

    def do_button_release_event(self, event):
        return True

    def do_size_request(self, requisition):
    	requisition.width, requisition.height = self.view.get_size_pixels()
    	requisition.height += self.margin_top + self.margin_bottom
    	requisition.width += self.margin_left + self.margin_right

    def _copy_to_clipboard(self, inline):
        for selection in (gtk.gdk.SELECTION_CLIPBOARD, gtk.gdk.SELECTION_PRIMARY):
            clipboard = self.get_clipboard(selection)
            clipboard.set_text(sympy.latex(self.result, inline=inline, itex=False))

    def _show_menu(self, event):
        # Create a menu offering to copy the result to the clipboard as a LaTeX
        # string.
        menu = gtk.Menu()
        menu.attach_to_widget(self, None)

        menu_item = gtk.MenuItem(label="Copy as _LaTeX")
        menu_item.connect('activate', lambda menu : self._copy_to_clipboard(False))
        menu_item.show()
        menu.add(menu_item)

        menu_item = gtk.MenuItem(label="Copy as LaTeX (_inline)")
        menu_item.connect('activate', lambda menu : self._copy_to_clipboard(True))
        menu_item.show()
        menu.add(menu_item)

        def on_selection_done(menu):
            menu.destroy()
        menu.connect('selection-done', on_selection_done)

        menu.popup(None, None, None, event.button, event.time)

    def print_widget(self, print_context, render=True):
        # Set printer dpi.
        self.doc.set_resolution(print_context.get_dpi_x())

        # Use simple black text color.
        root_element = self.doc.get_root_element()
        style = root_element.get_default_style()
        style.set_math_color(0.0, 0.0, 0.0, 1.0)
        root_element.set_default_style(style)

        # Render to cairo context (if given).
        if render:
            cr = print_context.get_cairo_context()

            x, y = cr.get_current_point()

            self.view.set_cairo(cr)
            self.view.render(x + self.margin_left, y + self.margin_top)

        # Get dimensions.
        width, height = self.view.get_size()
        width += self.margin_left + self.margin_right
        height += self.margin_top + self.margin_bottom

        # Restore original dpi and document style.
        self._sync_document_dpi()
        self._sync_document_style()

        # Return dimensions to caller.
        return width, height

class SympyResult(CustomResult):
    def __init__(self, expr):
        self.expr = expr

    def create_widget(self):
        return SympyRenderer(self.expr)

def __reinteract_wrap__(obj):
    sympy_classes = (sympy.Basic, sympy.Matrix, sympy.SMatrix)

    if isinstance(obj, sympy_classes):
        return SympyResult(obj)
    elif isinstance(obj, (list, tuple, dict)):
        if len(obj) == 0:
            return None
        for item in obj:
            if not isinstance(item, sympy_classes):
                return None
        return SympyResult(obj)
    else:
        return None

# Add hooks for sympy plotting functions.
def plot(*args):
    axes = Axes()
    sympy.plot(*args, axes=axes)
    return axes

def cplot(*args):
    axes = Axes()
    sympy.cplot(*args, axes=axes)
    return axes
