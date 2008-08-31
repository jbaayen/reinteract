import os

import gtk

from global_settings import global_settings

class WindowBuilder:
    def __init__(self, name):
        filename = os.path.join(global_settings.dialogs_dir, name + ".xml")
        self.builder = gtk.Builder()
        self.builder.add_from_file(filename)

    def __getattr__(self, name):
        obj = self.builder.get_object(name)
        if obj:
            return obj
        else:
            raise AttributeError("%s instance has no attribute '%s'" % (self.__class__.__name__, name))
