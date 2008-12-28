# Copyright 2007, 2008 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import parser
import token
import symbol
import sys

class UnsupportedSyntaxError(Exception):
    """Exception thrown when some type of Python code that we can't support was used"""
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class _RewriteState(object):
    def __init__(self, output_func_name=None, print_func_name=None, future_features=None):
        self.mutated = []
        self.output_func_name = output_func_name
        self.print_func_name = print_func_name
        self.future_features = future_features

    def add_mutated(self, method_spec):
        if not method_spec in self.mutated:
            self.mutated.append(method_spec)

def _do_match(t, pattern):
    # Match an AST tree against a pattern. Along with symbol/token names, patterns
    # can contain strings:
    #
    #  '': ignore the matched item
    #  'name': store the matched item into the result dict under 'name'
    #  '*': matches items to the end of the sequence; ignore matched items
    #  '*name': matches items to the end of the sequence; store the matched items as a sequence into the result dict
    #
    # Things following '*" like ((token.LPAR, ''), '*', (token.RPAR, '')) are not currently
    # supported, but could be if needed
    #
    # Returns None if nothing matched or a dict of key/value pairs
    #
    if (t[0] != pattern[0]):
        return None
    
    result = {}
    for i in (xrange(1, len(pattern))):
        if i >= len(t):
            return None
        if isinstance(pattern[i], tuple):
            subresult = _do_match(t[i], pattern[i])
            if subresult == None:
                return None
            result.update(subresult)
        else:
            if pattern[i] == '':
                pass
            elif pattern[i][0] == '*':
                if pattern[i] != '*':
                    result[pattern[i][1:]] = t[i:]
            else:
                result[pattern[i]] = t[i]

    return result

_method_call_pattern = \
                     (symbol.test,
                      (symbol.or_test,
                       (symbol.and_test,
                        (symbol.not_test,
                         (symbol.comparison,
                          (symbol.expr,
                           (symbol.xor_expr,
                            (symbol.and_expr,
                             (symbol.shift_expr,
                              (symbol.arith_expr,
                               (symbol.term,
                                (symbol.factor,

                                 (symbol.power,
                                  (symbol.atom,
                                   (token.NAME, 'variable')),
                                  (symbol.trailer,
                                   (token.DOT, ''),
                                   (token.NAME, 'method')),
                                  (symbol.trailer,
                                   (token.LPAR, ''),
                                   '*'))))))))))))))

def _is_test_method_call(t):
    # Check if the given AST is a "test" of the form 'v.m()' If it
    # matches, returns { 'variable': 'v', "method": m }, otherwise returns None
    args = _do_match(t, _method_call_pattern)
    if args == None:
        return None
    else:
        return args['variable'], args['method']

_attribute_pattern = \
                     (symbol.test,
                      (symbol.or_test,
                       (symbol.and_test,
                        (symbol.not_test,
                         (symbol.comparison,
                          (symbol.expr,
                           (symbol.xor_expr,
                            (symbol.and_expr,
                             (symbol.shift_expr,
                              (symbol.arith_expr,
                               (symbol.term,
                                (symbol.factor,

                                 (symbol.power,
                                  (symbol.atom,
                                   (token.NAME, 'variable')),
                                  (symbol.trailer,
                                   (token.DOT, ''),
                                   (token.NAME, '')))))))))))))))
    
    
def _is_test_attribute(t):
    # Check if the given AST is a attribute of the form 'v.a' If it
    # matches, returns v, otherwise returns None
    args = _do_match(t, _attribute_pattern)
    
    if args == None:
        return None
    else:
        return args['variable']

_slice_pattern = \
                     (symbol.test,
                      (symbol.or_test,
                       (symbol.and_test,
                        (symbol.not_test,
                         (symbol.comparison,
                          (symbol.expr,
                           (symbol.xor_expr,
                            (symbol.and_expr,
                             (symbol.shift_expr,
                              (symbol.arith_expr,
                               (symbol.term,
                                (symbol.factor,

                                 (symbol.power,
                                  (symbol.atom,
                                   (token.NAME, 'variable')),
                                  (symbol.trailer,
                                   (token.LSQB, ''),
                                   '*'))))))))))))))
    


