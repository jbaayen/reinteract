import gtk
from matplotlib.figure import Figure
from matplotlib.backends.backend_cairo import RendererCairo
import numpy

from reinteract.custom_result import CustomResult

class _DummyCanvas:
    def draw_event(*args):
        pass

class PlotResult(CustomResult):
    def __init__(self, *args):
        if len(args) == 1:
            self.y = args[0]
            self.x = numpy.arange(len(self.y))
        elif len(args) == 2:
            self.x = args[0]
            self.y = args[1]

    def create_widget(self):
        return PlotWidget(self)
    
class PlotWidget(gtk.DrawingArea):
    __gsignals__ = {
        'expose-event': 'override'
    }

    def __init__(self, result):
        gtk.DrawingArea.__init__(self)
        self.figure = Figure(facecolor='white', figsize=(6,4.5))
        self.figure.set_canvas(_DummyCanvas())

        axes = self.figure.add_axes((0.05,0.05,0.9,0.9))
        axes.plot(result.x, result.y)
    
    def do_expose_event(self, event):
        cr = self.window.cairo_create()
        
        renderer = RendererCairo(self.figure.dpi)
        renderer.set_width_height(self.allocation.width, self.allocation.height)
        renderer.set_ctx_from_surface(cr.get_target())
        
        # event.region is not bound: http://bugzilla.gnome.org/show_bug.cgi?id=487158
#        gdk_context = gtk.gdk.CairoContext(renderer.ctx)
#        gdk_context.region(event.region)
#        gdk_context.clip()
        
        self.figure.draw(renderer)

    def do_size_request(self, requisition):
        requisition.width = self.figure.bbox.width()
        requisition.height = self.figure.bbox.height()

#    def do_size_allocate(self, allocation):
#        gtk.DrawingArea.do_size_allocate(self, allocation)
#        
#        dpi = self.figure.dpi.get()
#        self.figure.set_size_inches (allocation.width / dpi, allocation.height / dpi)

def plot(*args):
    return PlotResult(*args)
