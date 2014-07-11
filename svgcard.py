#    Copyright (C) 2007, 2008 One Laptop Per Child
#    Copyright (C) 2013, Ignacio Rodriguez
#
#    Muriel de Souza Godoi - muriel@laptop.org
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#

import logging
import cairo

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import GdkPixbuf
from gi.repository import Pango
from gi.repository import PangoCairo

from sugar3.util import LRU
from sugar3.graphics import style

import theme
import face
import speak.voice
import model

_logger = logging.getLogger('memorize-activity')

radio = style.zoom(60)
BORDER_WIDTH = style.zoom(10)


class SvgCard(Gtk.EventBox):
    """
    This class is named SvgCard for historica reasons only.
    At the beginning a svg file was used to draw the card border.
    Now was replaced by cairo, to make easier implement a flip animaton.
    """

    # Default properties
    default_props = {}
    default_props['back'] = {'fill_color': style.Color('#b2b3b7'),
                             'stroke_color': style.Color('#b2b3b7')}
    default_props['back_text'] = {'text_color': style.Color('#c7c8cc')}
    default_props['front'] = {'fill_color': style.Color('#4c4d4f'),
                              'stroke_color': style.Color('#ffffff')}
    default_props['front_text'] = {'text_color': '#ffffff'}

    def __init__(self, identifier, pprops, jpeg, size,
                 bg_color='#000000', font_name=model.DEFAULT_FONT):
        Gtk.EventBox.__init__(self)

        self.bg_color = bg_color
        self.flipped = False
        self.flipped_once = False
        self.id = identifier
        self.jpeg = jpeg
        self.show_jpeg = False
        self.show_text = False
        self.size = size
        # animation data
        self._steps_scales = [0.66, 0.33, 0.1, 0.33, 0.66]
        self._animation_steps = len(self._steps_scales)
        self._on_animation = False
        self._animation_step = 0

        self.text_layouts = [None, None]
        self.font_name = font_name
        self._highlighted = False

        self.modify_bg(Gtk.StateType.NORMAL, Gdk.color_parse(bg_color))
        self.set_size_request(size, size)

        # Views properties
        views = ['back', 'back_text', 'front', 'front_text']
        self.pprops = pprops
        self.props = {}
        for view in views:
            self.props[view] = {}
            self.props[view].update(self.default_props[view])
            self.props[view].update(pprops.get(view, {}))

        if len(self.props['back_text'].get('card_text', '')) > 0:
            self.show_text = True

        self._cached_surface = {True: None, False: None}

        self.draw = Gtk.DrawingArea()
        self.draw.modify_bg(Gtk.StateType.NORMAL, Gdk.color_parse(bg_color))
        self.draw.set_events(Gdk.EventMask.ALL_EVENTS_MASK)
        self.draw.connect('draw', self.__draw_cb)
        self.draw.show_all()

        self.workspace = Gtk.VBox()
        self.workspace.add(self.draw)
        self.add(self.workspace)
        self.show_all()

    def __draw_cb(self, widget, context):
        flipped = self.flipped
        highlighted = self._highlighted
        if self._on_animation:
            if self._animation_step > self._animation_steps / 2:
                flipped = not self.flipped

        if not self._cached_surface[flipped]:
            self._prepare_cached_surface(context, flipped)

        if self._on_animation:
            scale = self._steps_scales[self._animation_step]
            context.translate(0, self.size * (1 - scale) / 2)
            context.scale(1.0, scale)
            self._animation_step += 1
            highlighted = False

        context.set_source_surface(self._cached_surface[flipped])
        context.paint()

        if highlighted:
            self.draw_round_rect(context, 0, 0, self.size, self.size, radio)
            context.set_source_rgb(1., 1., 1.)
            context.set_line_width(6)
            context.stroke()

        return False

    def _prepare_cached_surface(self, context, flipped):
        self._cached_surface[flipped] = \
            context.get_target().create_similar(cairo.CONTENT_COLOR_ALPHA,
                                                self.size, self.size)
        cache_context = cairo.Context(self._cached_surface[flipped])

        if flipped:
            icon_data = self.props['front']
        else:
            icon_data = self.props['back']

        cache_context.save()
        self.draw_round_rect(cache_context, 0, 0, self.size, self.size,
                             radio)
        r, g, b, a = icon_data['fill_color'].get_rgba()
        cache_context.set_source_rgb(r, g, b)
        cache_context.fill_preserve()

        r, g, b, a = icon_data['stroke_color'].get_rgba()
        cache_context.set_source_rgb(r, g, b)
        cache_context.set_line_width(BORDER_WIDTH)
        cache_context.stroke()
        cache_context.restore()

        if self.show_jpeg:
            Gdk.cairo_set_source_pixbuf(cache_context, self.jpeg,
                                        theme.SVG_PAD, theme.SVG_PAD)
            cache_context.paint()

        if self.show_text:
            cache_context.save()
            props = self.props[flipped and 'front_text' or
                               'back_text']
            layout = self.text_layouts[flipped]

            if not layout:
                layout = self.text_layouts[flipped] = \
                    self.create_text_layout(props['card_text'])

            width, height = layout.get_pixel_size()
            y = (self.size - height) / 2
            x = (self.size - width) / 2
            cache_context.set_source_rgb(1, 1, 1)
            cache_context.translate(x, y)
            PangoCairo.update_layout(cache_context, layout)
            PangoCairo.show_layout(cache_context, layout)
            cache_context.fill()
            cache_context.restore()

    def set_border(self, stroke_color, fill_color):
        """
        style_color, fill_color: str with format #RRGGBB
        """
        self.props['front'].update({'fill_color': style.Color(fill_color),
                                    'stroke_color': style.Color(stroke_color)})
        self._cached_surface[True] = None
        self.queue_draw()

    def set_pixbuf(self, pixbuf):
        if pixbuf is None:
            self.jpeg = None
            self.show_jpeg = False
        else:
            if self.jpeg is not None:
                del self.jpeg

            self.jpeg = pixbuf
            del pixbuf
            self.show_jpeg = True
        self._cached_surface[True] = None
        self.queue_draw()

    def get_pixbuf(self):
        return self.jpeg

    def set_highlight(self, status, mouse=False):
        if self.flipped and mouse:
            return
        self._highlighted = status
        self.queue_draw()

    def flip(self, full_animation=False):
        if self.flipped:
            return

        if not self.flipped_once:
            if self.jpeg is not None:
                pixbuf_t = GdkPixbuf.Pixbuf.new_from_file(self.jpeg)
                if pixbuf_t.get_width() != self.size - 22 \
                        or pixbuf_t.get_height() != self.size - 22:
                    self.jpeg = pixbuf_t.scale_simple(
                        self.size - 22, self.size - 22,
                        GdkPixbuf.InterpType.BILINEAR)
                    del pixbuf_t
                else:
                    self.jpeg = pixbuf_t
            self.flipped_once = True

        if self.jpeg is not None:
            self.show_jpeg = True
        text = self.props.get('front_text', {}).get('card_text', '')
        if text is not None and len(text) > 0:
            self.show_text = True
        else:
            self.show_text = False

        if full_animation:
            if self.id != -1 and self.get_speak():
                speaking_face = face.acquire()
                if speaking_face:
                    self._switch_to_face(speaking_face)
                    speaking_face.face.status.voice = \
                        speak.voice.by_lang(self.get_speak())
                    speaking_face.face.say(self.get_text())

            self._animation_step = 0
            self._on_animation = True
            self._animate_flip()
        else:
            self._finish_flip()

    def _animate_flip(self):
        if self._animation_step < self._animation_steps - 1:
            self.queue_draw()
            GObject.timeout_add(100, self._animate_flip)
        else:
            self._finish_flip()
        return False

    def _finish_flip(self):
        self._on_animation = False
        self.flipped = True
        self.queue_draw()

    def cement(self):
        if not self.get_speak():
            return
        self._switch_to_face(self.draw)

    def flop(self):
        self._animation_step = 0
        self._on_animation = True
        self._animate_flop()

    def _animate_flop(self):
        if self._animation_step < self._animation_steps - 1:
            self.queue_draw()
            GObject.timeout_add(100, self._animate_flop)
        else:
            self._finish_flop()
        return False

    def _finish_flop(self):
        self._on_animation = False
        if len(self.props['back_text'].get('card_text', '')) > 0:
            self.show_text = True
        else:
            self.show_text = False
        self.flipped = False
        self.show_jpeg = False

        if self.id != -1 and self.get_speak():
            self._switch_to_face(self.draw)

        self.queue_draw()

    def _switch_to_face(self, widget):
        for i in self.workspace.get_children():
            self.workspace.remove(i)
        self.workspace.add(widget)
        widget.set_size_request(self.size, self.size)

    def is_flipped(self):
        return self.flipped

    def get_id(self):
        return self.id

    def reset(self):
        if self.flipped:
            self.flop()

    def create_text_layout(self, text):
        key = (self.size, text)
        if key in _text_layout_cache:
            return _text_layout_cache[key]

        max_lines_count = len([i for i in text.split(' ') if i])

        for size in range(80, 66, -8) + range(66, 44, -6) + \
                range(44, 24, -4) + range(24, 15, -2) + range(15, 7, -1):

            card_size = self.size - BORDER_WIDTH * 2
            layout = self.create_pango_layout(text)
            layout.set_width(PIXELS_PANGO(card_size))
            layout.set_wrap(Pango.WrapMode.WORD)
            desc = Pango.FontDescription(self.font_name + " " + str(size))
            layout.set_font_description(desc)

            if layout.get_line_count() <= max_lines_count and \
                    layout.get_pixel_size()[0] <= card_size and \
                    layout.get_pixel_size()[1] <= card_size:
                break

        if layout.get_line_count() > 1:
            # XXX for single line ALIGN_CENTER wrongly affects on text position
            # and also in some cases for multilined text
            layout.set_alignment(Pango.Alignment.CENTER)

        _text_layout_cache[key] = layout

        return layout

    def change_font(self, font_name):
        # remove from local cache
        self.text_layouts[self.flipped] = False
        text = self.props['front_text']['card_text']
        key = (self.size, text)
        if key in _text_layout_cache:
            del _text_layout_cache[key]

        self.font_name = font_name
        self._cached_surface[True] = None
        self.queue_draw()

    def set_background(self, color):
        self.bg_color = color
        self.draw.modify_bg(Gtk.StateType.NORMAL,
                            Gdk.color_parse(self.bg_color))

    def change_text(self, newtext):
        self.text_layouts[self.flipped] = None
        self.props['front_text']['card_text'] = newtext
        if len(newtext) > 0:
            self.show_text = True
        self._cached_surface[True] = None
        self.queue_draw()

    def get_text(self):
        return self.props['front_text'].get('card_text', '')

    def change_speak(self, value):
        self.props['front_text']['speak'] = value

    def get_speak(self):
        return self.props['front_text'].get('speak')

    def draw_round_rect(self, context, x, y, w, h, r):
        context.move_to(x + r, y)
        context.line_to(x + w - r, y)
        context.curve_to(x + w, y, x + w, y, x + w, y + r)
        context.line_to(x + w, y + h - r)
        context.curve_to(x + w, y + h, x + w, y + h, x + w - r, y + h)
        context.line_to(x + r, y + h)
        context.curve_to(x, y + h, x, y + h, x, y + h - r)
        context.line_to(x, y + r)
        context.curve_to(x, y, x, y, x + r, y)


def PIXELS_PANGO(x):
    return x * 1000

_text_layout_cache = LRU(50)