def _is_test_slice(t):
    # Check if the given AST is a "test" of the form 'v[...]' If it
    # matches, returns v, otherwise returns None
    args = _do_match(t, _slice_pattern)

    if args == None:
        return None
    else:
        return args['variable']

def _do_create_funccall_expr_stmt(name, trailer):
    return (symbol.expr_stmt,
            (symbol.testlist,
             (symbol.test,
              (symbol.or_test,
               (symbol.and_test,
                (symbol.not_test,
                 (symbol.comparison,
                  (symbol.expr,
                   (symbol.xor_expr,
                    (symbol.and_expr,
                     (symbol.shift_expr,
                      (symbol.arith_expr,
                       (symbol.term,
                        (symbol.factor,
                         (symbol.power,
                          (symbol.atom,
                           (token.NAME, name)),
                          trailer)))))))))))))))
    
def _create_funccall_expr_stmt(name, args):
    # Creates an 'expr_stmt' that calls a function. args is a list of
    # "test" AST's to pass as arguments to the function
    if len(args) == 0:
        trailer = (symbol.trailer,
                   (token.LPAR, '('),
                   (token.RPAR, ')'))
    else:
        arglist = [ symbol.arglist ]
        for a in args:
            if len(arglist) > 1:
                arglist.append((token.COMMA, ','))
            arglist.append((symbol.argument, a))
                
        trailer = (symbol.trailer,
                   (token.LPAR, ')'),
                   arglist,
                   (token.RPAR, ')'))

    return _do_create_funccall_expr_stmt(name, trailer)

def _rewrite_tree(t, state, actions):
    # Generic rewriting of an AST, actions is a map of symbol/token type to function
    # to call to produce a modified version of the the subtree
    result = t
    for i in xrange(1, len(t)):
        subnode = t[i]
        subtype = subnode[0]
        if actions.has_key(subtype):
            filtered = actions[subtype](subnode, state)
            if filtered != subnode:
                if result is t:
                    result = list(t)
                result[i] = filtered
                
    return result
        
def _rewrite_expr_stmt(t, state):
    # expr_stmt: testlist (augassign (yield_expr|testlist) |
    #                      ('=' (yield_expr|testlist))*)
    
    assert(t[0] == symbol.expr_stmt)
    assert(t[1][0] == symbol.testlist)
    
    if len(t) == 2:
        # testlist
        subnode = t[1]
        for i in xrange(1, len(subnode)):
            subsubnode = subnode[i]
            if subsubnode[0] == symbol.test:
                method_spec = _is_test_method_call(subsubnode)
                if (method_spec != None):
                    state.add_mutated(method_spec)

        if state.output_func_name != None:
            return _create_funccall_expr_stmt(state.output_func_name, filter(lambda x: type(x) != int and x[0] == symbol.test, subnode))
        else:
            return t
    else:
        if (t[2][0] == symbol.augassign):
            # testlist augassign (yield_expr|testlist)
            subnode = t[1]
            assert(len(subnode) == 2) # can only augassign one thing, despite the grammar
            
            variable = _is_test_slice(subnode[1])
            if variable == None:
                variable = _is_test_attribute(subnode[1])
            
            if variable != None:
                state.add_mutated(variable)
        else:
            # testlist ('=' (yield_expr|testlist))+
            for i in xrange(1, len(t) - 1):
                if (t[i + 1][0] == token.EQUAL):
                    subnode = t[i]
                    assert(subnode[0] == symbol.testlist)
                    for j in xrange(1, len(subnode)):
                        subsubnode = subnode[j]
                        if subsubnode[0] == symbol.test:
                            variable = _is_test_slice(subsubnode)
                            if variable == None:
                                variable = _is_test_attribute(subnode[1])
                                
                            if variable != None:
                                state.add_mutated(variable)
        return t

