# Copyright 2008 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

def assert_equals(result, expected):
    if result != expected:
        raise AssertionError("Got %r, expected %r" % (result, expected))
