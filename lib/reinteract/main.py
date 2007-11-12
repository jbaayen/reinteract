import gtk
import pango

import os
import sys
import gettext
from gettext import gettext as _

from notebook import Notebook
from shell_buffer import ShellBuffer
from shell_view import ShellView

from format_escaped import format_escaped


notebook = Notebook()
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
    if not confirm_discard(_('Save the unchanged changes to worksheet "%s" before quitting?'), _('_Quit without saving')):
        return
    gtk.main_quit()

def on_quit(action):
    quit()

def on_cut(action):
    buf.cut_clipboard(view.get_clipboard(gtk.gdk.SELECTION_CLIPBOARD), view.get_editable())

def on_copy(action):
    buf.copy_clipboard(view.get_clipboard(gtk.gdk.SELECTION_CLIPBOARD))

def on_paste(action):
    buf.paste_clipboard(view.get_clipboard(gtk.gdk.SELECTION_CLIPBOARD), None, view.get_editable())

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
    
    buf.load(filename)
    calculate()

def on_open(action):
    if not confirm_discard('Discard unsaved changes to worksheet "%s"?', '_Discard'):
        return
    
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
    ('new',     gtk.STOCK_NEW,       None,         None,              None, on_new),
    ('open',    gtk.STOCK_OPEN,      None,         None,              None, on_open),
    ('save',    gtk.STOCK_SAVE,      None,         None,              None, on_save),
    ('save-as', gtk.STOCK_SAVE_AS,   None,         None,              None, on_save_as),
    ('quit',    gtk.STOCK_QUIT,      None,         None,              None, on_quit),
    ('cut',     gtk.STOCK_CUT,       None,         None,              None, on_cut),
    ('copy',    gtk.STOCK_COPY,      None,         None,              None, on_copy),
    ('paste',   gtk.STOCK_PASTE,     None,         None,              None, on_paste),
    ('delete',  gtk.STOCK_DELETE,    None,         None,              None, on_delete),
    ('calculate', gtk.STOCK_REFRESH, "_Calculate", '<control>Return', None, on_calculate),
])

ui_manager.insert_action_group(action_group, 0)

ui_manager.add_ui_from_string("""
<ui>
   <menubar name="MenuBar">
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
         <menuitem action="paste"/>
         <menuitem action="delete"/>
         <separator/>
         <menuitem action="calculate"/>
      </menu>
   </menubar>
   <toolbar name="ToolBar">
      <toolitem action="calculate"/>
   </toolbar>
</ui>
""")

ui_manager.ensure_update()

v.pack_start(ui_manager.get_widget("/MenuBar"), expand=False, fill=False)
v.pack_start(ui_manager.get_widget("/ToolBar"), expand=False, fill=False)

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

if len(sys.argv) > 1:
    load(sys.argv[1])

w.show()

def on_delete_event(window, event):
    quit()
    return True

w.connect('delete-event', on_delete_event)

gtk.main()
