#!/usr/bin/python

import copy
import compiler

import rewrite

_DEFINE_GLOBALS = compile("""
global reinteract_output, reinteract_print
def reinteract_output(*args):
   __reinteract_statement.do_output(*args)
def reinteract_print(*args):
   __reinteract_statement.do_print(*args)
""", __name__, 'exec')
    
class Statement:
    def __init__(self, text, parent = None):
        self.__text = text
        self.__parent = parent
        self.__result_scope = None

        if self.__parent != None:
            self.__globals = self.__parent.get_globals()
        else:
            self.__globals = { '__builtins__': __builtins__ }
            exec _DEFINE_GLOBALS in self.__globals

    def get_globals(self):
        return self.__globals

    def get_result_scope(self):
        return self.__result_scope

    def do_output(self, *args):
        if len(args) == 1 and args[0] == None:
            return
        
        if self.__result == None:
            self.__result = ""
        else:
            self.__result += "\n"
            
        if len(args) == 1:
            self.__result += repr(args[0])
        else:
            self.__result += repr(args)

    def do_print(self, *args):
        if self.__result == None:
            self.__result = ""
        else:
            self.__result += "\n"
            
        self.__result += " ".join(map(str, args))

    def eval(self):
        compiled, mutated = rewrite.rewrite_and_compile(self.__text)
        
        if self.__parent:
            scope = copy.copy(self.__parent.get_result_scope())
        else:
            scope = {}

        for mutation in mutated:
            if isinstance(mutation, tuple):
                variable, method = mutation
            else:
                variable = mutation

            scope[variable] = copy.copy(scope[variable])

        self.__result = None
        self.__globals['__reinteract_statement'] = self
        exec compiled in self.__globals, scope
        self.__globals['__reinteract_statement'] = None

        self.__result_scope = scope

        return self.__result

if __name__=='__main__':
    def expect(actual,expected):
        if actual != expected:
            raise AssertionError("Got: '%s'; Expected: '%s'" % (actual, expected))

    # A bare expression should give the repr of the expression
    expect(Statement("'a'").eval(), repr('a'))
    expect(Statement("1,2").eval(), repr((1,2)))

    # Print, on the other hand, gives the string form of the expression
    expect(Statement("print 'a'").eval(), 'a')

    # Test that we copy a variable before mutating it (when we can detect
    # the mutation)
    s1 = Statement("b = [0]")
    s1.eval()
    s2 = Statement("b[0] = 1", parent=s1)
    s2.eval()
    s3 = Statement("b[0]", parent = s2)
    expect(s3.eval(), "1")
    
    s2a = Statement("b[0]", parent=s1)
    expect(s2a.eval(), "0")
