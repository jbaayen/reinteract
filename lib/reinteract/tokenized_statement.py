import inspect
from tokenize import *

class _TokenIter(object):
    def __init__(self, statement, line, i):
        self.statement = statement
        self.line = line
        self.i = i
        self.__update()

    def __update(self):
        self.token_type, self.start, self.end, self.flags = self.statement.tokens[self.line][self.i]

    def prev(self):
        if self.i > 0:
            self.i -= 1
        else:
            l = self.line - 1
            while True:
                if l < 0:
                    raise StopIteration("Already at beginning")
                if len(self.statement.tokens[l]) > 0:
                    break
                l -= 1
            self.line = l
            self.i = len(self.statement.tokens[l]) - 1
        self.__update()
        
    def next(self):
        if self.i + 1 < len(self.statement.tokens[self.line]):
            self.i += 1
        else:
            l = self.line + 1
            while True:
                if l >= len(self.statement.tokens):
                    raise StopIteration("Already at end")
                if len(self.statement.tokens[l]) > 0:
                    break
                l += 1
            self.line = l
            self.i = 0
        self.__update()

    def is_open(self):
        return self.flags & FLAG_OPEN != 0
        
    def is_close(self):
        return self.flags & FLAG_CLOSE != 0
    
class TokenizedStatement(object):
    def __init__(self):
        self.lines = []
        self.tokens = []
        self.stacks = []

    def set_lines(self, lines):
        """Set the lines in the Tokenized statement

        Returns None if nothing changed, otherwise returns a list of
        lines that were added or changed. A return of [] means that
        some lines were deleted, but none added or changed.

        """
        
        # We want to avoid retokenizing everything on pure insertions
        # to make editing not egregiously O(n^2); we don't care much
        # if we have to retokenize on other cases.

        old_lines = self.lines
        old_tokens = self.tokens
        old_stacks = self.stacks

        self.lines = lines
        tokens = self.tokens = [None] * len(lines)
        stacks = self.stacks = [None] * len(lines)

        changed_lines = []

        # Iterate forward, find an unchanged segment of lines at the front

        m = min(len(lines), len(old_lines))

        i = 0
        while i < m:
            if lines[i] != old_lines[i]:
                break
            tokens[i] = old_tokens[i]
            stacks[i] = old_stacks[i]
            i += 1

        if i == len(lines) and i == len(old_lines): # Nothing to do
            return None

        # Iterate backwards, find an unchanged segment of lines at the end

        m = min(len(lines) - i, len(old_lines) - i)

        j = 0
        new_pos = len(lines) - 1
        old_pos = len(old_lines) - 1
        while j < m:
            if lines[new_pos] != old_lines[old_pos]:
                break
            tokens[new_pos] = old_tokens[old_pos]
            stacks[new_pos] = old_stacks[old_pos]
            new_pos -= 1
            old_pos -= 1
            j += 1

        # Start tokenizing at the first changed line

        if i > 0:
            stack = stacks[i - 1]
        else:
            stack = []

        while i < len(lines):
            if i > new_pos:
                # Once we are in the trailing section if identical
                # lines, and the stack is the same as it was before,
                # we can stop
                old_i = old_pos + i - new_pos - 1
                if old_i < 0:
                    old_stack = []
                else:
                    old_stack = old_stacks[old_i]

                if stack == old_stack:
                    break

            changed_lines.append(i)

            tokens[i], stack = tokenize_line(lines[i], stack)
            stacks[i] = stack
            i += 1

        return changed_lines

    def get_text(self):
        return "\n".join(self.lines)

    def get_tokens(self, line):
        return self.tokens[line]

    def _get_iter(self, line, index):
        # Get an iterator pointing to the token containing the specified
        # position. Return None if there no such token
        for i, (token_type, start, end, _) in enumerate(self.tokens[line]):
            if start > index:
                return None
            if start <= index and end > index:
                return _TokenIter(self, line, i)
            
        return None
        
    def _get_iter_before(self, line, index):
        # Get an iterator pointing the last token that is not completely after
        # the specified position. Returns None if the position is before any tokens
        
        tokens = self.tokens[line]
        if len(tokens) == 0 or index <= tokens[0][1]:
            while line > 0:
                line -= 1
                if len(self.tokens[line]) > 0:
                    return _TokenIter(self, line, len(self.tokens[line]) - 1)
                
            return None
        else:
            for i, (token_type, start, end, _) in enumerate(tokens):
                if index <= start:
                    return _TokenIter(self, line, i - 1)

            return _TokenIter(self, line, len(tokens) - 1)

    def _get_start_iter(self):
        # Get an iterator pointing to the first token, or None if the statement
        # is empty

        line = 0
        while line < len(self.lines) and len(self.tokens[line]) == 0:
            line += 1

        if line == len(self.lines) or len(self.tokens[line]) == 0:
            return None

        return _TokenIter(self, line, 0)
                  
    def get_pair_location(self, line, index):
        iter = self._get_iter(line, index)
        if iter == None:
            return None, None

        # We don't do pair matching on strings; it's obvious from the
        # fontification, even though strings can participate in the stack
        if iter.token_type == TOKEN_STRING:
            return None, None
        elif iter.is_close():
            level = 0
            while True:
                if iter.is_close():
                    level += 1
                elif iter.is_open():
                    level -= 1
                if level == 0:
                    return iter.line, iter.start
                    
                iter.prev()
                
        elif iter.is_open():
            level = 0
            while True:
                if iter.is_close():
                    level -= 1
                elif iter.is_open():
                    level += 1
                if level == 0:
                    return iter.line, iter.start

                try:
                    iter.next()
                except StopIteration:
                    break

        return None, None

    def get_next_line_indent(self, line):
        base_line = line
        while True:
            prev_line = base_line - 1
            if prev_line < 0:
                break
            if (len(self.stacks[prev_line]) == 0 and
                (len(self.tokens[prev_line]) == 0 or self.tokens[prev_line][-1][0] != TOKEN_CONTINUATION)):
                break

            base_line = prev_line

        indent_text = re.match(r"^[\t ]*", self.lines[base_line]).group(0)
        extra_indent = 0

        tokens = self.tokens[line]

        if (len(tokens) > 0 and tokens[-1][0] == TOKEN_COLON or
            len(tokens) > 1 and tokens[-1][0] == TOKEN_COMMENT and tokens[-2][0] == TOKEN_COLON):
            extra_indent = 4
        elif len(self.stacks[line]) > 0:
            extra_indent = 4
        elif len(tokens) > 0 and tokens[-1][0] == TOKEN_CONTINUATION:
            extra_indent = 4

        if extra_indent != 0:
            indent_text += " " * extra_indent
            
        return indent_text

    def __statement_is_import(self):
        iter = self._get_start_iter()
        if iter != None:
            while iter.token_type == TOKEN_CONTINUATION:
                try:
                    iter.next()
                except StopIteration:
                    break
            if iter.token_type == TOKEN_KEYWORD and self.lines[iter.line][iter.start:iter.end] == 'import':
                return True

        return False

    def __resolve_names(self, names, scope):
        obj = None
        for name in names:
            # First name is resolved against the scope
            if obj == None:
                try:
                    obj = scope[name]
                except KeyError:
                    return None
            # Subsequent names resolved
            else:
                try:
                    obj = getattr(obj, name)
                except AttributeError:
                    return None

        return obj
                
    def __sort_completions(self, completions):
        # Sort a set of completions with _ and __ names at the end.
        # (modifies completions and then returns it for convenience)
        
        def compare_completions(a, b):
            n_a = a[0]
            n_b = b[0]

            if n_a.startswith("__") and not n_b.startswith("__"):
                return 1
            elif n_b.startswith("__") and not n_a.startswith("__"):
                return -1
            elif n_a.startswith("_") and not n_b.startswith("_"):
                return 1
            elif n_b.startswith("_") and not n_a.startswith("_"):
                return -1
            else:
                return cmp(n_a, n_b)

        completions.sort(compare_completions)
        
        return completions

    def __list_scope(self, scope):
        # List possible completions given a scope directionary
        
        possible = scope.items()
        if '__builtins__' in scope:
            builtins = scope['__builtins__']
            if not isinstance(builtins, dict):
                builtins = dir(builtins)
                
            for k in builtins:
                if not k in scope:
                    possible.append((k, builtins[k]))

        return possible
    
    def __find_no_symbol_completions(self, scope):
        # Return the completions to offer when we don't have a start at a symbol
        
        result = []
        for completion, obj in self.__list_scope(scope):
            result.append((completion, completion, obj))

        return self.__sort_completions(result)
    
    def find_completions(self, line, index, scope):
        """Returns a list of possible completions at the given line and index.

        Scope is the scope to start calculating the comptions from. Each element
        in the returned list is a tuple of (display_form, text_to_insert, object_completed_to)'
        where object_completed_to can be used to determine the type of the completion
        or get docs about it.

        """

        # We turn off completion within an import statement, since it's less
        # than useful to complete to symbols in the current scope. Better would be to
        # actually examine the path and complete to real imports.
        if self.__statement_is_import():
            return []

        # We can offer completions if we are at a position of the form:
        # ([TOKEN_NAME|TOKEN_BUILTIN_CONSTANT] TOKEN_DOT)* (TOKEN_NAME|TOKEN_KEYWORD|TOKEN_BUILTIN_CONSTANT)?
        #
        # We work backwards from the last name, and build a list of names, then resolve
        # that list of names against the scope.
        
        # Look for a token right before the specified position.  index - 1 is OK here
        # even though that byte may note b a character start since we are just
        # interested in a position inside the token
        iter = self._get_iter(line, index - 1)
        if iter != None and (iter.token_type == TOKEN_KEYWORD or
                             iter.token_type == TOKEN_NAME or
                             iter.token_type == TOKEN_BUILTIN_CONSTANT):
            end = min(iter.end, index)
            names = [self.lines[iter.line][iter.start:end]]
            try:
                iter.prev()
            except StopIteration:
                pass
        else:
            # For a TOKEN_DOT, we can be more forgiving and accept white space between the
            # token and the current position
            iter = self._get_iter_before(line, index)
            if iter != None and iter.token_type == TOKEN_DOT:
                names = ['']
            # This is a non-exhaustive list of places where we know that we shouldn't complete to the
            # the scope. (We could do better by special casing actual completions for TOKEN_RSQB, TOKEN_RBRACE,
            # TOKEN_STRING)
            elif iter != None and iter.token_type in (TOKEN_NAME, TOKEN_BUILTIN_CONSTANT, TOKEN_RPAREN, TOKEN_RSQB, TOKEN_RBRACE,
                                                      TOKEN_STRING, TOKEN_NUMBER):
                return []
            
            else:
                return self.__find_no_symbol_completions(scope)

        while iter.token_type == TOKEN_DOT:
            try:
                iter.prev()
            except StopIteration:
                return []

            if iter.token_type != TOKEN_NAME and iter.token_type != TOKEN_BUILTIN_CONSTANT:
                return []

            names.insert(0, self.lines[iter.line][iter.start:iter.end])

        # We resolve the leading portion of the name path
        if len(names) > 1:
            object = self.__resolve_names(names[0:-1], scope)
            if object == None:
                return []
        else:
            object = None

        # Then we complete the last element of the name path against what we resolved
        # to, or against the scope (if there was just one name)
        result = []
        
        to_complete = names[-1]
        if object == None:
            for completion, obj in self.__list_scope(scope):
                if completion.startswith(to_complete):
                    result.append((completion, completion[len(to_complete):], obj))
        else:
            for completion in dir(object):
                if completion.startswith(to_complete):

                    if inspect.ismodule(object):
                        object_completed_to = getattr(object, completion, None)
                    # We special case these because obj.__class__.__module__/__doc__
                    # are also a strings, not a method/property
                    elif completion != '__module__' and completion != '__doc__':
                        # Using the attribute of the class over the attribute of
                        # the object gives us better docs on properties
                        try:
                            klass = getattr(object, '__class__')
                            object_completed_to = getattr(klass, completion)
                        except AttributeError:
                            object_completed_to = getattr(object, completion)
                    else:
                        object_completed_to = None
                        
                    result.append((completion, completion[len(to_complete):], object_completed_to))

        return self.__sort_completions(result)
            
    def get_object_at_location(self, line, index, scope, result_scope=None, include_adjacent=False):
        """Find the object at a particular location within the statement.

        Returns a tuple of (object, token_start_line, token_start_index, token_end_line, token_end_index)
        or None, None, None, None, None if there is no object

        scope -- scope dictionary to start resolving names from.
        result_scope -- scope to resolve names from on the left side of an assignment
        include_adjacent -- if False, then line/index identifies a character in the buffer. If True,
           then line/index identifies a position between characters, and symbols before or after that
           position are included.

        """

        NO_RESULT = None, None, None, None, None

        # Names within an import statement aren't there yet
        if self.__statement_is_import():
            return NO_RESULT
        
        # We can resolve the object if we are inside the final token of a sequence of the form:
        # ([TOKEN_NAME|TOKEN_BUILTIN_CONSTANT] TOKEN_DOT)* (TOKEN_NAME|TOKEN_KEYWORD|TOKEN_BUILTIN_CONSTANT)
        #
        # We work backwards from the last name, and build a list of names, then resolve
        # that list of names against the scope
        
        iter = self._get_iter(line, index)
        if iter != None and not (iter.token_type == TOKEN_KEYWORD or
                                 iter.token_type == TOKEN_NAME or
                                 iter.token_type == TOKEN_BUILTIN_CONSTANT):
            iter = None
        
        if iter == None and include_adjacent and index > 0:
            iter = self._get_iter(line, index - 1)
            
            if iter != None and not (iter.token_type == TOKEN_KEYWORD or
                                     iter.token_type == TOKEN_NAME or
                                     iter.token_type == TOKEN_BUILTIN_CONSTANT):
                iter = None
                
        if iter == None:
            return NO_RESULT

        start_index = iter.start
        end_index = iter.end

        names = [self.lines[iter.line][iter.start:iter.end]]
        try:
            iter.prev()
        except StopIteration:
            pass

        while iter.token_type == TOKEN_DOT:
            try:
                iter.prev()
            except StopIteration:
                return NO_RESULT

            if iter.token_type != TOKEN_NAME and iter.token_type != TOKEN_BUILTIN_CONSTANT:
                return NO_RESULT

            names.insert(0, self.lines[iter.line][iter.start:iter.end])

        if result_scope != None:
            while True:
                try:
                    iter.next()
                except StopIteration:
                    break
                
                if iter.token_type == TOKEN_EQUAL or iter.token_type == TOKEN_AUGEQUAL:
                    scope = result_scope
                    break

        obj = self.__resolve_names(names, scope)
        if obj != None:
            return obj, line, start_index, line, end_index
        else:
            return NO_RESULT

    def __repr__(self):
        return "TokenizedStatement" + repr([([(t[0], line[t[1]:t[2]]) for t in tokens], stack) for line, tokens, stack in zip(self.lines, self.tokens, self.stacks)])
            
