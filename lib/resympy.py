import gtk
import pango
import cairo
import lasem

import sympy

from reinteract.custom_result import CustomResult

class SympyRenderer(gtk.Widget):
    __gsignals__ = {
        'parent-set': 'override',
        'screen-changed' : 'override',
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
        gtk.Widget.__init__(self)

        self.set_flags(gtk.NO_WINDOW)

        self.cached_contents = None
        self.parent_style_set_id = 0

        # Construct Lasem document and view.
        # TODO use 'itex=True' here once this lands in sympy master; see
        # http://code.google.com/p/sympy/issues/detail?id=1663.
        tex = str("$%s$" % sympy.latex(result, inline=True))
        self.doc = lasem.mathml_document_new_from_itex(tex, len(tex))

        self.view = self.doc.create_view()

    def do_screen_changed(self, previous_screen):
        self._sync_document_dpi()

    def do_parent_set(self, parent):
        # We follow the parent GtkTextView text size.
        if self.parent:
            self.parent_style_set_id = \
                self.parent.connect("style-set", self._on_parent_style_set)
            self._sync_document_style()
        else:
            if self.parent_style_set_id > 0:
                parent.handler_disconnect(self.parent_style_set_id)

    def _on_parent_style_set(self, widget, style):
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

        gtk.Widget.do_size_allocate(self, allocation)

    def do_unrealize(self):
        gtk.Widget.do_unrealize(self)

        self.cached_contents = None

    def do_size_request(self, requisition):
    	requisition.width, requisition.height = self.view.get_size_pixels()
    	requisition.height += self.margin_top + self.margin_bottom
    	requisition.width += self.margin_left + self.margin_right

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

# The __bases__ trickery used below fails when a class is a direct descendent
# of object, as is sympy.Matrix.  Adding another layer solves the problem.
# However, modifying the new Matrix will not change the descendants of Matrix
# (namely SMatrix), so we'll have to get them separately.
# TODO This breaks when Matrix has been imported into other namespaces
# beforehand. See also http://bugs.python.org/issue672115 for the __bases__
# failure bug.
class Matrix(sympy.Matrix):
    pass
sympy.Matrix = Matrix
sympy.matrices.Matrix = Matrix

# Most sympy objects (that we care about) inherit from sympy.Basic.  So if we
# modify this one class, we can influence most objects at once.  Known
# exceptions: Matrix, and its erstwhile descendant SMatrix.  'Course,
# latex(SMatrix) throws a hissy fit
for cls in (sympy.Basic, sympy.Matrix, sympy.SMatrix):
    # Add CustomResult as an ancestor, so Reinteract will treat it specially.
    cls.__bases__ += (CustomResult,)
    # Provide a create_widget() method for display.
    cls.create_widget = lambda result : SympyRenderer(result)
