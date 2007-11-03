import re

TOKEN_KEYWORD      = 1
TOKEN_NAME         = 2
TOKEN_PUNCTUATION  = 3
TOKEN_COMMENT      = 4
TOKEN_STRING       = 5
TOKEN_CONTINUATION = 6
TOKEN_NUMBER       = 7
TOKEN_JUNK         = 8
TOKEN_LPAREN       = 9
TOKEN_RPAREN       = 10
TOKEN_LSQB         = 11
TOKEN_RSQB         = 11
TOKEN_LBRACE       = 12
TOKEN_RBRACE       = 13
TOKEN_BACKQUOTE    = 14
TOKEN_COLON        = 15

FLAG_OPEN = 1
FLAG_CLOSE = 2

_KEYWORDS = set([ 'and', 'as', 'assert', 'break', 'class', 'continue', 'def',
                  'del', 'elif', 'else', 'except', 'exec', 'finally',  'for',
                  'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'not',
                  'or', 'pass', 'print', 'raise',  'return', 'try', 'while',
                  'with', 'yield' ])

_PUNCTUATION_TOKENS = {
    '(' : TOKEN_LPAREN,
    ')' : TOKEN_RPAREN,
    '[' : TOKEN_LSQB,
    ']' : TOKEN_RSQB,
    '{' : TOKEN_LBRACE,
    '}' : TOKEN_RBRACE,
    '`' : TOKEN_BACKQUOTE,
    ':' : TOKEN_COLON
}

_PUNCTUATION_MATCH = {
    ')' : '(',
    ']' : '[',
    '}' : '{',
}

_TOKENIZE_RE = re.compile(r"""
# Operators and delimeters
(?P<punctuation>
  [@,:`;~\(\)\[\]\{\}] |
  [+%&|^-]=? |
  \*(?:\*=|\*|=|) |
  /(?:/=|/|=|) |
  <(?:<=|<|=|>|) |
  >(?:>=|>|=|) |
  =(?:=|) |
  !=) |

(?P<comment> \#.*) |                                      # Comment
(?P<identifier> [A-Za-z_][A-Za-z0-9_]*) |                 # Identifier

(?P<string>
  (?:[rR][uU]?|[uU][rR]?|)
  (?P<stringcore>
    (?: '''(?:\\.|[^'\\])*(?:'''|(?=\\$)|$)) |       # String delimited with '''
    (?: \"""(?:\\.|[^"\\])*(?:\"""|(?=\\$)|$)) |     # String delimited with \"""
    (?:   '(?:\\.|[^'\\])*(?:'|(?=\\$)|$)) |           # String delimited with '
    (?:   "(?:\\.|[^"\\])*(?:"|(?=\\$)|$))             # String delimited with "
  )
) |

(?P<continuation> \\) |                                   # Line continuation

# A "number-like", possibly invalid expression
(?P<number>
  0[Xx][0-9A-Za-z_]* |

  (?: [0-9] | \.[0-9] )
  [0-9.]*
  (?: [eE][+-]? [0-9A-Za-z_.]* |
      [0-9A-Za-z_.]* )
) |

(?P<dot> \.) |                                            # isolated .
(?P<white> \s+) |                                         # whitespace
(?P<junk> .+?)                                            # Junk

""", re.VERBOSE)

_CLOSE_STRING_RE = {
    "'''": re.compile(r"(?:\\.|[^\'\\])*(?:\'\'\'|(?=\\$)|$)"),
    '"""': re.compile(r"(?:\\.|[^\"\\])*(?:\"\"\"|(?=\\$)|$)"),
    "'": re.compile(r"(?:\\.|[^\'\\])*(?:\'|(?=\\$)|$)"),
    '"': re.compile(r"(?:\\.|[^\"\\])*(?:\"|(?=\\$)|$)")
 }

# A valid number; the idea is that when tokenizing, we want to keep
# together sequences like 0junk or 0e+a and then mark them as entirely
# invalid rather than breaking them into a "valid" number and a "valid"
# part after that

_NUMBER_RE = re.compile(r"""
^(?:
0j? |                                         # 0 (or complex)
0[Xx][0-9A-Fa-f_]* |                          # Hex 
0[0-7]+ |                                     # Octal
(?:[1-9][0-9]*|0)j? |                         # Decimal (or complex)
(?:(?:[0-9]*\.[0-9]+|[0-9]+\.?)[eE][+-]?[0-9]+ | # Floating point (or complex)
      [0-9]*\.[0-9]+|[0-9]+\.)j?
)$
""", re.VERBOSE)