def _rewrite_print_stmt(t, state):
    # print_stmt: 'print' ( [ test (',' test)* [','] ] |
    #                       '>>' test [ (',' test)+ [','] ] )
    if state.print_func_name !=None and t[2][0] == symbol.test:
        return _create_funccall_expr_stmt(state.print_func_name, filter(lambda x: type(x) != int and x[0] == symbol.test, t))
    else:
        return t

def _rewrite_global_stmt(t, state):
    raise UnsupportedSyntaxError("The global statement is not supported")
    
def _rewrite_small_stmt(t, state):
    # small_stmt: (expr_stmt | print_stmt  | del_stmt | pass_stmt | flow_stmt |
    #              import_stmt | global_stmt | exec_stmt | assert_return)
    return _rewrite_tree(t, state,
                         { symbol.expr_stmt:  _rewrite_expr_stmt,
                           symbol.print_stmt: _rewrite_print_stmt,
                           symbol.global_stmt: _rewrite_global_stmt })

    # Future special handling: import_stmt
    # Not valid: flow_stmt, global_stmt

def _rewrite_simple_stmt(t, state):
    # simple_stmt: small_stmt (';' small_stmt)* [';'] NEWLINE
    return _rewrite_tree(t, state,
                         { symbol.small_stmt: _rewrite_small_stmt })

def _rewrite_suite(t, state):
    # suite: simple_stmt | NEWLINE INDENT stmt+ DEDENT
    return _rewrite_tree(t, state,
                         { symbol.simple_stmt: _rewrite_simple_stmt,
                           symbol.stmt:        _rewrite_stmt })

def _rewrite_block_stmt(t, state):
    return _rewrite_tree(t, state,
                         { symbol.suite:      _rewrite_suite })

_rewrite_compound_stmt_actions = {
    symbol.if_stmt:    _rewrite_block_stmt,
    symbol.while_stmt: _rewrite_block_stmt,
    symbol.for_stmt:   _rewrite_block_stmt,
    symbol.try_stmt:   _rewrite_block_stmt,
    symbol.funcdef:    _rewrite_block_stmt,
    symbol.with_stmt:  _rewrite_block_stmt
}

def _rewrite_compound_stmt(t, state):
    # compound_stmt: if_stmt | while_stmt | for_stmt | try_stmt | with_stmt | funcdef | classdef
    return _rewrite_tree(t, state, _rewrite_compound_stmt_actions)

def _rewrite_stmt(t, state):
    # stmt: simple_stmt | compound_stmt
    return _rewrite_tree(t, state,
                         { symbol.simple_stmt:   _rewrite_simple_stmt,
                           symbol.compound_stmt: _rewrite_compound_stmt })

def _create_future_import_statement(future_features):
    import_as_names = [symbol.import_as_names]
    for feature in future_features:
        if len(import_as_names) > 1:
            import_as_names.append((token.COMMA, ','))
        import_as_names.append((symbol.import_as_name,
                                (token.NAME, feature)))

    return (symbol.stmt,
            (symbol.simple_stmt,
             (symbol.small_stmt,
              (symbol.import_stmt,
               (symbol.import_from,
                (token.NAME,
                 'from'),
                (symbol.dotted_name,
                 (token.NAME,
                  '__future__')),
                (token.NAME,
                 'import'),
                import_as_names))),
             (token.NEWLINE, '')))

def _rewrite_file_input(t, state):
    # file_input: (NEWLINE | stmt)* ENDMARKER
    if state.future_features:
        # Ideally, we'd be able to pass in flags to the AST.compile() operation as we can with the
        # builtin compile() function. Lacking that ability, we just munge an import statement into
        # the start of the syntax tree
        return ((symbol.file_input, _create_future_import_statement(state.future_features)) +
                tuple((_rewrite_stmt(x, state) if x[0] == symbol.stmt else x) for x in t[1:]))
        
    else:
        return _rewrite_tree(t, state, { symbol.stmt: _rewrite_stmt })

