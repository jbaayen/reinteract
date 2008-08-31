import copy
import gobject
import imp
import os
import sys

from notebook_info import NotebookInfo

# Used to give each notebook a unique namespace
_counter = 1

# Hook the import function in the global __builtin__ module; this is used to make
# imports from a notebook locally scoped to that notebook. We do it this way
# rather than replacing __builtins__ to avoid triggering restricted mode.
import __builtin__
saved_import = __builtin__.__import__
def reinteract_import(name, globals=None, locals=None, fromlist=None, level=-1):
    if globals and '__reinteract_notebook' in globals:
        return globals['__reinteract_notebook'].do_import(name, globals, locals, fromlist, level)
    else:
        return saved_import(name, globals, locals, fromlist, level)

__builtin__.__import__ = reinteract_import

class HelpResult:
    def __init__(self, arg):
        self.arg = arg

class _Helper:
    # We use a callable object here rather than a function so that we handle
    # help without arguments, just like the help builtin
    def __repr__(self):
        return "Type help(object) for help about object"

    def __call__(self, arg=None):
        if arg == None:
            return self
        
        return HelpResult(arg)

######################################################################

class NotebookFile(gobject.GObject):
    worksheet = gobject.property(type=gobject.TYPE_PYOBJECT)

    def __init__(self, path):
        gobject.GObject.__init__(self)
        self.path = path

class WorksheetFile(NotebookFile):
    pass

class LibraryFile(NotebookFile):
    pass

class MiscFile(NotebookFile):
    pass

######################################################################

class Notebook(gobject.GObject):
    __gsignals__ = {
        'files-changed': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ())
    }

    def __init__(self, folder=None):
        gobject.GObject.__init__(self)

        global _counter

        self.__prefix = "__reinteract" + str(_counter)
        _counter += 1


        self.folder = folder

        if folder:
            path = [folder]
        else:
            path = []

        self.__path = path
        self.__modules = {}

        self.__root_module = imp.new_module(self.__prefix)
        self.__root_module.path = path
        sys.modules[self.__prefix] = self.__root_module

        self.files = {}
        self.worksheets = set()

        if folder:
            self.info = NotebookInfo(folder)
        else:
            self.info = None

        self.refresh()

    ############################################################
    # Loading and Saving
    ############################################################

    def __load_files(self, folder, old_files, new_files):
        if folder:
            full_folder = os.path.join(self.folder, folder)
        else:
            full_folder = self.folder

        files_added = False

        for f in os.listdir(full_folder):
            if folder == None and f == "index.rnb":
                continue

            if folder:
                relative = os.path.join(folder, f)
            else:
                relative = f

            full_path = os.path.join(full_folder, f)

            if os.path.isdir(full_path):
                files_added = self.__load_files(relative, old_files, new_files) or files_added
            elif relative in old_files:
                new_files[relative] = old_files[relative]
                del old_files[relative]
            elif f.endswith('~'):
                pass
            else:
                if f.endswith('.rws') or f.endswith('.RWS'):
                    file = WorksheetFile(relative)
                    absolute = os.path.join(full_folder, f)
                    for worksheet in self.worksheets:
                        if os.path.abspath(worksheet.filename) == absolute:
                            file.worksheet = worksheet
                            break
                elif f.endswith('.py') or f.endswith('.PY'):
                    file = LibraryFile(relative)
                else:
                    file = MiscFile(relative)
                new_files[relative] = file
                files_added = True

        return files_added

    ############################################################
    # Import handling
    ############################################################

    def __reset_all_modules(self):
        for (name, module) in enumerate(self.__modules):
            del sys.modules[self.__prefix + "." + name]

    def reset_module_by_filename(self, filename):
        for (name, module) in enumerate(self.__modules):
            if module.__filename__ == filename:
                del sys.modules[self.__prefix + "." + name]
                del self.__modules[name]
                return module

    def __load_local_module(self, fullname, f, pathname, description):
        prefixed = self.__prefix + "." + fullname
        
        # Trick ... to change the builtins array for the module we are about
        # to load, we stick an empty module initialized the way we want into
        # sys.modules and count on imp.load_module() finding that and doing
        # the rest of the loading into that module

        new = imp.new_module(prefixed)
        self.setup_globals(new.__dict__)
        
        assert not prefixed in sys.modules
        sys.modules[prefixed] = new
        result =  imp.load_module(prefixed, f, pathname, description)
        assert result == new
        
        return result

    def __find_and_load(self, fullname, name, parent=None, local=None):
        if parent == None:
            assert local == None
            try:
                f, pathname, description = imp.find_module(name, self.__path)
                local = True
            except ImportError:
                f, pathname, description = imp.find_module(name)
                local = False
        else:
            assert local != None
            f, pathname, description = imp.find_module(name, parent.__path__)

        try:
            if local:
                module = self.__load_local_module(fullname, f, pathname, description)
                self.__modules[name] = module
            else:
                module = imp.load_module(fullname, f, pathname, description)

            if parent != None:
                parent.__dict__[name] = module
        finally:
            if f != None:
                f.close()

        return module, local
        
    def __import_recurse(self, names):
        fullname = ".".join(names)
        
        try:
            return self.__modules[fullname], True
        except KeyError:
            pass
        
        try:
            return sys.modules[fullname], False
        except KeyError:
            pass

        if len(names) == 1:
            module, local = self.__find_and_load(fullname, names[-1])
        else:
            parent, local = self.__import_recurse(names[0:-1])
            module, _ = self.__find_and_load(fullname, names[-1], parent=parent, local=local)

        return module, local

    def __ensure_from_list_item(self, fullname, fromname, module, local):
        if fromname == "*": # * inside __all__, ignore
            return
        
        if not isinstance(fromname, basestring):
            raise TypeError("Item in from list is not a string")
        
        try:
            getattr(module, fromname)
        except AttributeError:
            self.__find_and_load(fullname + "." + fromname, fromname, parent=module, local=local)
        
    def do_import(self, name, globals=None, locals=None, fromlist=None, level=None):
        names = name.split('.')
        
        module, local =  self.__import_recurse(names)
        
        if fromlist != None:
            # In 'from a.b import c', if a.b.c doesn't exist after loading a.b, The built-in
            # __import__ will try to load a.b.c as a module; do the same here.
            for fromname in fromlist:
                if fromname == "*":
                    try:
                        all = getattr(module, "__all__")
                        for allname in all:
                            self.__ensure_from_list_item(name, allname, module, local)
                    except AttributeError:
                        pass
                else:
                    self.__ensure_from_list_item(name, fromname, module, local)
                            
            return module
        elif local:
            return self.__modules[names[0]]
        else:
            return sys.modules[names[0]]

    ############################################################
    # Worksheet tracking
    #############################################################

    def on_worksheet_notify_filename(self, worksheet, *args):
        old_file = None
        new_file = None
        for file in self.files.values():
            if file.worksheet == worksheet:
                old_file = file

            if worksheet.filename and os.path.abspath(os.path.join(self.folder, file.path)) == os.path.abspath(worksheet.filename):
                new_file = file

        if old_file != new_file:
            if old_file:
                old_file.worksheet = None

            if new_file:
                new_file.worksheet = worksheet

    def _add_worksheet(self, worksheet):
        # Called from Worksheet
        self.worksheets.add(worksheet)
        worksheet._notebook_filename_changed_handler = worksheet.connect('notify::filename', self.on_worksheet_notify_filename)

    def _remove_worksheet(self, worksheet):
        # Called from Worksheet
        worksheet.disconnect(worksheet._notebook_filename_changed_handler)
        del worksheet._notebook_filename_changed_handler
        self.worksheets.remove(worksheet)

        for file in self.files.values():
            if file.worksheet == worksheet:
                file.worksheet = None

    ############################################################
    # Public API
    ############################################################

    def refresh(self):
        if not self.folder:
            return

        old_files = self.files
        self.files = {}
        files_added = self.__load_files(None, old_files, self.files)
        if files_added or len(old_files) > 0:
            self.emit('files-changed')

    def set_path(self, path):
        if path != self.__path:
            self.__path = path
            self.__root_module.path = path
            self.__reset_all_modules()

    def setup_globals(self, globals):
        globals['__reinteract_notebook'] = self
        globals['help'] = _Helper()

    def save(self):
        pass
    
