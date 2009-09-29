# Copyright 2009 Jorn Baayen
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import gtk
import sympy
from sympy.printing import mathml
from sympy.printing.mathml import MathMLPrinter
from sympy.utilities.mathml import c2p
import gtkmathview

from reinteract.recorded_object import RecordedObject, default_filter
import reinteract.custom_result as custom_result

class MathRenderer(RecordedObject, custom_result.CustomResult):
    def __init__(self, expr):
        self.expr = expr

    def create_widget(self):
		widget = gtkmathview.MathView()
		widget.load_buffer(c2p(mathml(self.expr), simple=True))
		return widget

def supports_class(expr):
    for cls in type(expr).__mro__:
        printmethod = '_print_' + cls.__name__
        if hasattr(MathMLPrinter, printmethod):
            return True
    return False