######################################################################
# Import procesing

# dotted_name: NAME ('.' NAME)*
def _process_dotted_name(t):
    assert t[0] == symbol.dotted_name
    joined = "".join((t[i][1] for i in xrange(1, len(t))))
    basename = t[-1][1]

    return joined, basename

# dotted_as_name: dotted_name [('as' | NAME) NAME]
def _process_dotted_as_name(t):
    assert t[0] == symbol.dotted_as_name
    name, basename = _process_dotted_name(t[1])
    if len(t) == 2:
        as_name = basename
    else:
        assert len(t) == 4
        assert t[2] == (token.NAME, 'as')
        as_name = t[3][1]

    return (name, [( '.', as_name )])

# dotted_as_names: dotted_as_name (',' dotted_as_name)*
def _process_dotted_as_names(t):
    assert t[0] == symbol.dotted_as_names
    result = []
    for i in xrange(1, len(t)):
        if t[i][0] == token.COMMA:
            continue
        result.append(_process_dotted_as_name(t[i]))

    return result

# import_name: 'import' dotted_as_names
def _process_import_name(t):
    assert t[0] == symbol.import_name
    assert t[1] == (token.NAME, 'import')
    return _process_dotted_as_names(t[2])

# import_as_name: NAME [('as' | NAME) NAME]
def _process_import_as_name(t):
    assert t[0] == symbol.import_as_name
    assert t[1][0] == token.NAME
    if len(t) == 2:
        return (t[1][1], t[1][1])
    else:
        assert len(t) == 4
        assert t[3][0] == token.NAME
        return (t[1][1], t[3][1])

# import_as_names: import_as_name (',' import_as_name)* [',']
def _process_import_as_names(t):
    assert t[0] == symbol.import_as_names
    result = []
    for i in xrange(1, len(t)):
        if t[i][0] == token.COMMA:
            continue
        sym, as_name = _process_import_as_name(t[i])
        result.append((sym, as_name))

    return result

# import_from: ('from' ('.'* dotted_name | '.'+)
#                            'import' ('*' | '(' import_as_names ')' | import_as_names))
def _process_import_from(t):
    assert t[0] == symbol.import_from
    assert t[1] == (token.NAME, 'from')
    name = ""
    i = 2
    while t[i][0] == token.DOT:
        name += "."
        i += 1
    if t[i][0] == symbol.dotted_name:
        joined, _ = _process_dotted_name(t[i])
        name += joined
        i += 1
    assert t[i] == (token.NAME, 'import')
    i += 1
    if t[i][0] == token.STAR:
        import_map = '*'
    elif t[i][0] == token.LPAR:
        import_map = _process_import_as_names(t[i + 1])
        assert t[i + 2][0] == token.RPAR
    else:
        import_map = _process_import_as_names(t[i])

    return [(name, import_map)]

_import_pattern = \
    (symbol.file_input,
     (symbol.stmt,
      (symbol.simple_stmt,
       (symbol.small_stmt,
        (symbol.import_stmt,
         'imp')),
       '*')),
      '*')

# import_stmt: import_name | import_from
def _get_imports(t):
    args = _do_match(t, _import_pattern)
    if args:
        imp = args['imp']
        if imp[0] == symbol.import_name:
            return _process_import_name(imp)
        else:
            assert imp[0] == symbol.import_from
            return _process_import_from(imp)
    else:
        return None

######################################################################

