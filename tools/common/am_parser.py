import logging
import re

_logger = logging.getLogger("AMParser")

# Simple class to suck in a AM file and get variables from it with substitution
class AMParser(object):
    # We ignore possibility of \\\n - a literal backslash at the end of a line
    VARIABLE_RE = re.compile(
        r'^([a-zA-Z_][a-zA-Z0-9_]*)[ \t]*=[ \t]*((?:.*\\\n)*.*)',
        re.MULTILINE);
    REFERENCE_RE = re.compile(r'\$\(([a-zA-Z_][a-zA-Z0-9_]*)\)')

    def __init__(self, filename, overrides={}):
        _logger.debug('Scanning %s', filename)

        f = open(filename, "r")
        contents = f.read()
        f.close()

        self.d = {}
        for m in AMParser.VARIABLE_RE.finditer(contents):
            name = m.group(1)
            value = m.group(2).replace('\\\n', '')
            # Canonicalize whitespace for clean debugg output, would break
            # quoted strings but we don't have any
            value = re.sub(r'\s+', ' ', value.strip())
            self.d[name] = value
            # _logger.debug('   %s = %s', name, value)

        self.d.update(overrides)

    def __getitem__(self, key):
        return AMParser.REFERENCE_RE.sub(lambda m: self[m.group(1)], self.d[key])

    def __iter__(self):
        return self.d.iterkeys()

    def __contains__(self, item):
        return item in self.d

    def iterkeys(self):
        return self.d.iterkeys()

    def iteritems(self):
        return ((x, self[x]) for x in self.d.iterkeys())
