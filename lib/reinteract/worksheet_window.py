import gtk
import pango

import os
import sys

from about_dialog import AboutDialog
from global_settings import global_settings
from notebook import Notebook
from shell_buffer import ShellBuffer, ADJUST_BEFORE
from shell_view import ShellView

from format_escaped import format_escaped

_UI_STRING="""
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
"""

class WorksheetWindow:
    def __init__(self):
        self.use_hildon = False

        if global_settings.use_hildon:
            global hildon
            import hildon

        if global_settings.use_hildon:
            self.window = hildon.Window()
        else:
            self.window = gtk.Window()

        self.notebook = Notebook()

        main_vbox = gtk.VBox()
        self.window.add(main_vbox)

        ui_manager = gtk.UIManager()
        self.window.add_accel_group(ui_manager.get_accel_group())

        action_group = gtk.ActionGroup("main")
        action_group.add_actions([
            ('file',    None,                "_File"),
            ('edit',    None,                "_Edit"),
            ('help',   	None,                "_Help"),
            ('new',     gtk.STOCK_NEW,       None,         None,              None, self.on_new),
            ('open',    gtk.STOCK_OPEN,      None,         None,              None, self.on_open),
            ('save',    gtk.STOCK_SAVE,      None,         None,              None, self.on_save),
            ('save-as', gtk.STOCK_SAVE_AS,   None,         None,              None, self.on_save_as),
            ('quit',    gtk.STOCK_QUIT,      None,         None,              None, self.on_quit),
            ('cut',     gtk.STOCK_CUT,       None,         None,              None, self.on_cut),
            ('copy',    gtk.STOCK_COPY,      None,         None,              None, self.on_copy),
            ('copy-as-doctests',
             gtk.STOCK_COPY,
             "Copy as Doc_tests",
             "<control><shift>c",
             None,
             self.on_copy_as_doctests),
            ('paste',   gtk.STOCK_PASTE,     None,         None,              None,  self.on_paste),
            ('delete',  gtk.STOCK_DELETE,    None,         None,              None,  self.on_delete),
            ('about',   gtk.STOCK_ABOUT,      None,         None,              None, self.on_about),
            ('calculate', gtk.STOCK_REFRESH, "Ca_lculate", '<control>Return', None,  self.on_calculate),
        ])

        ui_manager.insert_action_group(action_group, 0)

        if global_settings.use_hildon:
            menu_element = 'popup'
        else:
            menu_element = 'menubar'

        ui_manager.add_ui_from_string(_UI_STRING % { 'menu_element': menu_element })
        ui_manager.ensure_update()

        menu = ui_manager.get_widget("/TopMenu")
        toolbar = ui_manager.get_widget("/ToolBar")

        if global_settings.use_hildon:
            self.window.set_menu(menu)
            self.window.add_toolbar(toolbar)
        else:
            main_vbox.pack_start(menu, expand=False, fill=False)
            main_vbox.pack_start(toolbar, expand=False, fill=False)

        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        main_vbox.pack_start(sw, expand=True, fill=True)

        self.buf = ShellBuffer(self.notebook)
        self.view = ShellView(self.buf)
        self.view.modify_font(pango.FontDescription("monospace"))

        sw.add(self.view)

        self.window.set_default_size(700, 800)

        main_vbox.show_all()
        self.view.grab_focus()

        self.buf.worksheet.connect('notify::filename', self.__update_title)
        self.buf.worksheet.connect('notify::code-modified', self.__update_title)

        self.__update_title()

        self.window.connect('key-press-event', self.on_key_press_event)
        self.window.connect('delete-event', self.on_delete_event)

        if global_settings.use_hildon:
            settings = self.window.get_settings()
            settings.set_property("gtk-button-images", False)
            settings.set_property("gtk-menu-images", False)

    #######################################################
    # Utility
    #######################################################

    def __save_as(self):
        if global_settings.use_hildon:
            chooser = hildon.FileChooserDialog(w, gtk.FILE_CHOOSER_ACTION_SAVE)
        else:
            chooser = gtk.FileChooserDialog("Save As...", self.window, gtk.FILE_CHOOSER_ACTION_SAVE,
                                            (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                             gtk.STOCK_SAVE,   gtk.RESPONSE_OK))
        chooser.set_default_response(gtk.RESPONSE_OK)
        response = chooser.run()
        filename = None
        if response == gtk.RESPONSE_OK:
            filename = chooser.get_filename()

        if filename != None:
            self.buf.worksheet.save(filename)
            self.notebook.set_path([os.path.dirname(os.path.abspath(filename))])

        chooser.destroy()

    def __update_title(self, *args):
        if self.buf.worksheet.code_modified:
            title = "*"
        else:
            title = ""

        if self.buf.worksheet.filename == None:
            title += "Unsaved Worksheet"
        else:
            title += os.path.basename(self.buf.worksheet.filename)

        title += " - Reinteract"

        self.window.set_title(title)

    def __confirm_discard(self, message_format, continue_button_text):
        if not self.buf.worksheet.code_modified:
            return True

        if self.buf.worksheet.filename == None:
            save_button_text = gtk.STOCK_SAVE_AS
        else:
            save_button_text = gtk.STOCK_SAVE

        if self.buf.worksheet.filename == None:
            name = "Unsaved Worksheet"
        else:
            name = self.buf.worksheet.filename

        message = format_escaped("<big><b>" + message_format + "</b></big>", name)

        dialog = gtk.MessageDialog(parent=self.window, buttons=gtk.BUTTONS_NONE,
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
            if self.buf.worksheet.filename == None:
                self.__save_as()
            else:
                self.buf.worksheet.save()

            if self.buf.worksheet.code_modified:
                return False
            else:
                return True
        else:
            return False

    def quit(self):
        if not self.__confirm_discard('Save the unchanged changes to worksheet "%s" before quitting?', '_Quit without saving'):
            return
        gtk.main_quit()

    #######################################################
    # Callbacks
    #######################################################

    def on_quit(self, action):
        self.quit()

    def on_cut(self, action):
        self.view.emit('cut-clipboard')

    def on_copy(self, action):
        self.view.emit('copy-clipboard')

    def on_copy_as_doctests(self, action):
        self.view.copy_as_doctests()

    def on_paste(self, action):
        self.view.emit('paste-clipboard')

    def on_delete(self, action):
        self.buf.delete_selection(True, self.view.get_editable())

    def on_new(self, action):
        if not self.__confirm_discard('Discard unsaved changes to worksheet "%s"?', '_Discard'):
            return

        self.buf.worksheet.clear()

    def on_open(self, action):
        if not self.__confirm_discard('Discard unsaved changes to worksheet "%s"?', '_Discard'):
            return

        if global_settings.use_hildon:
            chooser = hildon.FileChooserDialog(self.window, gtk.FILE_CHOOSER_ACTION_OPEN)
        else:
            chooser = gtk.FileChooserDialog("Open Worksheet...", self.window, gtk.FILE_CHOOSER_ACTION_OPEN,
                                            (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                             gtk.STOCK_OPEN,   gtk.RESPONSE_OK))
        chooser.set_default_response(gtk.RESPONSE_OK)
        response = chooser.run()
        filename = None
        if response == gtk.RESPONSE_OK:
            filename = chooser.get_filename()

        if filename != None:
            self.load(filename)

        chooser.destroy()

    def on_save(self, action):
        if self.buf.worksheet.filename == None:
            self.__save_as()
        else:
            self.buf.worksheet.save()

    def on_save_as(self, action):
        self.__save_as()

    def on_about(self, action):
        d = AboutDialog(self.window)
        d.run()

    def on_calculate(self, action):
        self.view.calculate()

    def on_key_press_event(self, window, event):
        # We have a <Control>Return accelerator, but this hooks up <Control>KP_Enter as well;
        # maybe someone wants that
        if (event.keyval == gtk.keysyms.Return or event.keyval == gtk.keysyms.KP_Enter) and (event.state & gtk.gdk.CONTROL_MASK != 0):
            self.view.calculate()
            return True
        return False

    def on_delete_event(self, window, event):
        self.quit()
        return True

    #######################################################
    # Public API
    #######################################################

    def show(self):
        self.window.show()

    def load(self, filename):
        self.notebook.set_path([os.path.dirname(os.path.abspath(filename))])
        if not os.path.exists(filename):
            # FIXME
            self.buf.worksheet.filename = filename
        else:
            self.buf.worksheet.load(filename)
            self.buf.place_cursor(self.buf.get_start_iter())
            self.view.calculate()
