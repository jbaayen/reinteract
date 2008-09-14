import ctypes
import gobject
import signal
import sys
import thread

from statement import Statement

#
# The primary means we use to interrupt a running thread is a Python facility
# to set an exception asynchronously on another thread. To keep it out of
# unsuspecting hands, it's not bound in Python, so we need to accesss it
# through pthreads.
#
_PyThreadState_SetAsyncExc = ctypes.pythonapi.PyThreadState_SetAsyncExc

#
# _PyThreadState_SetAsyncExc won't immediately wake up a thread that is blocking
# in a syscall, so we also send a Unix signal to hopefully wake such a thread
# up. (This can be foiled if the syscall is called within C code that catches
# EINTR and restarts. In that case, we have no way of killing the thread without
# breaking Python internal state so we don't try.)
#
# To make sending a signal wake the thread up out of the syscall without killing
# the thread, we need a non-default no-op handler for the signal. The slightly
# tricky thing about what we do is that signal.signal() is defined to affect only
# the main thread, but the way it does it is set up a handler for all threads and
# then ignore the signal in all but the main thread. So, our ignore_handler is
# never called, but Python's handler does what we wanted to do (ignore the signal)
# anyways.
#
if sys.platform == 'win32':
    _pthread_kill = None
else:
    if sys.platform == 'darwin':
        # pthread_kill is in the C library on OS/X
        # ctypes.util.find_library("c") should work in theory, but doesn't
        _pthreads_dll = ctypes.CDLL("/usr/lib/libc.dylib")
    else:
        # Assume Linux. We intentionally don't guard this against failure
        # so that we get bug reports when we don't find libpthread
        _pthreads_dll = ctypes.CDLL("libpthread.so.0")
    
    _pthread_kill = _pthreads_dll.pthread_kill

if _pthread_kill != None:
    def _ignore_handler(signum, frame):
        pass

    signal.signal(signal.SIGUSR1, _ignore_handler)

class ThreadExecutor(gobject.GObject):
    """Class to execute Python statements asynchronously in a thread

    Signals
    =======
     -  B{statement-complete}(executor, statement) emitted when the executor is done with all processing it will do on a statement
     -  B{complete}(executor): emitted when the executor is done with all processing

    """

    __gsignals__ = {
        'statement-complete' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        'complete' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
    }

    def __init__(self, parent_statement=None):
        """Initialize the ThreadExecutor object

        @param parent_statement: prievous statement defining the execution environment for the first statement

        """
        gobject.GObject.__init__(self)

        self.parent_statement = parent_statement
        self.statements = []
        self.lock = thread.allocate_lock()

        self.idle_id = 0
        self.last_complete = -1
        self.last_signalled = -1
        self.complete = False
        self.interrupted = False

    def __run_idle(self):
        self.lock.acquire()
        complete = self.complete
        last_complete = self.last_complete
        self.idle_id = 0
        self.lock.release()

        for i in xrange(self.last_signalled + 1, last_complete + 1):
            self.emit('statement-complete', self.statements[i])

        self.last_signalled = last_complete

        if self.complete:
            self.emit('complete')

        return False

    def __queue_idle(self):
        # Must be called with the lock held
        if not self.idle_id:
            self.idle_id = gobject.idle_add(self.__run_idle)

    def __run_thread(self):
        # The patten used twice here of:
        #
        #  try:
        #      # do something with lock not held
        #      self.lock.acquire()
        #   except:
        #      self.lock.acquire()
        #   finally:
        #      # do finishing steps
        #
        # Counts on two things: a) we can receive an unexpected exception like
        # KeyboardInterrupt only once b) that exception can't occur with the lock
        # held. Given those assumptions, we can be sure that the finishing steps
        # will be run and they won't be interrupted.
        #
        statement = None
        try:
            for i, statement in enumerate(self.statements):
                self.lock.acquire()
                statement.before_execute()
                try:
                    self.lock.release()
                    statement.execute()
                    self.lock.acquire()
                except:
                    self.lock.acquire()
                finally:
                    statement.after_execute()
                    result_state = statement.state
                    self.last_complete = i;
                    self.__queue_idle()
                    self.lock.release()

                    if result_state != Statement.EXECUTE_SUCCESS:
                        break

            self.lock.acquire()
        except KeyboardInterrupt, e:
            self.lock.acquire()
        except BaseException, e:
            self.lock.acquire()
            raise
        finally:
            self.complete = True
            self.last_complete = len(self.statements) - 1
            self.__queue_idle()
            self.lock.release()

    def add_statement(self, statement):
        """Add a statement to the list of statements that the executor will execute."""

        self.statements.append(statement)

    def compile(self):
        """Compile all statements.

        If compilation failed, then all processing for the executor is complete, so
        ::statement-complete is emitted for each statement, then ::complete is emitted.
        Otherwise no signals are emitted, until the executor is run using execute()

        @returns: True if all statements compiled successfully

        """

        success = True
        parent = self.parent_statement
        for statement in self.statements:
            statement.set_parent(parent)
            if not statement.compile():
                success = False
            parent = statement

        if not success:
            for statement in self.statements:
                self.emit('statement-complete', statement)
            self.emit('complete')

        return success

    def execute(self):
        """Execute the statements of the executor asynchronously in a thread."""
        self.tid = thread.start_new_thread(self.__run_thread, ())

    def interrupt(self):
        """Interrupts the execution of the executor if possible.

        Makes a best-effort attempt to interrupt the execution of the executor.
        An attempt is made to interrupt any blocking system calls, however if
        the execution is inside native code this may not be succesful.
        Long-running native code-computations will also not be interrupted.

        Once the thread is succesfully interrupted, execution finishes as per normal
        by emitting the ::statement-complete and ::complete signals, except that
        the state of the interrupted statement will be Statement.INTERRUPTED,
        and subsequence statements will have a state of Statement.COMPILE_SUCCESS.

        Calling interrupt() more than once will have no effect.

        """

        # See note in __run_thread() as to why we need to lock and why we need to
        # protect against sending the KeyboardInterrupt exception more than once
        self.lock.acquire()
        if not self.complete and not self.interrupted:
            self.interrupted = True
            _PyThreadState_SetAsyncExc(self.tid, ctypes.py_object(KeyboardInterrupt))
            if _pthread_kill != None:
                _pthread_kill(self.tid, signal.SIGUSR1)
        self.lock.release()