if __name__ == '__main__':
    import copy
    import os
    import tempfile

    base = tempfile.mkdtemp("", "shell_buffer")
    
    def cleanup():
        for root, dirs, files in os.walk(base, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))

    def cleanup_pyc():
        # Not absolutely necessary, but makes things less confusing if we do
        # this between tests
        for root, dirs, files in os.walk(base, topdown=False):
            for name in files:
                if name.endswith(".pyc"):
                    os.remove(os.path.join(root, name))
                
    def write_file(name, contents):
        absname = os.path.join(base, name)
        dirname = os.path.dirname(absname)
        try:
            os.makedirs(dirname)
        except:
            pass

        f = open(absname, "w")
        f.write(contents)
        f.close()

    def do_test(import_text, evaluate_text, expected):
        nb = Notebook(path=[base])

        scope = {}
        nb.setup_globals(scope)
        
        exec import_text in scope
        result = eval(evaluate_text, scope)

        if result != expected:
            raise AssertionError("Got '%s', expected '%s'" % (result, expected))

        cleanup_pyc()

    try:
        write_file("mod1.py", "a = 1")
        write_file("package1/__init__.py", "__all__ = ['mod2']")
        write_file("package1/mod2.py", "b = 2")
        write_file("package2/__init__.py", "")
        write_file("package2/mod3.py", "import package1.mod2\nc = package1.mod2.b + 1")

        do_test("import mod1", "mod1.__file__", os.path.join(base, "mod1.py"))

        do_test("import mod1", "mod1.a", 1)
        do_test("import mod1 as m", "m.a", 1)
        do_test("from mod1 import a", "a", 1)
        do_test("from mod1 import a as a2", "a2", 1)

        do_test("import package1.mod2", "package1.mod2.b", 2)
        do_test("import package1.mod2 as m", "m.b", 2)
        do_test("from package1 import mod2", "mod2.b", 2)
        do_test("from package1 import *", "mod2.b", 2)

        # http://www.reinteract.org/trac/ticket/5
        do_test("import package2.mod3", "package2.mod3.c", 3)
    finally:
        cleanup()
