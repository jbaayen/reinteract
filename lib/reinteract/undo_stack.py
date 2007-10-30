import re

# Two consecutive inserts where the first one matches this regular
# expression are merged together
COALESCE_RE = re.compile(r'^\S+$')

class _InsertDeleteOp(object):
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text

    def _insert(self, buffer):
        start = buffer._get_iter_at_nr_pos(self.start)
        buffer.insert_interactive(start, self.text, True)
        buffer.place_cursor(start)

    def _delete(self, buffer):
        start = buffer._get_iter_at_nr_pos(self.start)
        end = buffer._get_iter_at_nr_pos(self.end)
        buffer.delete_interactive(start, end, True)
        buffer.place_cursor(start)

class InsertOp(_InsertDeleteOp):
    def redo(self, buffer):
        self._insert(buffer)
        
    def undo(self, buffer):
        self._delete(buffer)

    def __repr__(self):
        return "InsertOp(%s, %s, %s)" % (self.start, self.end, repr(self.text))

class DeleteOp(_InsertDeleteOp):
    def redo(self, buffer):
        self._delete(buffer)
        
    def undo(self, buffer):
        self._insert(buffer)

    def __repr__(self):
        return "DeleteOp(%s, %s, %s)" % (self.start, self.end, repr(self.text))
    
class BeginActionOp(object):
    def __repr__(self):
        return "BeginActionOp()"
    
class EndActionOp(object):
    def __repr__(self):
        return "EndActionOp()"
    
class UndoStack(object):
    def __init__(self, buffer):
        self.__buffer = buffer
        self.__position = 0
        # The position at which we last pruned the stack; everything after
        # this has been inserted consecutively without any intervening
        # undos and redos
        self.__prune_position = 0
        self.__stack = []
        self.__applying_undo = False
        self.__user_action_count = 0
        self.__action_ops = 0

    def __apply_op(self, op, reverse):
        self.__applying_undo = True
        try:
            self.__buffer._apply_undo_op(op, reverse)
        finally:
            self.__applying_undo = False
        
    def undo(self):
        if self.__position == 0:
            return

        self.__position -= 1
        
        self.__applying_undo = True
        try:
            if isinstance(self.__stack[self.__position], EndActionOp):
                self.__position -= 1
                while not isinstance(self.__stack[self.__position], BeginActionOp):
                    self.__stack[self.__position].undo(self.__buffer)
                    self.__position -= 1
            else:
                self.__stack[self.__position].undo(self.__buffer)
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
                    self.__stack[self.__position - 1].redo(self.__buffer)
                    self.__position += 1
            else:
                self.__stack[self.__position - 1].redo(self.__buffer)
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
                cur.start == prev.end and COALESCE_RE.match(prev.text):
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

        if self.__user_action_count > 0:
            self.__action_ops += 1
        else:
            self.__check_coalesce()
            
        self.__stack.append(op)
        self.__position += 1
        
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
    
