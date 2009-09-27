# Copyright 2009 Jorn Baayen
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import gtk
import sympy
import latexmath2png
import os

from reinteract.recorded_object import RecordedObject, default_filter
import reinteract.custom_result as custom_result

class LatexMath(RecordedObject, custom_result.CustomResult):
    def __init__(self, expr):
        self.expr = expr

    def create_widget(self):
        latexmath2png.math2png([sympy.latex(self.expr, inline=False)], os.getcwd(), prefix = '/tmp/reinteract')
        widget = gtk.image_new_from_file('/tmp/reinteract1.png')
        os.remove('/tmp/reinteract1.png')
        return widget
