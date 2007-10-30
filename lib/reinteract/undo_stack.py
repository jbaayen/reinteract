class _InsertDeleteOp(object):
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text

    def _insert(self, buffer):
        start = buffer._get_iter_at_nr_pos(self.start)
        buffer.insert_interactive(start, self.text, len(self.text), True)

    def _delete(self, buffer):
        start = buffer._get_iter_at_nr_pos(self.start)
        end = buffer._get_iter_at_nr_pos(self.end)
        buffer.delete_interactive(start, end, True)

class InsertOp(_InsertDeleteOp):
    def redo(self, buffer):
        self._insert(buffer)
        
    def undo(self, buffer):
        self._delete(buffer)

class DeleteOp(_InsertDeleteOp):
    def redo(self, buffer):
        self._delete(buffer)
        
    def undo(self, buffer):
        self._insert(buffer)

class UndoStack(object):
    def __init__(self, buffer):
        self.__buffer = buffer
        self.__position = 0
        self.__stack = []
        self.__applying_undo = False

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
            self.__stack[self.__position].undo(self.__buffer)
        finally:
            self.__applying_undo = False            

    def redo(self):
        if self.__position == len(self.__stack):
            return

        self.__position += 1
        self.__applying_undo = True
        try:
            self.__stack[self.__position - 1].redo(self.__buffer)
        finally:
            self.__applying_undo = False            
        
    def append_op(self, op):
        if self.__applying_undo:
            return
        
        if self.__position < len(self.__stack):
            self.__stack[self.__position:] = []
        self.__stack.append(op)
        self.__position += 1
        
    def clear(self):
        self.__stack = []
        self.__position = 0
