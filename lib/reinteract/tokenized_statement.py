from tokenize import tokenize_line

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

    if failed:
        sys.exit(1)
    else:
        sys.exit(0)
