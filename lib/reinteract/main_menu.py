import gobject

from about_dialog import AboutDialog
from application import application
from reinteract.native_main_menu import NativeMainMenu

class MainMenu(NativeMainMenu):
    """This class is an interface to OS X main menu. (The interface
    of this class could likely be used for other types of main menu
    if the need ever arises.)

    The actual heavy-lifting is done in the NativeMainMenu superclass
    which is implemented in the native-code wrapper application. Here
    we just forward activated menu items in one direction, and
    enable/disabling of menu items in the other direction.

    """

    def __init__(self):
        NativeMainMenu.__init__(self)
        self.__active_window = None

    def run_action(self, action_name):
        method_name = 'on_' + action_name.replace('-', '_')
        if self.__active_window and hasattr(self.__active_window, method_name):
            getattr(self.__active_window, method_name)(None)
        elif hasattr(self, method_name):
            getattr(self, method_name)()
        else:
            print action_name

    def do_action(self, action_name):
        # Recursing the main loop (which we do for various messages, etc), is a bad thing
        # to do out of a Quartz menu callback, so defer the real work to the next run of
        # the main loop
        gobject.idle_add(self.run_action, action_name, priority=gobject.PRIORITY_HIGH)

    def on_about(self):
        application.show_about_dialog()

    def on_new_notebook(self, action):
        application.create_notebook_dialog()

    def on_open_notebook(self, action):
        application.open_notebook_dialog()

    def on_quit(self):
        application.quit()

    def window_activated(self, window):
        self.__active_window = window

    def window_deactivated(self, window):
        if window == self.__active_window:
            self.__active_window = None

main_menu = MainMenu()
