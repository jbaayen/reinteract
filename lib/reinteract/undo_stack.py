import re

# Two consecutive inserts are merged together if the sum of the
# two matches this. The (?!\n) is to defeat the normal regular
# expression behavior where 'a$' matches 'a\n' because $ matches
# before the last newline in the string
COALESCE_RE = re.compile(r'^\S+ *(?!\n)$')

class _InsertDeleteOp(object):
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text

    def _insert(self, worksheet):
        worksheet.begin_user_action()
        worksheet.insert(self.start[0], self.start[1], self.text)
        worksheet.end_user_action()
        worksheet.place_cursor(self.end[0], self.end[1])

    def _delete(self, worksheet):
        worksheet.begin_user_action()
        worksheet.delete_range(self.start[0], self.start[1], self.end[0], self.end[1])
        worksheet.end_user_action()
        worksheet.place_cursor(self.start[0], self.start[1])

class InsertOp(_InsertDeleteOp):
    def redo(self, worksheet):
        self._insert(worksheet)
        
    def undo(self, worksheet):
        self._delete(worksheet)

    def __repr__(self):
        return "InsertOp(%s, %s, %s)" % (self.start, self.end, repr(self.text))

class DeleteOp(_InsertDeleteOp):
    def redo(self, worksheet):
        self._delete(worksheet)
        
    def undo(self, worksheet):
        self._insert(worksheet)

    def __repr__(self):
        return "DeleteOp(%s, %s, %s)" % (self.start, self.end, repr(self.text))
    
class BeginActionOp(object):
    def __repr__(self):
        return "BeginActionOp()"
    
class EndActionOp(object):
    def __repr__(self):
        return "EndActionOp()"
    
class UndoStack(object):
    def __init__(self, worksheet):
        self.__worksheet = worksheet
        self.__position = 0
        # The position at which we last pruned the stack; everything after
        # this has been inserted consecutively without any intervening
        # undos and redos
        self.__prune_position = 0
        self.__stack = []
        self.__applying_undo = False
        self.__user_action_count = 0
        self.__action_ops = 0

    def undo(self):
        if self.__position == 0:
            return

        self.__position -= 1
        
        self.__applying_undo = True
        try:
            if isinstance(self.__stack[self.__position], EndActionOp):
                self.__position -= 1
                while not isinstance(self.__stack[self.__position], BeginActionOp):
                    self.__stack[self.__position].undo(self.__worksheet)
                    self.__position -= 1
            else:
                self.__stack[self.__position].undo(self.__worksheet)
        finally:
            self.__applying_undo = False

    def redo(self):
        if self.__position == len(self.__stack):
            return

        self.__position += 1
        self.__applying_undo = True
        try:
            if isinstance(self.__stack[self.__position - 1], BeginActionOp):
                self.__position += 1
                while not isinstance(self.__stack[self.__position - 1], EndActionOp):
                    self.__stack[self.__position - 1].redo(self.__worksheet)
                    self.__position += 1
            else:
                self.__stack[self.__position - 1].redo(self.__worksheet)
        finally:
            self.__applying_undo = False

    def __check_coalesce(self):
        assert self.__position == len(self.__stack)
        # Don't coalesce two ops unless they are actually adjacent in time
        if self.__position < self.__prune_position + 2:
            return

        cur = self.__stack[-1]
        prev = self.__stack[-2]
        if isinstance(cur, InsertOp) and isinstance(prev, InsertOp) and \
                cur.start == prev.end and COALESCE_RE.match(prev.text + cur.text):
            prev.end = cur.end
            prev.text += cur.text
            self.__stack.pop()
            self.__position -= 1
            
    def append_op(self, op):
        if self.__applying_undo:
            return

        if self.__position < len(self.__stack):
            assert self.__action_ops == 0
            self.__stack[self.__position:] = []
            self.__prune_position = self.__position

        self.__stack.append(op)
        self.__position += 1
        
        if self.__user_action_count > 0:
            self.__action_ops += 1
        else:
            self.__check_coalesce()
        
    def begin_user_action(self):
        self.__user_action_count += 1
        
    def end_user_action(self):
        self.__user_action_count -= 1
        if self.__user_action_count == 0:
            if self.__action_ops > 1:
                self.__stack.insert(len(self.__stack) - self.__action_ops, BeginActionOp())
                self.__stack.append(EndActionOp())
                self.__position += 2
            elif self.__action_ops == 1:
                self.__check_coalesce()
            self.__action_ops = 0
                

    def clear(self):
        self.__stack = []
        self.__position = 0

    def __repr__(self):
        return "UndoStack(stack=%s, position=%d)" % (self.__stack, self.__position)
    
