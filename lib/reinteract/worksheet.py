import copy
import sys

_DEFINE_GLOBALS = compile("""
global reinteract_output, reinteract_print
def reinteract_output(*args):
   __reinteract_statement.do_output(*args)
def reinteract_print(*args):
   __reinteract_statement.do_print(*args)
""", __name__, 'exec')

class Worksheet:
    def __init__(self, notebook):
        builtins = copy.copy(__builtins__)
        builtins['__import__'] = notebook.do_import
        
        self.global_scope = { '__builtins__': builtins }
        exec _DEFINE_GLOBALS in self.global_scope

    def do_import(self, name, globals, locals, fromlist, level):
        __import__(self, name, globals, locals, fromlist, level)

