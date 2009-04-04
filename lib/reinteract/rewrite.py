# Copyright 2007-2009 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import parser
import re
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

    def add_mutated(self, path):
        # Make sure our "mutation" isn't something like "asdfa".length(); we
        # will miss some valid mutations that we could handle like
        # (some_list).append(5). If such cases ever become and issue, we
        # could add some code here to simplify them into a "normal" form.
        if path[0][1][0] == token.NAME:
            if not path in self.mutated:
                self.mutated.append(path)

def _do_match(t, pattern, start_pos=0, start_pattern_index=0):
    # Match an AST tree against a pattern. Along with symbol/token names, patterns
    # can contain strings:
    #
    #  '': ignore the matched item
    #  'name': store the matched item into the result dict under 'name'
    #  '*': matches multiple items (greedy); ignore matched items
    #  '*name': matches items (greedy); store the matched items as a sequence into the result dict
    #
    # Returns None if nothing matched or a dict of key/value pairs
    #
    # start_pos/start_pattern_index are used to match a trailing portion of the
    # tree against a trailing portion of the pattern; this is used internally to implement
    # non-terminal wildcards in patterns.
    #
    if start_pattern_index == 0:
        if (t[0] != pattern[0]):
            return None

    result = {}
    pos = max(1, start_pos)
    for i in xrange(max(1, start_pattern_index), len(pattern)):
        if isinstance(pattern[i], tuple):
            if pos >= len(t):
                return None
            subresult = _do_match(t[pos], pattern[i])
            if subresult is None:
                return None
            result.update(subresult)
        else:
            if len(pattern[i]) > 0 and pattern[i][0] == '*':
                if i + 1 < len(pattern):
                    # Non-final *, need to find where the tail portion matches, start
                    # backwards from the end to implement a greedy match
                    for tail_pos in xrange(len(t) - 1, pos - 1, -1):
                        tail_result = _do_match(t, pattern,
                                                start_pos=tail_pos,
                                                start_pattern_index=i + 1)
                        if tail_result is not None:
                            result.update(tail_result)
                            break
                    else:
                        return None
                else:
                    tail_pos = len(t)

                if pattern[i] != '*':
                    result[pattern[i][1:]] = t[pos:tail_pos]

                return result
            else:
                if pos >= len(t):
                    return None
                if pattern[i] != '':
                    result[pattern[i]] = t[pos]

        pos += 1

    if pos > len(t):
        return None
    else:
        return result

_path_pattern = \
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
                                  '*path')))))))))))))

def _is_test_path(t):
    # Check if the given AST is "test" of the form 'a.b...c' (where there
    # may be slices and method calls in the path). If it  matches,
    # returns 'a.b...c, otherwise returns None
    args = _do_match(t, _path_pattern)
    if args is None:
        return None
    else:
        return args['path']

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
                                  '*path',
                                  (symbol.trailer,
                                   (token.DOT, ''),
                                   (token.NAME, 'method_name')),
                                  (symbol.trailer,
                                   (token.LPAR, ''),
                                   '*'))))))))))))))

def _is_test_method_call(t):
    # Check if the given AST is a "test" of the form 'a...b.c()' If it
    # matches, returns ('a...b', 'c'), otherwise returns None
    args = _do_match(t, _method_call_pattern)
    if args is None:
        return None
    else:
        return args['path'], args['method_name']

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
                                  '*path',
                                  (symbol.trailer,
                                   (token.DOT, ''),
                                   (token.NAME, '')))))))))))))))
    
    
def _is_test_attribute(t):
    # Check if the given AST is a "test" of the form 'a...b.c' If it
    # matches, returns 'a...b', otherwise returns None
    args = _do_match(t, _attribute_pattern)
    
    if args is None:
        return None
    else:
        return args['path']

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
                                  '*path',
                                  (symbol.trailer,
                                   (token.LSQB, ''),
                                   '*'))))))))))))))
    


def _is_test_slice(t):
    # Check if the given AST is a "test" of the form 'a...b[c]' If it
    # matches, returns 'a...b', otherwise returns None
    args = _do_match(t, _slice_pattern)

    if args is None:
        return None
    else:
        return args['path']

