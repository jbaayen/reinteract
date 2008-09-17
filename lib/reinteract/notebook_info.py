from ConfigParser import RawConfigParser, ParsingError
import os
import time

def format_duration(past):
    if past < 60: # Sanity ... a date before 1972
        return ""

    now = time.time()

    diff = now - past
    if diff <= 0:
        return ""
    elif diff < 90:
        return "A minute ago"
    elif diff < 60 * 60:
        return "%.0f minutes ago" % (diff / 60.)
    elif diff < 24 * 60 * 60:
        return "%.0f hours ago" % (diff / (60. * 60.))

    time_struct = time.localtime(now)
    day_start = time.mktime((time_struct[0], time_struct[1], time_struct[2], 0, 0, 0, time_struct[6], time_struct[7], time_struct[8]))
    diff_days = (day_start - past) / (60. * 60. * 24.)

    if diff_days < 1:
        return "Yesterday"
    elif diff_days < 7:
        return "%.0f days ago" % (diff_days)
    elif diff_days < 10.5:
        return "1 week ago"
    elif diff_days < 30:
        return "%.0f weeks ago" % (diff_days / 7.)
    elif diff_days < 45:
        return "1 month ago"
    elif diff_days < 365:
        return "%.0f months ago" % (diff_days / 30.)
    elif diff_days < 550 * 1.5:
        return "1 year ago"
    else:
        return "%.0f years ago" % (diff_days / 365.)

class NotebookInfo(object):
    def __init__(self, folder):
        self.folder = folder
        self.__load()

    def __load(self):
        self.__parser = RawConfigParser()

        # Fallback with the modtime of the folder as "last_modified"
        st = os.stat(self.folder)
        self.__parser.add_section('Notebook')
        self.__parser.set('Notebook', 'last_modified', str(st.st_mtime))

        index_file = os.path.join(self.folder, "index.rnb")
        try:
            f = open(index_file, "r")
        except IOError, e:
            # If not readable, just ignore
            return

        try:
            self.__parser.readfp(f)
        except ParsingError:
            # If not readable, just ignore
            return
        finally:
            f.close()

    def __save(self):
        self.__parser.set('Notebook', 'last_modified', str(time.time()))
        index_file = os.path.join(self.folder, "index.rnb")

        f = open(index_file, "w")
        self.__parser.write(f)
        f.close()

    def update_last_modified(self):
        # last_modified is updated to the current time every time we save
        self.__save()

    @property
    def last_modified(self):
        if self.__parser.has_option('Notebook', 'last_modified'):
            return self.__parser.getfloat('Notebook', 'last_modified')
        return os.path.basename(self.folder)

    @property
    def last_modified_text(self):
        return format_duration(self.last_modified)

    @property
    def name(self):
        return os.path.basename(self.folder)

    def __get_description(self):
        if self.__parser.has_option('Notebook', 'description'):
            return self.__parser.get('Notebook', 'description')
        else:
            return ""

    def __set_description(self, description):
        self.__parser.set('Notebook', 'description', description)
        self.__save()

    description = property(__get_description, __set_description)