######################################################################

if __name__ == '__main__': #pragma: no cover
    gobject.threads_init()

    import stdout_capture
    stdout_capture.init()

    import time

    from notebook import Notebook
    from statement import Statement
    from test_utils import assert_equals
    from worksheet import Worksheet

    failed = False

    notebook = Notebook()
    worksheet = Worksheet(notebook)

    def test_execute(statements):
        executor = ThreadExecutor()

        for s, expected_state, expected_results in statements:
            statement = Statement(s, worksheet)
            statement._expected_state = expected_state
            statement._expected_results = expected_results
            executor.add_statement(statement)

        loop = gobject.MainLoop()

        def on_statement_complete(executor, statement):
            statement._got_state = statement.state
            statement._got_results = statement.results

        def on_complete(executor):
            loop.quit()

        def interrupt():
            executor.interrupt()

        global timed_out
        timed_out = False
        def timeout():
            global timed_out
            timed_out = True
            loop.quit()

        executor.connect('statement-complete', on_statement_complete)
        executor.connect('complete', on_complete)

        if executor.compile():
            executor.execute()
            interrupt_source = gobject.timeout_add(500, interrupt)
            timeout_source = gobject.timeout_add(1000, timeout)
            loop.run()
            if timed_out:
                raise AssertionError("Interrupting ThreadExecutor failed")
            gobject.source_remove(interrupt_source)
            gobject.source_remove(timeout_source)

        for s in executor.statements:
            assert_equals(s._got_state, s._expected_state)
            assert_equals(s._got_results, s._expected_results)

    test_execute(
        [
            ("a = 1", Statement.COMPILE_SUCCESS, None),
            ("a =", Statement.COMPILE_ERROR, None)
        ])

    test_execute(
        [
            ("a = 1", Statement.EXECUTE_SUCCESS, []),
            ("a", Statement.EXECUTE_SUCCESS, ['1'])
        ])

    test_execute(
        [
            ("a = 1", Statement.EXECUTE_SUCCESS, []),
            ("b", Statement.EXECUTE_ERROR, None),
            ("c = 2", Statement.COMPILE_SUCCESS, None)
        ])

    # Test interrupting straight python code
    test_execute(
        [
            ("y = 1", Statement.EXECUTE_SUCCESS, []),
            ("for x in xrange(0,100000000): y = y* 2", Statement.INTERRUPTED, None),
            ("z = 1", Statement.COMPILE_SUCCESS, None)
        ])

    # Test interrupting a blocking syscall, if support on this platform
    if _pthread_kill != None:
        test_execute(
            [
                ("import sys", Statement.EXECUTE_SUCCESS, []),
                ("sys.stdin.readline()", Statement.INTERRUPTED, None),
                ("z = 1", Statement.COMPILE_SUCCESS, None)
            ])