class Rewriter:
    """Class to rewrite and extract information from Python code"""

    def __init__(self, code, encoding="utf8", future_features=None):
        """Initialize the Rewriter object

        @param code: the text to compile
        @param encoding: the encoding of the text
        @param future_features: a list of names from the __future__ module

        """
        if (isinstance(code, unicode)):
            code = code.encode("utf8")
            encoding = "utf8"

        self.code = code
        self.encoding = encoding
        self.future_features = future_features
        self.original = parser.suite(code).totuple()

    def get_imports(self):
        """
        Return information about any imports made by the statement

        @returns: A list of tuples, which each tuple is either (module_name, '*'),
          (module_name, [('.', as_name)]), or (module_name, [(name, as_name), ...]).

        """

        return _get_imports(self.original)

    def rewrite_and_compile(self, output_func_name=None, print_func_name=None):
        """
        Compiles the parse tree into code, while rewriting the parse tree according to the
        output_func_name and print_func_name arguments.

        At the same time, the code is scanned for possible mutations, and a list is returned.
        In the list:

         - A string indicates the mutation of a variable by assignment to a slice of it,
           or to an attribute.

         - A tuple of (variable_name, method_name) indicates the invocation of a method
           on the variable; this will sometimes be a mutation (e.g., list.append(value)),
           and sometimes not.

        @param output_func_name: the name of function used to wrap statements that are simply expressions.
           (More than one argument will be passed if the statement is in the form of a list.)
           Can be None.

        @param print_func_name: the name of a function used to replace print statements without a destination
          file. Can be None.

        @returns: a tuple of the compiled code followed by a list of mutations
        """
        state = _RewriteState(output_func_name=output_func_name,
                              print_func_name=print_func_name,
                              future_features=self.future_features)

        rewritten = _rewrite_file_input(self.original, state)
        encoded = (symbol.encoding_decl, rewritten, self.encoding)
        try:
            compiled = parser.sequence2ast(encoded).compile()
        except parser.ParserError, e:
            if "Illegal number of children for try/finally node" in e.message:
                raise UnsupportedSyntaxError("try/except/finally not supported due to Python issue 4529")
            else:
                raise UnsupportedSyntaxError("Unexpected parser error: " + e.message);

        return (compiled, state.mutated)

##################################################3

