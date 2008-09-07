#!/usr/bin/python

import copy
import sys

from custom_result import CustomResult
from notebook import HelpResult
from rewrite import Rewriter
from stdout_capture import StdoutCapture

# A wrapper so we don't have to trap all exceptions when running statement.Execute
class ExecutionError(Exception):
    def __init__(self, error_type, value, traceback):
        self.type = error_type
        self.value = value
        self.traceback = traceback

    def __str__(self):
        return "ExecutionError: " + str(self.cause)

class WarningResult(object):
    def __init__(self, message):
        self.message = message
    
class Statement:
    def __init__(self, text, worksheet, parent = None):
        self.__text = text
        self.__worksheet = worksheet
        self.result_scope = None
        self.results = None
        self.stdout_buffer = None

        self.parent_future_features = None
        self.__compiled = None
        self.set_parent(parent)

        self.__compile()

    def set_parent(self, parent):
        self.__parent = parent
        if parent:
            new_future_features = parent.future_features
        else:
            new_future_features = None

        if new_future_features != self.parent_future_features:
            self.parent_future_features = new_future_features
            if self.__compiled:
                self.__compile()

    def __compile(self):
        rewriter = Rewriter(self.__text, future_features=self.parent_future_features)
        self.imports = rewriter.get_imports()

        # May raise SyntaxError, UnsupportedSyntaxError
        self.__compiled, self.__mutated = rewriter.rewrite_and_compile(output_func_name='reinteract_output')

        self.future_features = self.parent_future_features
        if self.imports != None:
            for module, symbols in self.imports:
                if module == '__future__' and symbols != '*' and symbols[0][0] != '.':
                    merged = set()
                    if self.future_features:
                        merged.update(self.future_features)
                    merged.update((sym for sym, _ in symbols))
                    self.future_features = sorted(merged)

    def get_result_scope(self):
        return self.result_scope

    def do_output(self, *args):
        if len(args) == 1:
            arg = args[0]
            
            if args[0] == None:
                return
            elif isinstance(args[0], CustomResult) or isinstance(args[0], HelpResult):
                self.results.append(args[0])
            else:
                self.results.append(repr(args[0]))
                self.result_scope['_'] = args[0]
        else:
            self.results.append(repr(args))
            self.result_scope['_'] = args

    def do_print(self, *args):
        self.results.append(" ".join(map(str, args)))

    def stdout_write(self, str):
        if self.stdout_buffer == None:
            self.stdout_buffer = str
        else:
            self.stdout_buffer += str

        pos = 0
        while True:
            next = self.stdout_buffer.find("\n", pos)
            if next < 0:
                break
            self.results.append(self.stdout_buffer[pos:next])
            pos = next + 1
            
        if pos > 0:
            self.stdout_buffer = self.stdout_buffer[pos:]

    def execute(self):
        root_scope = self.__worksheet.global_scope
        if self.__parent:
            scope = copy.copy(self.__parent.result_scope)
        else:
            scope = copy.copy(root_scope)

        self.results = []
        self.result_scope = scope
        self.stdout_buffer = None
        
        for mutation in self.__mutated:
            if isinstance(mutation, tuple):
                variable, method = mutation
            else:
                variable = mutation

            try:
                if type(scope[variable]) != type(sys):
                    scope[variable] = copy.copy(scope[variable])
            except:
                self.results.append(WarningResult("Variable '%s' apparently modified, but can't copy it" % variable))

        root_scope['__reinteract_statement'] = self
        capture = StdoutCapture(self.stdout_write)
        capture.push()
        try:
          try:
              exec self.__compiled in scope, scope
              if self.stdout_buffer != None and self.stdout_buffer != '':
                  self.results.append(self.stdout_buffer)
          except:
              self.results = None
              self.result_scope = None
              error_type, value, traceback = sys.exc_info()
              raise ExecutionError(error_type, value, traceback)
        finally:
            root_scope['__reinteract_statement'] = None
            self.stdout_buffer = None
            capture.pop()

if __name__=='__main__':
    import stdout_capture
    from notebook import Notebook
    from worksheet import Worksheet

    stdout_capture.init()

    notebook = Notebook()
    worksheet = Worksheet(notebook)
    
    def expect(actual,expected):
        if actual != expected:
            raise AssertionError("Got: '%s'; Expected: '%s'" % (actual, expected))

    def expect_result(text, result):
        s = Statement(text, worksheet)
        s.execute()
        if isinstance(result, basestring):
            expect(s.results[0], result)
        else:
            expect(s.results, result)

    # A bare expression should give the repr of the expression
    expect_result("'a'", repr('a'))
    expect_result("1,2", repr((1,2)))

    # Print, on the other hand, gives the string form of the expression, with
    # one result object per output line
    expect_result("print 'a'", 'a')
    expect_result("print 'a', 'b'", ['a b'])
    expect_result("print 'a\\nb'", ['a','b'])

    # Test that we copy a variable before mutating it (when we can detect
    # the mutation)
    s1 = Statement("b = [0]", worksheet)
    s1.execute()
    s2 = Statement("b[0] = 1", worksheet, parent=s1)
    s2.execute()
    s3 = Statement("b[0]", worksheet, parent = s2)
    s3.execute()
    expect(s3.results[0], "1")
    
    s2a = Statement("b[0]", worksheet, parent=s1)
    s2a.execute()
    expect(s2a.results[0], "0")

    # Tests of 'from __future__ import...'
    s1 = Statement("from __future__ import division", worksheet)
    expect(s1.future_features, ['division'])
    s2 = Statement("from __future__ import with_statement", worksheet, parent=s1)
    expect(s2.future_features, ['division', 'with_statement'])

    s1 = Statement("import  __future__", worksheet) # just a normal import
    expect(s1.future_features, None)
