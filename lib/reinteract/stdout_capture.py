import threading

import sys

def init():
    """Initialize the stdout_capture module. This must be called before using the StdoutCapture class"""
    global _saved_stdout
    _saved_stdout = sys.stdout
    sys.stdout = _StdoutStack()

class _StdoutStack(threading.local):
    """The StdoutStack object is used to allow overriding sys.stdout in a per-thread manner"""
    
    def __init__(self):
        self.stack = []
        self.current = _saved_stdout

    def write(self, str):
        self.current.write(str)

    def push(self, value):
        self.stack.append(self.current)
        self.current = value

    def pop(self):
        self.current = self.stack.pop()
    
class StdoutCapture:
    """

    The StdoutCapture object allows temporarily redirecting writes to sys.stdout to call a function
    You must call stdout_capture.init() before using this function

        >>> s = ""
        >>> def capture_it(str):
        ...    global s
        ...    s += str
        >>> c = StdoutCapture(capture_it)
        >>> c.push()
        >>> try:
        ...    print "Foo"
        ... finally:
        ...    c.pop()
        >>> s
        "Foo\\n"

    """
    
    def __init__(self, write_function):
        self.__write_function = write_function

    def push(self):
        """Temporarily make the capture object active"""
        
        if not isinstance(sys.stdout, _StdoutStack):
            raise RuntimeError("stdout_capture.init() has not been called, or sys.stdout has been overridden again")
        
        sys.stdout.push(self)

    def pop(self):
        """End the effect of the previous call to pop"""
        
        if not isinstance(sys.stdout, _StdoutStack):
            raise RuntimeError("stdout_capture.init() has not been called, or sys.stdout has been overridden again")
        
        sys.stdout.pop()

    # Support 'with StdoutCapture(func):' for the future, though reinteract currently limits
    # itself to Python-2.4.
    
    def __enter__(self):
        self.push()

    def __exit__(self, *args):
        self.pop()
    
    def write(self, str):
        self.__write_function(str)

if __name__ == "__main__":
    init()
    
    s = ""
    def capture_it(str):
        global s
        s += str
        
    #with StdoutCapture(capture_it):
    #    print "Foo"
    # 
    #asssert s == "Foo\n"

    s = ""
    
    c = StdoutCapture(capture_it)
    c.push()
    try:
        print "Foo"
    finally:
        c.pop()

    assert s == "Foo\n"

