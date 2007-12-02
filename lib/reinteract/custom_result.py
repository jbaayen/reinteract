import gtk

class CustomResult(object):
    def create_widget(self):
        raise NotImplementedError

def show_menu(widget, event, save_callback=None):
    """Convenience function to create a right-click menu with a Save As option"""

    toplevel = widget.get_toplevel()
        
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
            save_callback(filename)
                    
    menu_item.connect('activate', on_activate)
    menu.popup(None, None, None, event.button, event.time)