def tokenize_line(str, stack=None):
    if (stack == None):
        stack = []
    else:
        stack = list(stack)

    tokens = []
    pos = 0
    
    if len(stack) > 0:
        if stack[-1] in _CLOSE_STRING_RE:
            delim = stack[-1]
            match = _CLOSE_STRING_RE[delim].match(str)
            assert(match)

            flags = 0

            s  = match.group()
            if (len(s) >= len(delim) and s.endswith(delim) and
                (len(s) == len(delim) or
                 not s[len(s)-len(delim)-1] == '\\' or
                 (len(s) > len(delim) + 1 and
                  s[len(s)-len(delim)-2] == '\\'))):
                flags |= FLAG_CLOSE
                stack.pop()
                
            tokens.append((TOKEN_STRING, match.start(), match.end(), flags))
            
            pos = match.end()
            
    l = len(str)
    while pos < l:
        match = _TOKENIZE_RE.match(str, pos)
        assert(match)
#        print repr(match.group()), match.span(), match.groupdict()
        
        if not match.group('white'):
            flags = 0
            
            token_type = None
            if match.group('punctuation'):
                token_type = TOKEN_PUNCTUATION
                s = match.group()
                if s in _PUNCTUATION_TOKENS:
                    token_type = _PUNCTUATION_TOKENS[s]
                    if token_type == TOKEN_BACKQUOTE:
                        if len(stack) > 0 and stack[-1] == "`":
                            flags |= FLAG_CLOSE
                            stack.pop()
                        else:
                            flags |= FLAG_OPEN
                            stack.append("`")
                    elif s in _PUNCTUATION_MATCH:
                        if len(stack) > 0 and stack[-1] == _PUNCTUATION_MATCH[s]:
                            flags |= FLAG_CLOSE
                            stack.pop()
                        else:
                            token_type = TOKEN_JUNK
                    elif token_type == TOKEN_LPAREN or token_type == TOKEN_LSQB or token_type == TOKEN_LBRACE:
                        flags |= FLAG_OPEN
                        stack.append(s)
            elif match.group('identifier'):
                s = match.group()
                if s in _KEYWORDS:
                    token_type = TOKEN_KEYWORD
                else:
                    token_type = TOKEN_NAME
            elif match.group('number'):
                s = match.group()
                m2 = _NUMBER_RE.match(s)
                if _NUMBER_RE.match(s):
                    token_type = TOKEN_NUMBER
                else:
                    token_type = TOKEN_JUNK
            elif match.group('string'):
                token_type = TOKEN_STRING
                core = match.group('stringcore')
                if core.startswith('"""'):
                    delim = '"""'
                elif core.startswith("'''"):
                    delim = "'''"
                elif core.startswith("'"):
                    delim = "'"
                else:
                    delim = '"'
                if len(core) == len(delim) or \
                   not core.endswith(delim) or \
                   (core[len(core)-len(delim)-1] == '\\' and
                    core[len(core)-len(delim)-2] != '\\'):
                    flags |= FLAG_OPEN
                    stack.append(delim)

            elif match.group('dot'):
                token_type = TOKEN_PUNCTUATION
            elif match.group('comment'):
                token_type = TOKEN_COMMENT
            elif match.group('continuation'):
                token_type = TOKEN_CONTINUATION
            elif match.group('junk'):
                token_type = TOKEN_JUNK

            tokens.append((token_type, match.start(), match.end(), flags))
                
        pos = match.end()

    # Catch an unterminated, uncontinued short string, and don't leave it on the stack
    # Would be nice to indicate an error here somehow, but I'm not sure how
    if len(stack) > 0 and (stack[-1] == "'" or stack[-1] == '"') and \
            (len(tokens) == 0  or tokens[-1][0] != TOKEN_CONTINUATION):
        token_type, start, end, flags = tokens[-1]
        flags &= ~FLAG_OPEN
        tokens[-1] = (token_type, start, end, flags)
        stack.pop()
        
    return (tokens, stack)
    
