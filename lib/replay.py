import gtk
import os

from numpy import float32, float64

from reinteract.custom_result import CustomResult

class PlayResult(CustomResult):
    def __init__(self, data):
        self.__data = data

    def create_widget(self):
        widget = gtk.Button("Play")
        widget.connect('clicked', self.play)

        return widget

    def play(self, *args):
        if self.__data.dtype == float32:
            command = 'play -t raw -r 44100 -f -4 -L -q -'
        else:
            command = 'play -t raw -r 44100 -f -8 -L -q -'
            
        f = os.popen(command, 'w')
        self.__data.tofile(f)
        f.close()
    
def play(data):
    if data.dtype != float32 and data.dtype != float64:
        raise TypeError("Data must be float32 or float64, not %s", data.dtype)
    
    return PlayResult(data)
