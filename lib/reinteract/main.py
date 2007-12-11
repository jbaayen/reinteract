import gtk
import pango

import os
import sys

from notebook import Notebook
from shell_buffer import ShellBuffer
from shell_view import ShellView

from format_escaped import format_escaped
from optparse import OptionParser

usage = "usage: %prog [options]"
op = OptionParser(usage=usage)
op.add_option("-u", "--ui", type="choice", choices=("standard", "hildon"),
              default="standard",  help=("which user interface to use (standard or "
					 "hildon), default=%default"))

options, args = op.parse_args()
use_hildon = False

if options.ui == "hildon":
    try:
        import hildon
        use_hildon = True
    except ImportError, e:
        print "Error importing hildon. Falling back to standard ui."

notebook = Notebook()

if use_hildon:
    w = hildon.Window()
else:
    w = gtk.Window()

v = gtk.VBox()
w.add(v)

buf = ShellBuffer(notebook)
view = ShellView(buf)
view.modify_font(pango.FontDescription("monospace"))
buf = view.get_buffer()

ui_manager = gtk.UIManager()
w.add_accel_group(ui_manager.get_accel_group())

def quit():
    if not confirm_discard('Save the unchanged changes to worksheet "%s" before quitting?', '_Quit without saving'):
        return
    gtk.main_quit()

def on_quit(action):
    quit()

def on_cut(action):
    view.emit('cut-clipboard')

def on_copy(action):
    view.emit('copy-clipboard')

def on_copy_as_doctests(action):
    view.get_buffer().copy_as_doctests(view.get_clipboard(gtk.gdk.SELECTION_CLIPBOARD))

def on_paste(action):
    view.emit('paste-clipboard')

def on_delete(action):
    buf.delete_selection(True, view.get_editable())

def confirm_discard(message_format, continue_button_text):
    if not buf.code_modified:
        return True

    if buf.filename == None:
        save_button_text = gtk.STOCK_SAVE_AS
    else:
        save_button_text = gtk.STOCK_SAVE

    if buf.filename == None:
        name = "Unsaved Worksheet"
    else:
        name = buf.filename
        
    message = format_escaped("<big><b>" + message_format + "</b></big>", name)
    
    dialog = gtk.MessageDialog(parent=w, buttons=gtk.BUTTONS_NONE,
                               type=gtk.MESSAGE_WARNING)
    dialog.set_markup(message)
                            
    dialog.add_buttons(continue_button_text, gtk.RESPONSE_OK,
                       gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                       save_button_text, 1)
    dialog.set_default_response(1)
    response = dialog.run()
    dialog.destroy()

    if response == gtk.RESPONSE_OK:
        return True
    elif response == 1:
        if buf.filename == None:
            save_as()
        else:
            buf.save()

        if buf.code_modified:
            return False
        else:
            return True
    else:
        return False
    
def on_new(action):
    if not confirm_discard('Discard unsaved changes to worksheet "%s"?', '_Discard'):
        return
    
    buf.clear()

def load(filename):
    notebook.set_path([os.path.dirname(os.path.abspath(filename))])
    if not os.path.exists(filename):
        buf.filename = filename
        update_title()
    else:
        buf.load(filename)
        calculate()

def on_open(action):
    if not confirm_discard('Discard unsaved changes to worksheet "%s"?', '_Discard'):
        return
    
    if use_hildon:
        chooser = hildon.FileChooserDialog(w, gtk.FILE_CHOOSER_ACTION_OPEN)
    else:
        chooser = gtk.FileChooserDialog("Open Worksheet...", w, gtk.FILE_CHOOSER_ACTION_OPEN,
                                        (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                         gtk.STOCK_OPEN,   gtk.RESPONSE_OK))
    chooser.set_default_response(gtk.RESPONSE_OK)
    response = chooser.run()
    filename = None
    if response == gtk.RESPONSE_OK:
        filename = chooser.get_filename()

    if filename != None:
        load(filename)

    chooser.destroy()

def on_save(action):
    if buf.filename == None:
        on_save_as(action)
    else:
        buf.save()

def save_as():
    if use_hildon:
        chooser = hildon.FileChooserDialog(w, gtk.FILE_CHOOSER_ACTION_SAVE)
    else:
        chooser = gtk.FileChooserDialog("Save As...", w, gtk.FILE_CHOOSER_ACTION_SAVE,
                                        (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                         gtk.STOCK_SAVE,   gtk.RESPONSE_OK))
    chooser.set_default_response(gtk.RESPONSE_OK)
    response = chooser.run()
    filename = None
    if response == gtk.RESPONSE_OK:
        filename = chooser.get_filename()

    if filename != None:
        buf.save(filename)
        notebook.set_path([os.path.dirname(os.path.abspath(filename))])

    chooser.destroy()
        
def on_save_as(action):
    save_as()

def find_program_in_path(progname):
    try:
        path = os.environ['PATH']
    except KeyError:
        path = os.defpath

    for dir in path.split(os.pathsep):
        p = os.path.join(dir, progname)
        if os.path.exists(p):
            return p

    return None

def find_url_open_program():
    for progname in ['xdg-open', 'htmlview', 'gnome-open']:
        path = find_program_in_path(progname)
        if path != None:
            return path
    return None
    
