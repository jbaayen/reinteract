# Copyright 2008 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import logging
import subprocess

# Intentionally don't use "utils" here to get meaningful messages
_logger = logging.getLogger("builder")

def check_call(args):
    """Log the command then call subprocess.check_call()"""
    _logger.info("%s", subprocess.list2cmdline(args))
    subprocess.check_call(args)