_literal_string_pattern = \
         (symbol.simple_stmt,
          (symbol.small_stmt,
           (symbol.expr_stmt,
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
                           (token.STRING,
                            '*')))))))))))))))))))

def _is_simple_stmt_literal_string(t):
    # Tests if the given string is a simple statement that is a literal string
    return _do_match(t, _literal_string_pattern) is not None

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
        
# Method names that are considered not to be getters. The Python
# standard library contains methods called isfoo() and getfoo()
# (though not hasfoo()) so we don't for a word boundary. It could
# be tightened if false positives becomes a problem.
_GETTER_RE = re.compile("get|is|has")

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
                result = _is_test_method_call(subsubnode)
                if result is not None:
                    path, method_name = result
                    if _GETTER_RE.match(method_name) is None:
                        state.add_mutated(path)

        if state.output_func_name is not None:
            return _create_funccall_expr_stmt(state.output_func_name, filter(lambda x: type(x) != int and x[0] == symbol.test, subnode))
        else:
            return t
    else:
        if (t[2][0] == symbol.augassign):
            # testlist augassign (yield_expr|testlist)
            subnode = t[1]
            assert(len(subnode) == 2) # can only augassign one thing, despite the grammar
            
            # Depending on what a is, a += b can modify a. For example appending
            # to an array with a += [3]. If a is immutable (a number say), then copying
            # it is unnecessary, but cheap
            path = _is_test_path(subnode[1])
            if path is not None:
                state.add_mutated(path)
        else:
            # testlist ('=' (yield_expr|testlist))+
            for i in xrange(1, len(t) - 1):
                if (t[i + 1][0] == token.EQUAL):
                    subnode = t[i]
                    assert(subnode[0] == symbol.testlist)
                    for j in xrange(1, len(subnode)):
                        subsubnode = subnode[j]
                        if subsubnode[0] == symbol.test:
                            path = _is_test_slice(subsubnode)
                            if path is None:
                                path = _is_test_attribute(subnode[1])

                            if path is not None:
                                state.add_mutated(path)
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

def _rewrite_docstring_suite(t, state):
    # suite: simple_stmt | NEWLINE INDENT stmt+ DEDENT
    if t[1][0] == symbol.simple_stmt:
        # Check if the only child is a docstring
        if _is_simple_stmt_literal_string(t[1]):
            return t
        else:
            return _rewrite_suite(t, state)
    else:
        result = t
        i = 3
        assert t[i][0] == symbol.stmt
        # Skip the first statement if it is a docstring
        if _is_simple_stmt_literal_string(t[i][1]):
            i += 1
        while t[i][0] == symbol.stmt:
            filtered = _rewrite_stmt(t[i], state)
            if filtered != t[i]:
                if result is t:
                    result = list(t)
                result[i] = filtered
            i += 1

        return result

def _rewrite_docstring_block_stmt(t, state):
    # Like _rewrite_block_stmt, but if the first statement is a literal
    # string interpret it as a docstring and don't rewrite it to output
    return _rewrite_tree(t, state,
                         { symbol.suite:      _rewrite_docstring_suite })

_rewrite_compound_stmt_actions = {
    symbol.if_stmt:    _rewrite_block_stmt,
    symbol.while_stmt: _rewrite_block_stmt,
    symbol.for_stmt:   _rewrite_block_stmt,
    symbol.try_stmt:   _rewrite_block_stmt,
    symbol.funcdef:    _rewrite_docstring_block_stmt,
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
# Turn list of paths that are mutated into code to copy them

def _get_path_root(path):
    atom_value = path[0][1]
    assert atom_value[0] == token.NAME

    return atom_value[1]

def _describe_path(path):
    # Turn a path into a (skeletal) textual description

    # path: atom trailer*

    # atom: ('(' [yield_expr|testlist_gexp] ')' |
    #       '[' [listmaker] ']' |
    #       '{' [dictmaker] '}' |
    #       '`' testlist1 '`' |
    #       NAME | NUMBER | STRING+)
    atom_value = path[0][1]
    if atom_value[0] == token.NAME:
        result = atom_value[1]
    elif atom_value[0] == token.LPAR:
        result = "(...)"
    elif atom_value[0] == token.LSQB:
        result = "[...]"
    elif atom_value[0] == token.LBRACE:
        result = "{...}"
    elif atom_value[0] == token.BACKQUOTE:
        result = "`...`"
    elif atom_value[0] == token.NUMBER:
        result = str(atom_value[1])
    elif atom_value[0] == token.STRING:
        result = '"..."'

    # trailer: '(' [arglist] ')' | '[' subscriptlist ']' | '.' NAME
    for trailer in path[1:]:
        trailer_value = trailer[1]
        if trailer_value[0] == token.LPAR:
            result += "(...)"
        elif trailer_value[0] == token.LSQB:
            result += "[...]"
        elif trailer_value[0] == token.DOT:
            result += "." + trailer[2][1]

    return result

def create_path_test(path):
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
                       (symbol.power,) + path))))))))))))

