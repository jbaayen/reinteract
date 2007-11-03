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
        print repr(escaped)
        
        if self.__data.dtype == float32:
            command = "sox -t raw -r 44100 -f -4 -L -q - '%s'" % escaped
        else:
            command = "sox -t raw -r 44100 -f -8 -L -q - '%s'" % escaped
            
        f = os.popen(command, 'w')
        self.__data.tofile(f)
        f.close()

    def on_button_press(self, button, event):
        if event.button == 3:
            toplevel = button.get_toplevel()
        
            menu = gtk.Menu()
            menu_item = gtk.ImageMenuItem(stock_id=gtk.STOCK_SAVE_AS)
            menu_item.show()
            menu.add(menu_item)

            def on_selection_done(menu):
                menu.destroy()
            menu.connect('selection-done', on_selection_done)

            def on_activate(menu):
                chooser = gtk.FileChooserDialog("Save As...", toplevel, gtk.FILE_CHOOSER_ACTION_SAVE,
                                                (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                                 gtk.STOCK_SAVE,   gtk.RESPONSE_OK))
                chooser.set_default_response(gtk.RESPONSE_OK)
                response = chooser.run()
                filename = None
                if response == gtk.RESPONSE_OK:
                    filename = chooser.get_filename()

                chooser.destroy()
                
                if filename != None:
                    self.__save(filename)
                    
            menu_item.connect('activate', on_activate)
            
            menu.popup(None, None, None, event.button, event.time)
            
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
