# Copyright 2007-2009 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import gobject
import gtk
import re
from shell_buffer import ShellBuffer, ADJUST_NONE, ADJUST_BEFORE, ADJUST_AFTER
from chunks import StatementChunk, CommentChunk, BlankChunk
from completion_popup import CompletionPopup
from doc_popup import DocPopup
from global_settings import global_settings
from notebook import NotebookFile
import sanitize_textview_ipc

LEFT_MARGIN_WIDTH = 10

ALL_WHITESPACE_RE = re.compile("^\s*$")

class ShellView(gtk.TextView):
    __gsignals__ = {
        'backspace' : 'override',
        'expose-event': 'override',
        'focus-out-event': 'override',
        'button-press-event': 'override',
        'button-release-event': 'override',
        'motion-notify-event': 'override',
        'key-press-event': 'override',
        'leave-notify-event': 'override',
        'motion-notify-event': 'override',
        'realize': 'override',
        'unrealize': 'override',
        'size-allocate': 'override'
   }
        
    def __init__(self, buf):
        self.edit_only = buf.worksheet.edit_only

        if not self.edit_only:
            buf.worksheet.connect('chunk-inserted', self.on_chunk_inserted)
            buf.worksheet.connect('chunk-changed', self.on_chunk_changed)
            buf.worksheet.connect('chunk-status-changed', self.on_chunk_status_changed)
            buf.worksheet.connect('notify::state', self.on_notify_state)

            # Track changes to update completion
            buf.connect_after('insert-text', self.on_after_insert_text)
            buf.connect_after('delete-range', self.on_after_delete_range)
            buf.connect_after('end-user-action', self.on_after_end_user_action)

            self.__inserted_in_user_action = False
            self.__deleted_in_user_action = False

        buf.connect('add-custom-result', self.on_add_custom_result)
        buf.connect('pair-location-changed', self.on_pair_location_changed)
            
        gtk.TextView.__init__(self, buf)
        if not self.edit_only:
            self.set_border_window_size(gtk.TEXT_WINDOW_LEFT, LEFT_MARGIN_WIDTH)
        self.set_left_margin(2)

        # Attach a "behavior object" to the view which, by ugly hacks, makes it
        # do simply and reasonable things for cut-and-paste and DND
        sanitize_textview_ipc.sanitize_view(self)

        self.add_events(gtk.gdk.LEAVE_NOTIFY_MASK)

        self.__completion_popup = CompletionPopup(self)
        self.__doc_popup = DocPopup()
        self.__mouse_over_object = None
        self.__mouse_over_timeout = None

        self.__mouse_over_start = buf.create_mark(None, buf.get_start_iter(), True)

        self.__arg_highlight_start = None
        self.__arg_highlight_end = None
        buf.connect('mark-set', self.on_mark_set)

    def __get_worksheet_line_yrange(self, line):
        buffer_line = self.get_buffer().pos_to_iter(line)
        return self.get_line_yrange(buffer_line)

    def __get_worksheet_line_at_y(self, y, adjust):
        buf = self.get_buffer()
        (buffer_line, _) = self.get_line_at_y(y)
        return buf.iter_to_pos(buffer_line, adjust)[0]

    def paint_chunk(self, cr, area, chunk, fill_color, outline_color):
        buf = self.get_buffer()
        
        (y, _) = self.__get_worksheet_line_yrange(chunk.start)
        (end_y, end_height) = self.__get_worksheet_line_yrange(chunk.end - 1)
        height = end_y + end_height - y
        
        (_, window_y) = self.buffer_to_window_coords(gtk.TEXT_WINDOW_LEFT, 0, y)
        cr.rectangle(area.x, window_y, area.width, height)
        cr.set_source_rgb(*fill_color)
        cr.fill()
                
        cr.rectangle(0.5, window_y + 0.5, LEFT_MARGIN_WIDTH - 1, height - 1)
        cr.set_source_rgb(*outline_color)
        cr.set_line_width(1)
        cr.stroke()

    def do_realize(self):
        gtk.TextView.do_realize(self)

        if not self.edit_only:
            self.get_window(gtk.TEXT_WINDOW_LEFT).set_background(self.style.white)

        # While the the worksheet is executing, we want to display a watch cursor
        # Trying to override the cursor setting of GtkTextView is really hard because
        # of things like hiding the cursor when typing, so we take the simple approach
        # of using an input-only "cover window" that we set the cursor on and
        # show on top of the GtkTextView's normal window.

        self.__watch_window = gtk.gdk.Window(self.window,
                                             self.allocation.width, self.allocation.height,
                                             gtk.gdk.WINDOW_CHILD,
                                             (gtk.gdk.SCROLL_MASK |
                                              gtk.gdk.BUTTON_PRESS_MASK |
                                              gtk.gdk.BUTTON_RELEASE_MASK |
                                              gtk.gdk.POINTER_MOTION_MASK |
                                              gtk.gdk.POINTER_MOTION_HINT_MASK),
                                             gtk.gdk.INPUT_ONLY,
                                             x=0, y=0)
        self.__watch_window.set_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
        self.__watch_window.set_user_data(self)

        if self.get_buffer().worksheet.state == NotebookFile.EXECUTING:
            self.__watch_window.show()
            self.__watch_window.raise_()

    def do_unrealize(self):
        self.__watch_window.set_user_data(None)
        self.__watch_window.destroy()
        self.__watch_window = None
        gtk.TextView.do_unrealize(self)

    def do_size_allocate(self, allocation):
        gtk.TextView.do_size_allocate(self, allocation)
        if (self.flags() & gtk.REALIZED) != 0:
            self.__watch_window.resize(allocation.width, allocation.height)

    def __expose_window_left(self, event):
        (_, start_y) = self.window_to_buffer_coords(gtk.TEXT_WINDOW_LEFT, 0, event.area.y)
        start_line = self.__get_worksheet_line_at_y(start_y, adjust=ADJUST_AFTER)
        
        (_, end_y) = self.window_to_buffer_coords(gtk.TEXT_WINDOW_LEFT, 0, event.area.y + event.area.height - 1)
        end_line = self.__get_worksheet_line_at_y(end_y, adjust=ADJUST_BEFORE)

        buf = self.get_buffer()

        cr = event.window.cairo_create()

        for chunk in buf.worksheet.iterate_chunks(start_line, end_line + 1):
            if isinstance(chunk, StatementChunk):
                if chunk.executing:
                    self.paint_chunk(cr, event.area, chunk, (0, 1, 0), (0, 0.5, 0))
                elif chunk.error_message is not None:
                    self.paint_chunk(cr, event.area, chunk, (1, 0, 0), (0.5, 0, 0))
                elif chunk.needs_compile:
                    self.paint_chunk(cr, event.area, chunk, (1, 1, 0), (0.5, 0.5, 0))
                elif chunk.needs_execute:
                    self.paint_chunk(cr, event.area, chunk, (1, 0, 1), (0.5, 0.5, 0))
                else:
                    self.paint_chunk(cr, event.area, chunk, (0, 0, 1), (0, 0, 0.5))

    def __draw_rect_outline(self, event, rect):
        if (rect.y + rect.height <= event.area.y or rect.y >= event.area.y + event.area.height):
            return

        cr = event.window.cairo_create()
        cr.set_line_width(1.)
        cr.rectangle(rect.x + 0.5, rect.y + 0.5, rect.width - 1, rect.height - 1)
        cr.set_source_rgb(0.6, 0.6, 0.6)
        cr.stroke()

    def __expose_arg_highlight(self, event):
        buf = self.get_buffer()

        # We want a rectangle enclosing the range between arg_highlight_start and
        # arg_highlight_end; the method here isn't correct in the presence of
        # RTL text, but the necessary Pango functionality isn't exposed to
        # a GtkTextView user. RTL code is rare. We also don't handle multiple-line
        # highlight regions right. (Return ends the highlight, so you'd need to paste)
        rect = self.get_iter_location(buf.get_iter_at_mark (self.__arg_highlight_start))
        rect.x, rect.y = self.buffer_to_window_coords(gtk.TEXT_WINDOW_TEXT,
                                                      rect.x, rect.y)
        rect.width = 0
        end_rect = self.get_iter_location(buf.get_iter_at_mark (self.__arg_highlight_end))
        end_rect.x, end_rect.y = self.buffer_to_window_coords(gtk.TEXT_WINDOW_TEXT,
                                                              end_rect.x, end_rect.y)
        end_rect.width = 0

        rect = rect.union(end_rect)

        self.__draw_rect_outline(event, rect)

    def __expose_pair_location(self, event):
        pair_location = self.get_buffer().get_pair_location()
        if pair_location is None:
            return
        
        rect = self.get_iter_location(pair_location)

        rect.x, rect.y = self.buffer_to_window_coords(gtk.TEXT_WINDOW_TEXT, rect.x, rect.y)

        self.__draw_rect_outline(event, rect)

    def do_expose_event(self, event):
        if not self.edit_only and event.window == self.get_window(gtk.TEXT_WINDOW_LEFT):
            self.__expose_window_left(event)
            return False
        
        gtk.TextView.do_expose_event(self, event)

        if event.window == self.get_window(gtk.TEXT_WINDOW_TEXT):
            if self.__arg_highlight_start:
                self.__expose_arg_highlight(event)
            else:
                self.__expose_pair_location(event)
        
        return False

    # This is likely overengineered, since we're going to try as hard as possible not to
    # have tabs in our worksheets. We don't do the funky handling of \f.
    def __count_indent(self, text):
        indent = 0
        for c in text:
            if c == ' ':
                indent += 1
            elif c == '\t':
                indent += 8 - (indent % 8)
            else:
                break

        return indent

    def __find_outdent(self, iter):
        buf = self.get_buffer()
        line, _ = buf.iter_to_pos(iter)

        current_indent = self.__count_indent(buf.worksheet.get_line(line))

        while line > 0:
            line -= 1
            line_text = buf.worksheet.get_line(line)
            # Empty lines don't establish indentation
            if ALL_WHITESPACE_RE.match(line_text):
                continue

            indent = self.__count_indent(line_text)
            if indent < current_indent:
                return re.match(r"^[\t ]*", line_text).group(0)

        return ""

    def __find_default_indent(self, iter):
        buf = self.get_buffer()
        line, offset = buf.iter_to_pos(iter)

        while line > 0:
            line -= 1
            chunk = buf.worksheet.get_chunk(line)
            if isinstance(chunk, StatementChunk):
                return chunk.tokenized.get_next_line_indent(line - chunk.start)
            elif isinstance(chunk, CommentChunk):
                return " " * self.__count_indent(buf.worksheet.get_line(line))

        return ""

    def __reindent_line(self, iter, indent_text):
        buf = self.get_buffer()

        line, pos = buf.iter_to_pos(iter, adjust=ADJUST_NONE)
        if line == None:
            return

        line_text = buf.worksheet.get_line(line)
        prefix = re.match(r"^[\t ]*", line_text).group(0)

        diff = self.__count_indent(indent_text) - self.__count_indent(prefix)
        if diff == 0:
            return 0

        common_len = 0
        for a, b in zip(prefix, indent_text):
            if a != b:
                break
            common_len += 1
    
        start = iter.copy()
        start.set_line_offset(common_len)
        end = iter.copy()
        end.set_line_offset(len(prefix))

        # Nitpicky-detail. If the selection starts at the start of the line, and we are
        # inserting white-space there, then the whitespace should be *inside* the selection
        mark_to_start = None
        if common_len == 0 and buf.get_has_selection():
            mark = buf.get_insert()
            if buf.get_iter_at_mark(mark).compare(start) == 0:
                mark_to_start = mark
                
            mark = buf.get_selection_bound()
            if buf.get_iter_at_mark(mark).compare(start) == 0:
                mark_to_start = mark
        
        buf.delete(start, end)
        buf.insert(end, indent_text[common_len:])

        if mark_to_start is not None:
            end.set_line_offset(0)
            buf.move_mark(mark_to_start, end)

        return diff

    def __reindent_selection(self, outdent):
        buf = self.get_buffer()

        bounds = buf.get_selection_bounds()
        if bounds == ():
            insert_mark = buf.get_insert()
            bounds = buf.get_iter_at_mark(insert_mark), buf.get_iter_at_mark(insert_mark)
        start, end = bounds

        line, _ = buf.iter_to_pos(start, adjust=ADJUST_AFTER)
        end_line, end_offset = buf.iter_to_pos(end, adjust=ADJUST_BEFORE)
        if end_offset == 0 and end_line > line:
            end_line -= 1

        iter = buf.pos_to_iter(line)

        if outdent:
            indent_text = self.__find_outdent(iter)
        else:
            indent_text = self.__find_default_indent(iter)

        diff = self.__reindent_line(iter, indent_text)
        while True:
            line += 1
            if line > end_line:
                return

            iter = buf.pos_to_iter(line)
            current_indent = self.__count_indent(buf.worksheet.get_line(line))
            self.__reindent_line(iter, max(0, " " * (current_indent + diff)))

    def __hide_completion(self):
        if self.__completion_popup.showing:
            self.__completion_popup.popdown()
            
    def do_focus_out_event(self, event):
        self.__hide_completion()
        self.__doc_popup.popdown()
        return gtk.TextView.do_focus_out_event(self, event)

    def __rewrite_window(self, event):
        # Mouse events on the "watch window" that covers the text view
        # during calculation need to be forwarded to the real text window
        # since it looks bad if keynav works, but you can't click on the
        # window to set the cursor, select text, and so forth

        if event.window == self.__watch_window:
            event.window = self.get_window(gtk.TEXT_WINDOW_TEXT)

        # Events on the left-margin window also get written so the user can
        # click there when starting a drag selection. We need to adjust the
        # X coordinate in that case
        if not self.edit_only and event.window == self.get_window(gtk.TEXT_WINDOW_LEFT):
            event.window = self.get_window(gtk.TEXT_WINDOW_TEXT)
            if event.type == gtk.gdk._3BUTTON_PRESS:
                # Workaround for http://bugzilla.gnome.org/show_bug.cgi?id=573664
                event.x = 50.
            else:
                event.x -= LEFT_MARGIN_WIDTH

    def do_button_press_event(self, event):
        self.__rewrite_window(event)

        self.__doc_popup.popdown()

        return gtk.TextView.do_button_press_event(self, event)

    def do_button_release_event(self, event):
        self.__rewrite_window(event)

        return gtk.TextView.do_button_release_event(self, event)

    def do_motion_notify_event(self, event):
        self.__rewrite_window(event)

        return gtk.TextView.do_motion_notify_event(self, event)

    def __remove_arg_highlight(self, cursor_to_end=True):
        buf = self.get_buffer()

        end = buf.get_iter_at_mark (self.__arg_highlight_end)

        buf.delete_mark(self.__arg_highlight_start)
        self.__arg_highlight_start = None
        buf.delete_mark(self.__arg_highlight_end)
        self.__arg_highlight_end = None

        if cursor_to_end:
            # If the arg_highlight ends at closing punctuation, skip over it
            tmp = end.copy()
            tmp.forward_char()
            text = buf.get_slice(end, tmp)

            if text in (")", "]", "}"):
                buf.place_cursor(tmp)
            else:
                buf.place_cursor(end)

    def do_key_press_event(self, event):
        buf = self.get_buffer()

        if self.__completion_popup.focused and self.__completion_popup.on_key_press_event(event):
            return True
        
        if self.__doc_popup.focused:
            self.__doc_popup.on_key_press_event(event)
            return True

        if not self.edit_only and event.keyval in (gtk.keysyms.F2, gtk.keysyms.KP_F2):
            self.__hide_completion()

            if self.__doc_popup.showing:
                self.__doc_popup.focus()
            else:
                self.show_doc_popup(focus_popup=True)

            return True

        if not self.__arg_highlight_start:
            self.__doc_popup.popdown()
        
        if event.keyval in (gtk.keysyms.KP_Enter, gtk.keysyms.Return):
            self.__hide_completion()

            if self.__arg_highlight_start:
                self.__remove_arg_highlight()
                self.__doc_popup.popdown()
                return True
            
            increase_indent = False
            insert = buf.get_iter_at_mark(buf.get_insert())
            line, pos = buf.iter_to_pos(insert, adjust=ADJUST_NONE)

            # Inserting return inside a ResultChunk would normally do nothing
            # but we want to make it insert a line after the chunk
            if line is None and not buf.get_has_selection():
                line, pos = buf.iter_to_pos(insert, adjust=ADJUST_BEFORE)
                iter = buf.pos_to_iter(line, -1)
                buf.place_cursor(iter)
                buf.insert_interactive(iter, "\n", True)
                
                return True

            buf.begin_user_action()
            
            gtk.TextView.do_key_press_event(self, event)
            # We need the chunks to be updated when computing the line indents
            buf.worksheet.rescan()

            insert = buf.get_iter_at_mark(buf.get_insert())
            
            self.__reindent_line(insert, self.__find_default_indent(insert))

            # If we have two comment lines in a row, assume a block comment
            if (line > 0 and
                isinstance(buf.worksheet.get_chunk(line), CommentChunk) and
                isinstance(buf.worksheet.get_chunk(line - 1), CommentChunk)):
                self.get_buffer().insert_interactive_at_cursor("# ", True)

            buf.end_user_action()
                
            return True
        elif event.keyval in (gtk.keysyms.Tab, gtk.keysyms.KP_Tab) and event.state & gtk.gdk.CONTROL_MASK == 0:
            buf.begin_user_action()
            self.__reindent_selection(outdent=False)
            buf.end_user_action()

            return True
        elif event.keyval == gtk.keysyms.ISO_Left_Tab and event.state & gtk.gdk.CONTROL_MASK == 0:
            buf.begin_user_action()
            self.__reindent_selection(outdent=True)
            buf.end_user_action()

            return True
        elif event.keyval == gtk.keysyms.space and event.state & gtk.gdk.CONTROL_MASK != 0:
            if self.__completion_popup.showing:
                if self.__completion_popup.spontaneous:
                    self.__completion_popup.popup(spontaneous=False)
                else:
                    self.__completion_popup.popdown()
            else:
                if self.__doc_popup.showing:
                    self.__doc_popup.popdown()
                self.__completion_popup.popup(spontaneous=False)
            return True
        elif event.keyval in (gtk.keysyms.z, gtk.keysyms.Z) and \
                (event.state & gtk.gdk.CONTROL_MASK) != 0 and \
                (event.state & gtk.gdk.SHIFT_MASK) == 0:
            buf.worksheet.undo()
            
            return True
        # This is the gedit/gtksourceview binding to cause your hands to fall off
        elif event.keyval in (gtk.keysyms.z, gtk.keysyms.Z) and \
                (event.state & gtk.gdk.CONTROL_MASK) != 0 and \
                (event.state & gtk.gdk.SHIFT_MASK) != 0:
            buf.worksheet.redo()
            
            return True
        # This is the familiar binding (Eclipse, etc). Firefox supports both
        elif event.keyval in (gtk.keysyms.y, gtk.keysyms.Y) and event.state & gtk.gdk.CONTROL_MASK != 0:
            buf.worksheet.redo()

            return True
        
        return gtk.TextView.do_key_press_event(self, event)

    def __show_mouse_over(self):
        self.__mouse_over_timeout = None
        
        if self.__completion_popup.showing:
            return
        
        self.__doc_popup.set_target(self.__mouse_over_object)
        location = self.get_buffer().get_iter_at_mark(self.__mouse_over_start)
        self.__doc_popup.position_at_location(self, location)
        self.__doc_popup.popup()

        return False
        
    def __stop_mouse_over(self):
        if self.__mouse_over_timeout:
            gobject.source_remove(self.__mouse_over_timeout)
            self.__mouse_over_timeout = None
            
        self.__mouse_over_object = None
        
    def do_motion_notify_event(self, event):
        # Successful mousing-over depends on knowing the types of symbols so doing the
        # checks are pointless in edit-only mode
        if not self.edit_only and event.window == self.get_window(gtk.TEXT_WINDOW_TEXT) and not self.__doc_popup.focused:
            buf = self.get_buffer()
            
            x, y = self.window_to_buffer_coords(gtk.TEXT_WINDOW_TEXT, int(event.x), int(event.y))
            iter, _ = self.get_iter_at_position(x, y)
            line, offset = buf.iter_to_pos(iter, adjust=ADJUST_NONE)
            if line is not None:
                obj, start_line, start_offset, _,_ = buf.worksheet.get_object_at_location(line, offset)
            else:
                obj = None

            if not obj is self.__mouse_over_object:
                self.__stop_mouse_over()
                self.__doc_popup.popdown()
                if obj is not None:
                    start = buf.pos_to_iter(start_line, start_offset)
                    buf.move_mark(self.__mouse_over_start, start)

                    self.__mouse_over_object = obj
                    try:
                        timeout = self.get_settings().get_property('gtk-tooltip-timeout')
                    except TypeError: # GTK+ < 2.12
                        timeout = 500
                    self.__mouse_over_timeout = gobject.timeout_add(timeout, self.__show_mouse_over)
                
        return gtk.TextView.do_motion_notify_event(self, event)

    def do_leave_notify_event(self, event):
        self.__stop_mouse_over()
        if not self.__doc_popup.focused:
            self.__doc_popup.popdown()
        return False

    def do_backspace(self):
        buf = self.get_buffer()
        
        insert = buf.get_iter_at_mark(buf.get_insert())
        line, offset = buf.iter_to_pos(insert)
        
        current_chunk = buf.worksheet.get_chunk(line)
        if isinstance(current_chunk, StatementChunk) or isinstance(current_chunk, BlankChunk):
            line_text = buf.worksheet.get_line(line)[0:offset]

            if re.match(r"^[\t ]+$", line_text):
                self.__reindent_line(insert, self.__find_outdent(insert))
                return
                       
        return gtk.TextView.do_backspace(self)

    def __invalidate_status(self, chunk):
        buf = self.get_buffer()
        
        (start_y, start_height) = self.__get_worksheet_line_yrange(chunk.start)
        (end_y, end_height) = self.__get_worksheet_line_yrange(chunk.end - 1)

        (_, window_y) = self.buffer_to_window_coords(gtk.TEXT_WINDOW_LEFT, 0, start_y)

        if self.window:
            left_margin_window = self.get_window(gtk.TEXT_WINDOW_LEFT)
            left_margin_window.invalidate_rect((0, window_y, LEFT_MARGIN_WIDTH, end_y + end_height - start_y),
                                               False)

    def on_chunk_inserted(self, worksheet, chunk):
        self.__invalidate_status(chunk)

    def on_chunk_changed(self, worksheet, chunk, changed_lines):
        self.__invalidate_status(chunk)

    def on_chunk_status_changed(self, worksheet, chunk):
        self.__invalidate_status(chunk)

    def on_notify_state(self, worksheet, param_spec):
        if (self.flags() & gtk.REALIZED) != 0:
            if worksheet.state == NotebookFile.EXECUTING:
                self.__watch_window.show()
                self.__watch_window.raise_()
            else:
                self.__watch_window.hide()

    def on_after_insert_text(self, buf, location, text, len):
        if buf.worksheet.in_user_action() and not buf.in_modification():
            self.__inserted_in_user_action = True

    def on_after_delete_range(self, buf, start, end):
        if buf.worksheet.in_user_action() and not buf.in_modification():
            self.__deleted_in_user_action = True

    def on_after_end_user_action(self, buf):
        if not buf.worksheet.in_user_action():
            if self.__completion_popup.showing:
                if self.__inserted_in_user_action or self.__deleted_in_user_action:
                    self.__completion_popup.update()
            else:
                if self.__inserted_in_user_action and global_settings.autocomplete:
                    self.__completion_popup.popup(spontaneous=True)
            self.__inserted_in_user_action = False
            self.__deleted_in_user_action = False

    def on_add_custom_result(self, buf, result, anchor):
        widget = result.create_widget()
        widget.show()
        self.add_child_at_anchor(widget, anchor)

    def on_mark_set(self, buffer, iter, mark):
        if self.__arg_highlight_start:
            # See if the user moved the cursor out of the highlight regionb
            buf = self.get_buffer()
            if mark != buf.get_insert():
                return

            if (iter.compare(buf.get_iter_at_mark(self.__arg_highlight_start)) < 0 or
                iter.compare(buf.get_iter_at_mark(self.__arg_highlight_end)) > 0):
                self.__remove_arg_highlight(cursor_to_end=False)

    def __invalidate_char_position(self, iter):
        y, height = self.get_line_yrange(iter)
        if self.window:
            text_window = self.get_window(gtk.TEXT_WINDOW_TEXT)
            width, _ = text_window.get_size()
            text_window.invalidate_rect((0, y, width, height), False)
        
    def on_pair_location_changed(self, buf, old_position, new_position):
        if old_position:
            self.__invalidate_char_position(old_position)
        if new_position:
            self.__invalidate_char_position(new_position)

    def calculate(self):
        buf = self.get_buffer()

        buf.worksheet.calculate()

        # This is a hack to work around the fact that scroll_mark_onscreen()
        # doesn't wait for a size-allocate cycle, so doesn't properly handle
        # embedded request widgets
        self.size_request()
        self.size_allocate((self.allocation.x, self.allocation.y,
                            self.allocation.width, self.allocation.height))

        self.scroll_mark_onscreen(buf.get_insert())

    def copy_as_doctests(self):
        buf = self.get_buffer()

        bounds = buf.get_selection_bounds()
        if bounds == ():
            start, end = buf.get_iter_at_mark(buf.get_insert())
        else:
            start, end = bounds

        start_line, start_offset = buf.iter_to_pos(start, adjust=ADJUST_BEFORE)
        end_line, end_offset = buf.iter_to_pos(end, adjust=ADJUST_BEFORE)

        doctests = buf.worksheet.get_doctests(start_line, end_line + 1)
        self.get_clipboard(gtk.gdk.SELECTION_CLIPBOARD).set_text(doctests)

    def show_doc_popup(self, focus_popup=False):
        """Pop up the doc popup for the symbol at the insertion point, if any

        @param focus_popup: if True, the popup will be given keyboard focus

        """

        buf = self.get_buffer()

        insert = buf.get_iter_at_mark(buf.get_insert())
        line, offset = buf.iter_to_pos(insert, adjust=ADJUST_NONE)
        if line is not None:
            obj, start_line, start_offset, _, _ = buf.worksheet.get_object_at_location(line, offset, include_adjacent=True)
        else:
            obj = None

        if obj is not None:
            start = buf.pos_to_iter(start_line, start_offset)
            self.__stop_mouse_over()
            self.__doc_popup.set_target(obj)
            self.__doc_popup.position_at_location(self, start)
            if focus_popup:
                self.__doc_popup.popup_focused()
            else:
                self.__doc_popup.popup()

    def highlight_arg_region(self, start, end):
        """Highlight the region between start and end for argument insertion.
        A box will be drawn around the region as long as the cursor is inside
        the region. If the user hits return, the cursor will be moved to the
        end (and past a single closing punctuation at the end, if any.)

        @param start iter at the start of the highlight region
        @param end iter at the end of the highlight region

        """

        buf = self.get_buffer()

        self.__arg_highlight_start = buf.create_mark(None, start, left_gravity=True)
        self.__arg_highlight_end = buf.create_mark(None, end, left_gravity=False)