def _create_copy_code(path, copy_func_name):
    path_test = create_path_test(path)

    return (symbol.file_input,
            (symbol.stmt,
             (symbol.simple_stmt,
              (symbol.small_stmt,
               (symbol.expr_stmt,
                (symbol.testlist,
                 path_test),
                (token.EQUAL,
                 '='),
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
                               (token.NAME,
                                copy_func_name)),
                              (symbol.trailer,
                               (token.LPAR,
                                '('),
                               (symbol.arglist,
                                (symbol.argument,
                                 path_test)),
                               (token.RPAR,
                                ')')))))))))))))))))),
              (token.NEWLINE, '\n'))),
            (token.ENDMARKER, '\n'))

def _compile_copy_code(path, copy_func_name):
    copy_code = _create_copy_code(path, copy_func_name)
    return parser.sequence2ast(copy_code).compile()

def _compile_mutations(paths, copy_func_name):
    # First add prefixes - if a.b.c is mutated, then we need to
    # shallow-copy first a and then a.b

    paths_to_copy = set()

    # path: atom trailer*
    # trailer: '(' [arglist] ')' | '[' subscriptlist ']' | '.' NAME
    #
    # We normally chop of trailers one by one, but if we have
    # .NAME(...) (two trailers) then we chop that off as one piece
    #
    for path in paths:
        while True:
            # Dont' try to copy things that don't look like they
            # can be assigned to
            if path[-1][1][0] != token.LPAR:
                paths_to_copy.add(path)

            if len(path) == 1:
                break

            if (path[-1][1][0] == token.LPAR and
                len(path) > 2 and
                path[-2][1][0] == token.DOT):

                path = path[0:-2]
            else:
                path = path[0:-1]

    # Sort the paths with shorter paths earlier so that we copy prefixes
    # before longer versions
    paths_to_copy = sorted(paths_to_copy, lambda x,y: cmp(len(x),len(y)))

    return [(_get_path_root(path),
             _describe_path(path),
             _compile_copy_code(path, copy_func_name)) for path in paths_to_copy]

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

    def rewrite_and_compile(self, output_func_name=None, print_func_name=None, copy_func_name="__copy"):
        """
        Compiles the parse tree into code, while rewriting the parse tree according to the
        output_func_name and print_func_name arguments.

        At the same time, the code is scanned for possible mutations, and a list is returned.
        Each item in the list is a tuple of:

         - The name of the variable at the root of the path to the object
           (e.g., for a.b.c, "a")

         - A string describing what should be copied. The string may include ellipses (...)
           for complex areas - it's meant as a human description

         - Code that can be evaluated to copy the object.

        @param output_func_name: the name of function used to wrap statements that are simply expressions.
           (More than one argument will be passed if the statement is in the form of a list.)
           Can be None.

        @param print_func_name: the name of a function used to replace print statements without a destination
          file. Can be None.

        @param copy_func_name: the name of a function used to make shallow copies of objects.
           Should have the same semantics as copy.copy (will normally be an import of copy.copy)
           Defaults to __copy.

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

        return (compiled, _compile_mutations(state.mutated, copy_func_name))

##################################################3

if __name__ == '__main__':
    import copy
    import re

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
    test_output('def x():\n    1\ny = x()', (1,))

    #
    # Test that we don't intercept docstrings, even though they look like bare expressions
    #
    test_output('def x():\n    "x"\n    return 1\ny = x()', ())
    test_output('def x():\n    """"x\n"""\n    return 1\ny = x()', ())
    test_output('def x(): "x"\ny = x()', ())

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
    def test_mutated(code, expected, prepare=None, assert_old=None, assert_new=None):
        compiled, mutated = rewrite_and_compile(code)

        #
        # Basic test - check the root and description for the returned list of mutations
        #
        mutated_root_desc = sorted(((root, description) for (root, description, _) in mutated))

        # Extract the root from a description (just take the first word)
        def expand_root_desc(description):
            m = re.match(r"([a-zA-Z_0-9]+)", description)
            return m.group(1), description

        expected_root_desc = sorted((expand_root_desc(x) for x in expected))

        if tuple(mutated_root_desc) != tuple(expected_root_desc):
            raise AssertionError("Got '%s', expected '%s'" % (mutated, expected))

        # More complex test
        #
        #  a) create old scope, execute 'prepare' in it
        #  b) copy old scope, execute each copy statement
        #  c) execute the code
        #  c) run assertion checks in old and new scope

        if prepare:
            old_scope = { '__copy' : copy.copy }
            exec prepare in old_scope
            new_scope = dict(old_scope)

            for _, _, copy_code in mutated:
                exec copy_code in new_scope

            exec compiled in new_scope

            old_ok = eval(assert_old, old_scope)
            if not old_ok:
                raise AssertionError("Old scope assertion '%s' failed" % assert_old)
            new_ok = eval(assert_new, new_scope)
            if not new_ok:
                raise AssertionError("New scope assertion '%s' failed" % assert_new)

    test_mutated('a[0] = 1', ('a',),
                 'a = [2]', 'a[0] == 2', 'a[0] == 1')
    test_mutated('a[0], b[0] = 1, 2', ('a', 'b'),
                 'a,b = [2],[1]', 'a[0],b[0] == 2,1', 'a[0],b[0] == 1,2')
    test_mutated('a[0], _ = 1', ('a'))
    test_mutated('a[0], b[0] = c[0], d[0] = 1, 2', ('a', 'b', 'c', 'd'))
    test_mutated('a[0][1] = 1', ('a', 'a[...]'),
                 'a = [[0,2],1]', 'a[0][1] == 2', 'a[0][1] == 1')

    # This isn't fully right - in the new scope b should be [1], not []
    test_mutated('a[0].append(1)', ('a', 'a[...]'),
                 'b = []; a = [b]',
                 'b == [] and a == [b]', 'b == [] and a == [[1]]')

    test_mutated('a += 1', ('a',))
    test_mutated('a[0] += 1', ('a', 'a[...]'))

    prepare = """
class A:
    def __init__(self):
        self.b = 1
    def addmul(self, x,y):
        self.b += x * y
    def get_a(self):
        return self.a
    pass
a = A()
a.a = A()
"""

    test_mutated('a.b = 2', ('a',),
                 prepare, 'a.b == 1', 'a.b == 2')
    test_mutated('a.b = 2', ('a',),
                 prepare, 'a.b == 1', 'a.b == 2')
    test_mutated('a.a.b = 2', ('a','a.a'),
                 prepare, 'a.a.b == 1', 'a.a.b == 2')
    test_mutated('a.a.b += 1', ('a','a.a','a.a.b'),
                 prepare, 'a.a.b == 1', 'a.a.b == 2')

    test_mutated('a.addmul(1,2)', ('a',),
                 prepare, 'a.b == 1', 'a.b == 3')
    test_mutated('a.a.addmul(1,2)', ('a', 'a.a'),
                 prepare, 'a.a.b == 1', 'a.a.b == 3')

    # We exempt some methods as being most likely getters.
    test_mutated('a.get_a()', ())
    test_mutated('a.hasA()', ())
    test_mutated('a.isa()', ())

    # These don't actually work properly since we don't know to copy a.a
    # So we just check the descriptions and not the execution
    test_mutated('a.get_a().b = 2', ('a',))
    test_mutated('a.get_a().a.b = 2', ('a', 'a.get_a(...).a'))

    #
    # Test handling of encoding
    #
    def test_encoding(code, expected, encoding=None):
        if encoding is not None:
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
