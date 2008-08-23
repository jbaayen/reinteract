import gtk

import os

def _find_program_in_path(progname):
    try:
        path = os.environ['PATH']
    except KeyError:
        path = os.defpath

    for dir in path.split(os.pathsep):
        p = os.path.join(dir, progname)
        if os.path.exists(p):
            return p

    return None

def _find_url_open_program():
    for progname in ['xdg-open', 'htmlview', 'gnome-open']:
        path = _find_program_in_path(progname)
        if path != None:
            return path
    return None

def _open_url(dialog, url):
    prog = _find_url_open_program()
    os.spawnl(os.P_NOWAIT, prog, prog, url)

class AboutDialog(gtk.AboutDialog):
    def __init__(self, parent):
        gtk.AboutDialog.__init__(self)
        self.set_transient_for(parent)
        self.set_name("Reinteract")
        self.set_copyright("Copyright \302\251 2007-2008 Owen Taylor, Red Hat, Inc., and others")
        self.set_website("http://www.reinteract.org")
        self.connect("response", lambda d, r: d.destroy())

    def run(self):
        if _find_url_open_program() != None:
            gtk.about_dialog_set_url_hook(_open_url)

        gtk.AboutDialog.run(self)