if __name__ == '__main__':
    def rewrite_and_compile(code, output_func_name=None, future_features=None, print_func_name=None, encoding="utf8"):
        return Rewriter(code, encoding, future_features).rewrite_and_compile(output_func_name, print_func_name)

    def create_file_input(s):
        # Wrap up a statement (like an expr_stmt) into a file_input, so we can
        # parse/compile it
        return (symbol.file_input,
                (symbol.stmt,
                 (symbol.simple_stmt,
                  (symbol.small_stmt, s),
                  (token.NEWLINE, '\n'))),
                (token.ENDMARKER, '\n'))

    def create_constant_test(c):
        # Create a test symbol which is a constant number
        return (symbol.test,
                (symbol.or_test,
                 (symbol.and_test,
                  (symbol.not_test,
                   (symbol.comparison,
                    (symbol.expr,
                     (symbol.xor_expr,
                      (symbol.and_expr,
                       (symbol.shift_expr,
                        (symbol.arith_expr,
                         (symbol.term,
                          (symbol.factor,
                           (symbol.power,
                            (symbol.atom,
                             (token.NUMBER, str(c))))))))))))))))
            

    #
    # Test _create_funccall_expr_stmt
    # 

    def test_funccall(args):
        t = create_file_input(_create_funccall_expr_stmt('set_test_args',
                                                         map(lambda c: create_constant_test(c), args)))
        test_args = [ 'UNSET' ]
        def set_test_args(*args): test_args[:] = args
        scope = { 'set_test_args': set_test_args }
        
        exec parser.sequence2ast(t).compile() in scope
        assert tuple(test_args) == args

    test_funccall(())
    test_funccall((1,))
    test_funccall((1,2))

    #
    # Test that our intercepting of bare expressions to save the output works
    #
    def test_output(code, expected):
        compiled, _ = rewrite_and_compile(code, output_func_name='reinteract_output')
        
        test_args = []
        def set_test_args(*args): test_args[:] = args
        scope = { 'reinteract_output': set_test_args }

        exec compiled in scope

        if tuple(test_args) != tuple(expected):
            raise AssertionError("Got '%s', expected '%s'" % (test_args, expected))

    test_output('a=3', ())
    test_output('1', (1,))
    test_output('1,2', (1,2))
    test_output('1;2', (2,))
    test_output('a=3; a', (3,))

    #
    # Test that our intercepting of print works
    #
    def test_print(code, expected):
        compiled, _ = rewrite_and_compile(code, print_func_name='reinteract_print')
        
        test_args = []
        def set_test_args(*args): test_args[:] = args
        scope = { 'reinteract_print': set_test_args }

        exec compiled in scope

        if tuple(test_args) != tuple(expected):
            raise AssertionError("Got '%s', expected '%s'" % (test_args, expected))

    test_print('a=3', ())
    test_print('print 1', (1,))
    test_print('print 1,2', (1,2))
    test_print('print "",', ("",))
    test_print('for i in [0]: print i', (0,))
    test_print('import sys; print >>sys.stderr, "",', ())

    #
    # Test catching possible mutations of variables
    #
    def test_mutated(code, expected):
        _, mutated = rewrite_and_compile(code)

        mutated = list(mutated)
        mutated.sort()
        
        expected = list(expected)
        expected.sort()

        if tuple(mutated) != tuple(expected):
            raise AssertionError("Got '%s', expected '%s'" % (mutated, expected))

    test_mutated('a[0] = 1', ('a',))
    test_mutated('a[0], b[0] = 1, 2', ('a', 'b'))
    test_mutated('a[0], _ = 1', ('a'))
    test_mutated('a[0], b[0] = c[0], d[0] = 1, 2', ('a', 'b', 'c', 'd'))

    test_mutated('a[0] += 1', ('a',))
    
    test_mutated('a.b = 1', ('a',))
    test_mutated('a.b += 1', ('a',))
    
    test_mutated('a.b()', (('a','b'),))
    test_mutated('a.b(1,2)', (('a','b'),))
    test_mutated('a.b.c(1,2)', ())

    #
    # Test handling of encoding
    #
    def test_encoding(code, expected, encoding=None):
        if encoding != None:
            compiled, _ = rewrite_and_compile(code, encoding=encoding, output_func_name='reinteract_output')
        else:
            compiled, _ = rewrite_and_compile(code, output_func_name='reinteract_output')
        
        test_args = []
        def set_test_args(*args): test_args[:] = args
        scope = { 'reinteract_output': set_test_args }

        exec compiled in scope

        if test_args[0] != expected:
            raise AssertionError("Got '%s', expected '%s'" % (test_args[0], expected))

    test_encoding(u"u'\u00e4'".encode("utf8"), u'\u00e4')
    test_encoding(u"u'\u00e4'", u'\u00e4')
    test_encoding(u"u'\u00e4'".encode("iso-8859-1"), u'\u00e4', "iso-8859-1")

    #
    # Test import detection
    #

    def test_imports(code, expected):
        rewriter = Rewriter(code)
        result = rewriter.get_imports()
        if result != expected:
            raise AssertionError("Got '%s', expected '%s'" % (result, expected))

    test_imports('a + 1', None)
    test_imports('import re', [('re', [('.', 're')])])
    test_imports('import re as r', [('re', [('.', 'r')])])
    test_imports('import re, os as o', [('re', [('.', 're')]), ('os', [('.', 'o')])])

    test_imports('from re import match', [('re', [('match', 'match')])])
    test_imports('from re import match as m', [('re', [('match', 'm')])])
    test_imports('from re import match as m, sub as s', [('re', [('match', 'm'), ('sub', 's')])])
    test_imports('from re import (match as m, sub as s)', [('re', [('match', 'm'), ('sub', 's')])])
    test_imports('from ..re import match', [('..re', [('match', 'match')])])
    test_imports('from re import *', [('re', '*')])

    test_imports('from __future__ import division', [('__future__', [('division', 'division')])])

    #
    # Test passing in future_features to use in compilation
    #

    scope = {}
    compiled, _ = rewrite_and_compile('a = 1/2', future_features=['with_statement', 'division'])
    exec compiled in scope
    assert scope['a'] == 0.5