if __name__ == '__main__':
    import sys
    
    failed = False
    
    def expect(str, expected_tokens, in_stack=[], expected_stack=[]):
        tokens, stack = tokenize_line(str, stack=in_stack)
        result = [(token[0], str[token[1]:token[2]]) for token in tokens]
        
        success = True
        if len(tokens) == len(expected_tokens):
            for (t, e) in zip(result, expected_tokens):
                if t != e:
                    success = False
                    break
        else:
            success = False
            
        if not success:
            print "For %s, got %s, expected %s" % (repr(str), result, expected_tokens)
            failed = True

        if stack != expected_stack:
            print "For %s, in_stack=%s, got out_stack=%s, expected out_stack=%s" % (repr(str), in_stack, stack, expected_stack)
            failed = True

    expect('.', [(TOKEN_PUNCTUATION, '.')])
    expect('(', [(TOKEN_LPAREN, '(')], expected_stack=['('])
    expect('<<=', [(TOKEN_PUNCTUATION, '<<=')])
    expect('<<>', [(TOKEN_PUNCTUATION, '<<'), (TOKEN_PUNCTUATION, '>')])

    expect("#foo", [(TOKEN_COMMENT, "#foo")])
    expect("1 #foo", [(TOKEN_NUMBER, "1"), (TOKEN_COMMENT, "#foo")])
    
    expect("abc", [(TOKEN_NAME, "abc")])
    
    expect("if", [(TOKEN_KEYWORD, "if")])
    
    expect("'abc'", [(TOKEN_STRING, "'abc'")])
    expect(r"'a\'bc'", [(TOKEN_STRING, r"'a\'bc'")])
    expect(r"'abc", [(TOKEN_STRING, r"'abc")])
    expect("'abc\\", [(TOKEN_STRING, "'abc"), (TOKEN_CONTINUATION, "\\")], expected_stack=["'"])
    
    expect('0x0', [(TOKEN_NUMBER, '0x0')])
    expect('1', [(TOKEN_NUMBER, '1')])
    expect('1.e3', [(TOKEN_NUMBER, '1.e3')])
    expect('.1e3', [(TOKEN_NUMBER, '.1e3')])
    expect('1.1e3', [(TOKEN_NUMBER, '1.1e3')])
    expect('1.1e+3', [(TOKEN_NUMBER, '1.1e+3')])

    expect('1.1e0+3', [(TOKEN_NUMBER, '1.1e0'), (TOKEN_PUNCTUATION, '+'), (TOKEN_NUMBER, '3')])

    expect('.', [(TOKEN_PUNCTUATION, '.')])
    expect('a.b', [(TOKEN_NAME, 'a'), (TOKEN_PUNCTUATION, '.'), (TOKEN_NAME, 'b')])

    expect('1a', [(TOKEN_JUNK, '1a')])

    # Stack tests
    expect('()', [(TOKEN_LPAREN, '('), (TOKEN_RPAREN, ')')])
    expect('}', [(TOKEN_JUNK, '}')])
    expect('(})', [(TOKEN_LPAREN, '('), (TOKEN_JUNK, '}'), (TOKEN_RPAREN, ')')])
    expect('`', [(TOKEN_BACKQUOTE, '`')], expected_stack=['`'])
    expect('``', [(TOKEN_BACKQUOTE, '`'), (TOKEN_BACKQUOTE, '`')])

    # Unterminated single line strings don't contribute to the stack
    expect('"', [(TOKEN_STRING, '"')], expected_stack=[])
    expect(r'"abc\"', [(TOKEN_STRING, r'"abc\"')])
    
    expect('"""foo""" """bar', [(TOKEN_STRING, '"""foo"""'), (TOKEN_STRING, '"""bar')], expected_stack=['"""'])

    # Testing starting with an open string
    expect('"', [(TOKEN_STRING, '"')], in_stack=['"'])
    expect('\\"', [(TOKEN_STRING, '\\"')], in_stack=['"'])
    expect('\\"" 1', [(TOKEN_STRING, '\\""'), (TOKEN_NUMBER, '1')], in_stack=['"'])
    expect("'", [(TOKEN_STRING, "'")], in_stack=["'"])
    expect('foo"""', [(TOKEN_STRING, 'foo"""')], in_stack=['"""'])
    expect('foo', [(TOKEN_STRING, 'foo')], in_stack=['"""'], expected_stack=['"""'])
    expect("foo'''", [(TOKEN_STRING, "foo'''")], in_stack=["'''"])
    expect('foo', [(TOKEN_STRING, 'foo')], in_stack=["'''"], expected_stack=["'''"])
    
    if failed:
        sys.exit(1)
    else:
        sys.exit(0)
