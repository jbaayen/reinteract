# Copyright 2007 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import gtk
from ctypes import *

# This works around a hole in the pygtk API, see:
#
#  http://bugzilla.gnome.org/show_bug.cgi?id=481715
#
# In theory, it's relatively robust against different architectures,
# and even the more probable changes between GTK+/pygtk/Python versions,
# but there's a lot that could go wrong.

class _GtkTextIter(Structure):
    _fields_ = [ ("dummy1",  c_void_p),
                 ("dummy2",  c_void_p),
                 ("dummy3",  c_int),
                 ("dummy4",  c_int),                 
                 ("dummy5",  c_int),                 
                 ("dummy6",  c_int),                 
                 ("dummy7",  c_int),
                 ("dummy8",  c_int),
                 ("dummy9",  c_void_p),
                 ("dummy10", c_void_p),
                 ("dummy11", c_int),
                 ("dummy12", c_int),
                 ("dummy13", c_int),
                 ("dummy14", c_void_p) ]

class _PyGBoxed_TextIter(Structure):
    _fields_ = [ ("PyObject_HEAD", c_byte * object.__basicsize__),
                 ("boxed", POINTER(_GtkTextIter) ) ]

def iter_copy_from(iter, other):
    iter_ctypes = _PyGBoxed_TextIter.from_address(id(iter)).boxed.contents
    other_ctypes = _PyGBoxed_TextIter.from_address(id(other)).boxed.contents

    for name, type in iter_ctypes._fields_:
        iter_ctypes.__setattr__(name, other_ctypes.__getattribute__(name))
