# Copyright 2007 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import gtk
import os

from numpy import float32, float64

import reinteract.custom_result as custom_result

class PlayResult(custom_result.CustomResult):
    def __init__(self, data):
        self.__data = data

    def create_widget(self):
        widget = gtk.Button("Play")
        widget.connect('clicked', self.play)

        widget.connect('button_press_event', self.on_button_press)
        widget.connect('realize', self.on_realize)

        return widget

    def play(self, *args):
        if self.__data.dtype == float32:
            command = "play -t raw -r 44100 -f -4 -L -q -"
        else:
            command = "play -t raw -r 44100 -f -8 -L -q -"
            
        f = os.popen(command, 'w')
        self.__data.tofile(f)
        f.close()

    def __save(self, filename):
        escaped = filename.replace("'", r"'\''")
        
        if self.__data.dtype == float32:
            command = "sox -t raw -r 44100 -f -4 -L -q - '%s'" % escaped
        else:
            command = "sox -t raw -r 44100 -f -8 -L -q - '%s'" % escaped
            
        f = os.popen(command, 'w')
        self.__data.tofile(f)
        f.close()

    def on_button_press(self, button, event):
        if event.button == 3:
            custom_result.show_menu(button, event, save_callback=self.__save)
            return True
        return False

    def on_realize(self, button):
        # Hack to get the right cursor over the button, since the button
        # doesn't set a cursor itself. button.window is the text view's
        # window, we have to search to find button.event_window, since
        # its not bound
        for c in button.window.get_children():
            if c.get_user_data() == button:
                cursor = gtk.gdk.Cursor(gtk.gdk.LEFT_PTR)
                c.set_cursor(cursor)
    
def play(data):
    if data.dtype != float32 and data.dtype != float64:
        raise TypeError("Data must be float32 or float64, not %s", data.dtype)
    
    return PlayResult(data)