if __name__ == '__main__':
    import sys
    
    failed = False
    
    def expect(ts, expected):
        result = []
        for line, tokens, stack in zip(ts.lines, ts.tokens, ts.stacks):
            elements = [ line[t[1]:t[2]] for t in tokens ]
            if stack != []:
                elements.append(stack)
            result.append(elements)

        if result != expected:
            print "For:\n%s\nGot:\n%s\nExpected:\n%s\n" % (
                "\n".join(ts.lines),
                "\n".join([repr(l) for l in result]),
                "\n".join([repr(l) for l in expected]))

            failed = True
    
    ts = TokenizedStatement()
    assert ts.set_lines(["1"]) == [0]
    expect(ts, [["1"]])

    ts = TokenizedStatement()
    assert ts.set_lines(['"""a','b"""']) == [0, 1]
    expect(ts, [['"""a',['"""']],['b"""']])

    ts = TokenizedStatement()
    assert ts.set_lines(['(1 + 2','+ 3 + 4)']) == [0, 1]
    expect(ts, [['(', '1', '+', '2', ['(']], ['+', '3', '+', '4', ')']])
    
    assert ts.set_lines(['(1 + 2','+ 3 + 4)']) == None
    expect(ts, [['(', '1', '+', '2', ['(']], ['+', '3', '+', '4', ')']])

    assert ts.set_lines(['(1 + 2','+ 5 + 6)']) == [1]
    expect(ts, [['(', '1', '+', '2', ['(']], ['+', '5', '+', '6', ')']])

    assert ts.set_lines(['(3 + 4','+ 5 + 6)']) == [0]
    expect(ts, [['(', '3', '+', '4', ['(']], ['+', '5', '+', '6', ')']])

    assert ts.set_lines(['((1 + 2','+ 5 + 6)']) == [0, 1]
    expect(ts, [['(', '(', '1', '+', '2', ['(', '(']], ['+', '5', '+', '6', ')', ['(']]])

    assert ts.set_lines(['((1 + 2', '+ 3 + 4)', '+ 5 + 6)']) == [1, 2]
    expect(ts, [['(', '(', '1', '+', '2', ['(', '(']], ['+', '3', '+', '4', ')', ['(']], ['+', '5', '+', '6', ')']])

    assert ts.set_lines(['((1 + 2', '+ 3 + 4)']) == [] # truncation

    ### Tests of iterator functionality
    
    ts = TokenizedStatement()
    ts.set_lines(['(1 + ','2)'])
    assert ts._get_iter(0, 2) == None
    assert ts._get_iter(1, 2) == None

    i = ts._get_iter(0, 3)
    assert i.token_type == TOKEN_PUNCTUATION
    assert i.start == 3
    assert i.end == 4

    i.prev()
    assert i.token_type == TOKEN_NUMBER
    assert i.start == 1
    assert i.end == 2

    i.prev()
    assert i.token_type == TOKEN_LPAREN
    assert i.start == 0
    assert i.end == 1

    raised = False
    try:
        i.prev()
    except StopIteration:
        raised = True
    assert raised
    assert i.start == 0
    assert i.end == 1

    i = ts._get_iter(0, 3)
    i.next()
    assert i.line == 1
    assert i.start == 0
    assert i.end == 1

    i.next()
    assert i.start == 1
    assert i.end == 2

    raised = False
    try:
        i.next()
    except StopIteration:
        raised = True
    assert raised
    assert i.start == 1
    assert i.end == 2

    ### Tests of paired punctuation
    
    ts = TokenizedStatement()
    ts.set_lines(['a = ([(1 + ',
                  '2), { "a" : "b" }',
                  ']}'])

    # Pair location is not at a random position
    assert ts.get_pair_location(1, 2) == (None, None)
    # Pair location is None for an unpaired closed (which isn't a close at all)
    assert ts.get_pair_location(2, 1) == (None, None)
    # Pair location is None for an unpaired open
    assert ts.get_pair_location(0, 4) == (None, None)

    # Open punctuation
    assert ts.get_pair_location(0, 5) == (2, 0)
    assert ts.get_pair_location(1, 4) == (1, 16)

    # Close punctuation
    assert ts.get_pair_location(2, 0) == (0, 5)
    assert ts.get_pair_location(1, 16) == (1, 4)

    ### Tests of get_next_line_indent()

    ts = TokenizedStatement()

    lines = ([('if (True):',                     4),
              ('    pass',                       4),
              ('if (True): # a true statement',  4),
              ('    pass',                       4),
              ('if (a >',                        4),
              ('    1 +',                        4),
              ('    5):',                        4),
              ('    pass',                       4),
              ('"""A string',                    4),
              ('    more string',                4),
              ('    string finish"""',           0),
              ('a = \\',                         4),
              ('    1',                          0),
              ])

    ts.set_lines([text for text, _ in lines])
    for i, (text, expected) in enumerate(lines):
        next_line_indent = ts.get_next_line_indent(i).count(" ")
        if next_line_indent != expected:
            print "For %s, got next_line_indent=%d, expected %d" % (text, next_line_indent, expected)
            failed = True

    ### Tests of find_completions()

    class MyObject:
        def method(self):
            pass
            
    scope = {
        '__builtins__': {
            'len': len
        },
        'a': 1,
        'abcd': 2,
        'bcde': 3,
        'obj': MyObject()
    }
            
    def test_completion(line, expected, index = -1):
        if index == -1:
            index = len(line)
        
        ts = TokenizedStatement()
        ts.set_lines([line])
        completions = [n for n, _, _ in ts.find_completions(0, index, scope)]
        if completions != expected:
            print "For %s/%d, got %s, expected %s" % (line,index,completions,expected)
            failed = True

    def test_multiline_completion(lines, line, index, expected):
        ts = TokenizedStatement()
        ts.set_lines(lines)
        completions = [n for n, _, _ in ts.find_completions(line, index, scope)]
        if completions != expected:
            print "For %s/%d/%d, got %s, expected %s" % (lines,line,index,completions,expected)
            failed = True

    test_completion("a", ['a', 'abcd'])
    test_completion("ab", ['abcd']) 
    test_completion("ab", ['a', 'abcd'], index=1) 
    test_completion("foo.", []) 
    test_completion("(a + b)", []) 
    test_completion("", ['a', 'abcd', 'bcde', 'len', 'obj', "__builtins__"])
    test_completion("foo + ", ['a', 'abcd', 'bcde', 'len', 'obj', "__builtins__"])
    test_completion("l", ['len'])
    test_completion("obj.", ['method', '__doc__', '__module__'])
    test_completion("obj.m", ['method', '__doc__', '__module__'], index=4)
    test_completion("obj.m", ['method'])
    test_completion("obj.m().n", [])
    test_completion("import a", [])

    test_multiline_completion(["(obj.", "m"], 1, 0, ['method', '__doc__', '__module__'])
    test_multiline_completion(["(obj.", "m"], 1, 1, ['method'])
    
    ### Tests of get_object_at_location()

    def test_object_at_location(line, index, expected, include_adjacent=False):
        ts = TokenizedStatement()
        ts.set_lines([line])
        obj, _, _, _, _ = ts.get_object_at_location(0, index, scope, include_adjacent=include_adjacent)
        if obj != expected:
            print "For %s/%d, got %s, expected %s" % (line,index,obj,expected)
            failed = True

    test_object_at_location("a", 0, 1)
    test_object_at_location("a", 1, None)
    test_object_at_location("obj.method", 0, scope['obj'])
    test_object_at_location("obj.method", 1, scope['obj'])
    test_object_at_location("obj.method", 4, scope['obj'].method)
    test_object_at_location("obj.met", 4, None)

    test_object_at_location("c a b", 2, 1, include_adjacent=True)
    test_object_at_location("c a b", 3, None, include_adjacent=False)
    test_object_at_location("c a b", 3, 1, include_adjacent=True)

    if failed:
        sys.exit(1)
    else:
        sys.exit(0)
