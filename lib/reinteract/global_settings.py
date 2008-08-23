# This module holds preferences and options that are global to the entire program.

import gobject

class GlobalSettings(gobject.GObject):
    use_hildon = gobject.property(type=bool, default=False)

global_settings = GlobalSettings()