def open_url(dialog, url):
    prog = find_url_open_program()
    os.spawnl(os.P_NOWAIT, prog, prog, url)
    
def on_about(action):
    if find_url_open_program() != None:
        gtk.about_dialog_set_url_hook(open_url)
    
    dialog = gtk.AboutDialog()
    dialog.set_transient_for(w)
    dialog.set_name("Reinteract")
    dialog.set_copyright("Copyright \302\251 2007 Owen Taylor, Red Hat, Inc., and others")
    dialog.set_website("http://www.reinteract.org")
    dialog.connect("response", lambda d, r: d.destroy())
    dialog.run()

def calculate():
    buf.calculate()

    # This is a hack to work around the fact that scroll_mark_onscreen()
    # doesn't wait for a size-allocate cycle, so doesn't properly handle
    # embedded request widgets
    w, h = view.size_request()
    view.size_allocate((view.allocation.x, view.allocation.y, w, h))
    
    view.scroll_mark_onscreen(buf.get_insert())
    
def on_calculate(action):
    calculate()

action_group = gtk.ActionGroup("main")
action_group.add_actions([
    ('file',    None,                "_File"),
    ('edit',    None,                "_Edit"),
    ('help',   	None,                "_Help"),
    ('new',     gtk.STOCK_NEW,       None,         None,              None, on_new),
    ('open',    gtk.STOCK_OPEN,      None,         None,              None, on_open),
    ('save',    gtk.STOCK_SAVE,      None,         None,              None, on_save),
    ('save-as', gtk.STOCK_SAVE_AS,   None,         None,              None, on_save_as),
    ('quit',    gtk.STOCK_QUIT,      None,         None,              None, on_quit),
    ('cut',     gtk.STOCK_CUT,       None,         None,              None, on_cut),
    ('copy',    gtk.STOCK_COPY,      None,         None,              None, on_copy),
    ('copy-as-doctests',
     gtk.STOCK_COPY,
     "Copy as _Doctests",
     "<control><shift>c",
     None,
     on_copy_as_doctests),
    ('paste',   gtk.STOCK_PASTE,     None,         None,              None, on_paste),
    ('delete',  gtk.STOCK_DELETE,    None,         None,              None, on_delete),
    ('about',   gtk.STOCK_ABOUT,      None,         None,              None, on_about),
    ('calculate', gtk.STOCK_REFRESH, "_Calculate", '<control>Return', None, on_calculate),
])

ui_manager.insert_action_group(action_group, 0)

if use_hildon:
    menu_element = 'popup'
else:
    menu_element = 'menubar'

ui_string="""
<ui>
   <%(menu_element)s name="TopMenu">
      <menu action="file">
         <menuitem action="new"/>
         <menuitem action="open"/>
         <separator/>
         <menuitem action="save"/>
         <menuitem action="save-as"/>
         <separator/>
         <menuitem action="quit"/>
      </menu>
      <menu action="edit">
         <menuitem action="cut"/>
         <menuitem action="copy"/>
         <menuitem action="copy-as-doctests"/>
         <menuitem action="paste"/>
         <menuitem action="delete"/>
         <separator/>
         <menuitem action="calculate"/>
      </menu>
	<menu action="help">
        <menuitem action="about"/>
      </menu>
   </%(menu_element)s>
   <toolbar name="ToolBar">
      <toolitem action="calculate"/>
   </toolbar>
</ui>
""" % { 'menu_element': menu_element }

ui_manager.add_ui_from_string(ui_string)
ui_manager.ensure_update()

menu = ui_manager.get_widget("/TopMenu")
toolbar = ui_manager.get_widget("/ToolBar")

if use_hildon:
    w.set_menu(menu)
    w.add_toolbar(toolbar)
else:
    v.pack_start(menu, expand=False, fill=False)
    v.pack_start(toolbar, expand=False, fill=False)

sw = gtk.ScrolledWindow()
sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
v.pack_start(sw, expand=True, fill=True)

sw.add(view)

w.set_default_size(700, 800)

v.show_all()
view.grab_focus()

def update_title(*args):
    if buf.code_modified:
        title = "*"
    else:
        title = ""
    
    if buf.filename == None:
        title += "Unsaved Worksheet"
    else:
        title += os.path.basename(buf.filename)
    
    title += " - Reinteract"

    w.set_title(title)

buf.connect('filename-changed', update_title)
buf.connect('code-modified-changed', update_title)

update_title()

# We have a <Control>Return accelerator, but this hooks up <Control>KP_Enter as well;
# maybe someone wants that
def on_key_press_event(window, event):
    if (event.keyval == 0xff0d or event.keyval == 0xff8d) and (event.state & gtk.gdk.CONTROL_MASK != 0):
        calculate()
        return True
    return False

w.connect('key-press-event', on_key_press_event)

if len(args) > 0:
    load(args[0])
else:
    # If you run reinteract from the command line, you'd expect to be able to
    # create a worksheet, test it, then save it in the current directory, and
    # have that act the same as loading the worksheet to start with. This is
    # less obviously right when run from a menu item.
    notebook.set_path([os.getcwd()])
    
if use_hildon:
    settings = w.get_settings()
    settings.set_property("gtk-button-images", False)
    settings.set_property("gtk-menu-images", False)

w.show()

def on_delete_event(window, event):
    quit()
    return True

w.connect('delete-event', on_delete_event)

gtk.main()
