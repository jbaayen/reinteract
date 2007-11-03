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

        if i == len(lines): # Nothing to do
            return changed_lines

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
        for i, (token_type, start, end, _) in enumerate(self.tokens[line]):
            if start > index:
                return None
            if start <= index and end > index:
                return _TokenIter(self, line, i)
            
        return None
        
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
    
    assert ts.set_lines(['(1 + 2','+ 3 + 4)']) == []
    expect(ts, [['(', '1', '+', '2', ['(']], ['+', '3', '+', '4', ')']])

    assert ts.set_lines(['(1 + 2','+ 5 + 6)']) == [1]
    expect(ts, [['(', '1', '+', '2', ['(']], ['+', '5', '+', '6', ')']])

    assert ts.set_lines(['(3 + 4','+ 5 + 6)']) == [0]
    expect(ts, [['(', '3', '+', '4', ['(']], ['+', '5', '+', '6', ')']])

    assert ts.set_lines(['((1 + 2','+ 5 + 6)']) == [0, 1]
    expect(ts, [['(', '(', '1', '+', '2', ['(', '(']], ['+', '5', '+', '6', ')', ['(']]])

    assert ts.set_lines(['((1 + 2', '+ 3 + 4)', '+ 5 + 6)']) == [1, 2]
    expect(ts, [['(', '(', '1', '+', '2', ['(', '(']], ['+', '3', '+', '4', ')', ['(']], ['+', '5', '+', '6', ')']])

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
    
    if failed:
        sys.exit(1)
    else:
        sys.exit(0)
