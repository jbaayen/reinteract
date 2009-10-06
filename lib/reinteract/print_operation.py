# Inspired by the Tomboy printing plugin.

import gtk
import pango
import cairo
import logging

from math import ceil

_debug = logging.getLogger("Printing").debug

class PageBreak:
    def __init__(self, paragraph, line):
        self.paragraph = paragraph
        self.line = line

class PrintOperation(gtk.PrintOperation):
    __gsignals__ = {
        'begin-print' : 'override',
        'draw-page': 'override',
        'end-print': 'override'
    }

    def __init__(self, editor):
        gtk.PrintOperation.__init__(self)

        self.editor = editor
        self.buffer = editor.view.get_buffer()

        self.page_breaks = []

        self.job_name = editor._get_display_name()

    def cm_to_pixel(self, cm, dpi):
        return cm * dpi / 2.54

    def _get_paragraph_attributes(self, layout, dpi_x, position, limit, start_index):
        attributes = []
        indentation = 0

        si = position.get_line_index() - start_index

        tags = position.get_tags()
        position.forward_to_tag_toggle(None)
        if position.compare(limit) > 0:
            position = limit

        screen_dpi_x = self.editor.view.get_screen().get_resolution()

        ei = position.get_line_index() - start_index

        for tag in tags:
            if tag.get_property("background_set"):
                color = tag.get_property("background_gdk")
                attributes.append(pango.AttrBackground(color.red, color.green, color.blue, si, ei))
            if tag.get_property("foreground_set"):
                color = tag.get_property("foreground_gdk")
                attributes.append(pango.AttrForeground(color.red, color.green, color.blue, si, ei))
            if tag.get_property("indent_set"):
                layout.set_indent(tag.get_property("indent"))
            if tag.get_property("left_margin_set"):
                indentation = tag.get_property("left-margin") / screen_dpiX * dpiX
            if tag.get_property("right_margin_set"):
                indentation = tag.get_property("right-margin") / screen_dpiX * dpiX
            if tag.get_property("font_desc") is not None:
                attributes.append(pango.AttrFontDesc(tag.get_property("font_desc"), si, ei))
            if tag.get_property("family_set"):
                attributes.append(pango.AttrFamily(tag.get_property("family"), si, ei))
            if tag.get_property("size_set"):
                attributes.append(pango.AttrSize(tag.get_property("size"), si, ei))
            if tag.get_property("style_set"):
                attributes.append(pango.AttrStyle(tag.get_property("style"), si, ei))
            if tag.get_property("underline_set") and tag.get_property("underline") is not pango.UNDERLINE_ERROR:
                attributes.append(pango.AttrUnderline(tag.get_property("underline"), si, ei))
            if tag.get_property("weight_set"):
                attributes.append(pango.AttrWeight(tag.get_property("weight"), si, ei))
            if tag.get_property("strikethrough_set"):
                attributes.append(pango.AttrStrikethrough(tag.get_property("strikethrough"), si, ei))
            if tag.get_property("rise_set"):
                attributes.append(pango.AttrRise(tag.get_property("rise"), si, ei))
            if tag.get_property("scale_set"):
                attributes.append(pango.AttrScale(tag.get_property("scale"), si, ei))
            if tag.get_property("stretch_set"):
                attributes.append(pango.AttrStretch(tag.get_property("stretch"), si, ei))

        return attributes, position, indentation

    def _create_paragraph_layout(self, context, p_start, p_end):
        layout = context.create_pango_layout()
        layout.set_font_description(self.editor.view.style.font_desc)
        start_index = p_start.get_line_index()
        indentation = 0

        dpi_x = context.get_dpi_x()
        attr_list = pango.AttrList()

        segm_start = p_start.copy()
        while segm_start.compare(p_end) < 0:
            attrs, segm_end, indentation = \
                self._get_paragraph_attributes(layout, dpi_x, segm_start, p_end, start_index)

            for a in attrs:
                attr_list.insert(a)

            segm_start = segm_end

        layout.set_attributes(attr_list)

        width = int(ceil((context.get_width() - self.margin_left - self.margin_right - indentation) * pango.SCALE))
        layout.set_width(width)
        layout.set_wrap(pango.WRAP_WORD_CHAR)

        text = self.buffer.get_slice(p_start, p_end, False)
        layout.set_text(text)

        return layout, indentation

    def do_begin_print(self, context):
        self.margin_top = self.cm_to_pixel(1.5, context.get_dpi_y())
        self.margin_left = self.cm_to_pixel(1, context.get_dpi_x())
        self.margin_right = self.cm_to_pixel(1, context.get_dpi_x())
        self.margin_bottom = self.cm_to_pixel(1.5, context.get_dpi_y())

        max_height = context.get_height() - self.margin_top - self.margin_bottom

        position, end_iter = self.buffer.get_bounds()

        page_height = 0
        done = position.compare(end_iter) >= 0
        while not done:
            line_end = position.copy()
            if not line_end.ends_line():
                line_end.forward_to_line_end()

            paragraph_number = position.get_line()
            layout, indentation = \
                self._create_paragraph_layout(context, position, line_end)

            child_anchor = position.get_child_anchor()
            if child_anchor is None:
                for line_in_paragraph in xrange(layout.get_line_count()):
                    line = layout.get_line(line_in_paragraph)
                    ink_rect, logical_rect = line.get_extents()

                    line_height = logical_rect[3] / pango.SCALE
                    if page_height + line_height >= max_height:
                        page_break = PageBreak(paragraph_number, line_in_paragraph)
                        self.page_breaks.append(page_break)

                        page_height = 0

                    page_height += line_height
            else:
                child_widgets = child_anchor.get_widgets()
                assert len(child_widgets) == 1
                child_widget = child_widgets[0]

                child_widget_width, child_widget_height = child_widget.print_widget(context, render=False)

                if page_height + child_widget_height >= max_height:
                    page_break = PageBreak(paragraph_number, 0)
                    self.page_breaks.append(page_break)

                    page_height = 0

                page_height += child_widget_height

            position.forward_line()
            done = position.compare(end_iter) >= 0

            del layout

        self.set_n_pages(len(self.page_breaks) + 1)

    def do_draw_page(self, context, page_nr):
        cr = context.get_cairo_context()
        cr.move_to(self.margin_left, self.margin_top)

        if page_nr == 0:
            start = PageBreak(0, 0)
        else:
            start = self.page_breaks[page_nr - 1]

        if page_nr < len(self.page_breaks):
            end = self.page_breaks[page_nr]
        else:
            end = PageBreak(-1, -1)

        _debug("on_draw_page with page_nr %d" % page_nr)

        position, end_iter = self.buffer.get_bounds()

        # Fast-forward to the right starting paragraph
        while position.get_line() < start.paragraph:
            position.forward_line()

        done = position.compare(end_iter) >= 0
        first_line = True
        while not done:
            line_end = position.copy()
            if not line_end.ends_line():
                line_end.forward_to_line_end()

            paragraph_number = position.get_line()
            layout, indentation = self._create_paragraph_layout(context, position, line_end)

            x, y = cr.get_current_point()

            child_anchor = position.get_child_anchor()
            if child_anchor is None:
                _debug("no child anchor. Position is at line %d" % paragraph_number)

                for line_number in xrange(layout.get_line_count()):
                    if done:
                        break

                    # Skip the lines up to the starting line in the
                    # first paragraph on this page
                    if paragraph_number == start.paragraph and line_number < start.line:
                        continue

                    # Break as soon as we hit the end line
                    if paragraph_number == end.paragraph and line_number == end.line:
                        done = True
                        break

                    line = layout.get_line(line_number)
                    ink_rect, logical_rect = line.get_extents()

                    line_height = logical_rect[3] / pango.SCALE

                    if first_line:
                        first_line = False
                    else:
                        cr.move_to(self.margin_left + indentation, y + line_height)

                    cr.show_layout_line(line)
            else:
                _debug("have child anchor")

                if paragraph_number == end.paragraph:
                    done = True
                else:
                    child_widgets = child_anchor.get_widgets()
                    assert len(child_widgets) == 1
                    child_widget = child_widgets[0]

                    child_widget_width, child_widget_height = child_widget.print_widget(context)

                    cr.move_to(self.margin_left + indentation, y + child_widget_height)

                    first_line = False

            position.forward_line()
            done = done or position.compare(end_iter) >= 0

    def do_end_print(self, context):
        pass
