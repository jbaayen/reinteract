import gtk

from ShellView import ShellView

w = gtk.Window()

v = gtk.VBox()
w.add(v)

sw = gtk.ScrolledWindow()
sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
v.pack_start(sw, expand=True, fill=True)

view = ShellView()
sw.add(view)

b = gtk.Button("Calculate")
v.pack_start(b, expand=False)

b.connect("clicked", lambda *kwargs: view.get_buffer().calculate())

w.set_default_size(300, 300)

w.show_all()

def on_key_press_event(window, event):
    if (event.keyval == 0xff0d or event.keyval == 0xff8d) and (event.state & gtk.gdk.CONTROL_MASK != 0):
        view.get_buffer().calculate()
        return True
    return False

def on_destroy(*args):
    gtk.main_quit()

w.connect('key-press-event', on_key_press_event)
w.connect('destroy', on_destroy)

gtk.main()
