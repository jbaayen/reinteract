# Copyright 2009 Jorn Baayen
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import gtk
from sympy import latex
from sympy.printing.latex import LatexPrinter
import latexmath2png
import os

import reinteract.custom_result as custom_result
import reinteract.statement as statement

class SympyLatexRenderer(custom_result.CustomResult):
    def __init__(self, expr):
        self.expr = expr

    def create_widget(self):
        latexmath2png.math2png([latex(self.expr, inline=False)], os.getcwd(), prefix = '/tmp/reinteract')
        widget = gtk.image_new_from_file('/tmp/reinteract1.png')
        os.remove('/tmp/reinteract1.png')
        return widget

    @staticmethod
    def can_render_class(expr):
        for cls in type(expr).__mro__:
            printmethod = '_print_' + cls.__name__
            if hasattr(LatexPrinter, printmethod):
                return True
        return False

statement.Statement.external_renderers.append(SympyLatexRenderer)
