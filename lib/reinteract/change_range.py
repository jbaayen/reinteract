# Copyright 2008 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

class ChangeRange(object):

    """
    The ChangeRange class is used to track what lines have changed, both for
    an overall WorkSheet and within individual chunks. The represention is
    a [start,end) range of lines within the range that have changed and a
    delta of how many lines have been inserted or deleted.

    (That it tracks changed lines is purely conventional, the same object
    could be used to track any other list of items.)
    """

    def __init__(self, start=-1, end=-1):
        self.start = start
        self.end = end
        self.delta = end - start

    def empty(self):
        """Return True if no lines have been inserted, deleted or changed"""
        return self.delta == 0 and self.start == self.end

    def change(self, start, end):
        """Mark a range of lines as having changed"""
        if self.empty():
            self.start = start
            self.end = end
        else:
            self.start = min(self.start, start)
            self.end = max(self.end, end)

    def insert(self, position, count):
        """Adjust the change range for an insertion"""
        if self.empty():
            self.start = position
            self.end = position + count
        else:
            if position < self.start:
                self.start = position
                self.end += count
            elif position < self.end:
                self.end += count
            else:
                self.end = position + count
        self.delta += count

    def delete_range(self, start, end):
        """Adjust the change range for a deletion"""
        if self.empty():
            self.start = self.end = start
        else:
            if self.start >= end:
                self.start -= end - start
            elif self.start >= start:
                self.start = start

            if self.end >= end:
                self.end -= end - start
            elif self.end >= start:
                self.end = start

        self.delta -= (end - start)

    def clear(self):
        """Clear the change range and reset to initial values"""
        self.start = self.end = -1
        self.delta = 0

    def __repr__(self):
        return "ChangeRange(%d,%d,%d)" % (self.start, self.end, self.delta)


######################################################################

if __name__ == '__main__': #pragma: no cover
    changes = ChangeRange()

    def expect(start, end, delta):
        if (changes.start, changes.end, delta) != (start, end, delta):
            raise AssertionError("Got %r, Expected %r" % ((changes.start, changes.end, delta), (start, end, delta)))

    # change()
    changes.change(1, 2)
    expect(1, 2, 0)
    changes.change(0, 3)
    expect(0, 3, 0)

    changes.clear()
    changes.change(0, 1)
    changes.change(2, 3)
    expect(0, 3, 0)

    # insert_lines()
    changes.clear()
    changes.insert(1,1)
    expect(1, 2, 1)

    changes.clear()
    changes.change(3,5)
    changes.insert(0,1)
    expect(0, 6, 1)

    changes.clear()
    changes.change(3,5)
    changes.insert(4,1)
    expect(3, 6, 1)

    changes.clear()
    changes.change(3,4)
    changes.insert(5,1)
    expect(3, 6, 1)

    # delete_range()
    changes.clear()
    changes.delete_range(0, 1)
    expect(0, 0, -1)

    changes.clear()
    changes.change(3, 6)
    changes.delete_range(0, 1)
    expect(2, 5, -1)

    changes.clear()
    changes.change(3, 6)
    changes.delete_range(2, 4)
    expect(2, 4, -2)

    changes.clear()
    changes.change(3, 6)
    changes.delete_range(4, 5)
    expect(3, 5, -1)

    changes.clear()
    changes.change(3, 6)
    changes.delete_range(5, 7)
    expect(3, 5, -2)

    changes.clear()
    changes.change(3, 6)
    changes.delete_range(7, 8)
    expect(3, 6, -1)

    changes.clear()
    changes.change(3, 6)
    changes.delete_range(2, 7)
    expect(2, 2, -5)

    # Combinations of insertions and deletions
    changes.clear()
    changes.insert(2, 2)
    changes.delete_range(2, 4)
    expect(2, 2, 0)

    # since the changes above were a no-op, we start from scratch
    changes.insert(0, 1)
    expect(0, 1, 1)
