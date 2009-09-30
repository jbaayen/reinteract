# Copyright 2009 Jorn Baayen
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import gtk
import sympy
from sympy.printing.latex import LatexPrinter
import matplotlib.texmanager as texmanager
import numpy
import gconf
import pango

import reinteract.custom_result as custom_result
import reinteract.statement as statement

class SympyLatexRenderer(custom_result.CustomResult):
    tex_manager = texmanager.TexManager()

    def __init__(self, expr):
        self.expr = expr

    def _on_parent_set(self, widget, parent):
        if widget.parent:
            widget.parent.connect("style-set", self._on_style_set)

            self._update()

    def _on_style_set(self, widget, style):
        self._update()

    def _create_pixbuf(self, font_desc, dpi, color=(0, 0, 0)):
        latex = sympy.latex(self.expr, inline=False)

        font_size = font_desc.get_size() / pango.SCALE

        rgb = (color[0] / 255.0, color[1] / 255.0, color[2] / 255.0)

        im_float = self.tex_manager.get_rgba(latex, \
                                             fontsize=font_size, \
                                             dpi=dpi, \
                                             rgb=rgb)
        im_ubyte = numpy.empty(im_float.shape, dtype=numpy.ubyte)
        for i in xrange(im_float.shape[0]):
            for j in xrange(im_float.shape[1]):
                for k in xrange(im_float.shape[2]):
                    im_ubyte[i, j, k] = round(im_float[i, j, k] * 255)

        return gtk.gdk.pixbuf_new_from_array(im_ubyte, gtk.gdk.COLORSPACE_RGB, 8)

    def _update(self):
        font_desc = self.widget.parent.style.font_desc

        client = gconf.client_get_default()
        dpi = client.get_float('/desktop/gnome/font_rendering/dpi')

        color = self.widget.parent.style.text[gtk.STATE_NORMAL]

        pixbuf = self._create_pixbuf(font_desc, \
                                     dpi, \
                                     (color.red, color.green, color.blue))

        self.widget.set_from_pixbuf(pixbuf)

    def create_widget(self):
        self.widget = gtk.Image()
        self.widget.connect('parent-set', self._on_parent_set)
        return self.widget

    @staticmethod
    def can_render_class(expr):
        for cls in type(expr).__mro__:
            printmethod = '_print_' + cls.__name__
            if hasattr(LatexPrinter, printmethod):
                return True
        return False

statement.Statement.external_renderers.append(SympyLatexRenderer)
