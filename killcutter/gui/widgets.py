"""Small reusable desktop components: cards, frame canvas, scrollable forms."""
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

from . import theme as t
from .state import image_rect, source_pixel
from .surfaces import rounded_surface


class Card(tk.Frame):
    """A rounded surface. ``role`` names a palette entry so it can be restyled."""
    def __init__(self, parent, padding=18, role='CARD', **kwargs):
        super().__init__(parent, bg=t.BG, **kwargs)
        self.background = tk.Canvas(self, bg=t.BG, highlightthickness=0)
        self.background.place(x=0, y=0, relwidth=1, relheight=1)
        self.role = role
        self.padding = padding
        self._surface_key = None
        self.content = tk.Frame(self, bg=self.color)
        self.content.pack(fill='both', expand=True, padx=t.px(padding), pady=t.px(padding))
        self.background.bind('<Configure>', lambda e: self._draw(e.width, e.height))

    @property
    def color(self):
        return getattr(t, self.role)

    def refresh(self):
        self.configure(bg=t.BG)
        self.background.configure(bg=t.BG)
        self.content.configure(bg=self.color)
        self.content.pack_configure(padx=t.px(self.padding), pady=t.px(self.padding))
        self._draw(self.background.winfo_width(), self.background.winfo_height())

    def _draw(self, width, height):
        if width < 2 or height < 2:
            return
        key = (width, height, t.px(18), self.color, t.BORDER)
        if key == self._surface_key:
            return
        self._surface_key = key
        self.photo = ImageTk.PhotoImage(rounded_surface(
            width, height, t.px(18), self.color, t.BORDER), master=self)
        self.background.delete('all')
        self.background.create_image(0, 0, anchor='nw', image=self.photo)



class RoundedTreeview(ttk.Treeview):
    """Keep native table interactions with a rounded, continuous header strip."""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._header_corners = [tk.Label(self, bd=0, highlightthickness=0, takefocus=False)
                                for _ in range(4)]
        self._header_key = None
        self._header_timer = None
        self.bind('<Configure>', self._schedule_header, add='+')
        self.bind('<<ThemeChanged>>', self._schedule_header, add='+')
        self.bind('<Destroy>', self._cancel_header, add='+')
        for corner in self._header_corners:
            for sequence in ('<Button-1>', '<ButtonRelease-1>', '<Motion>'):
                corner.bind(sequence, lambda event, seq=sequence: self.event_generate(
                    seq, x=event.x_root-self.winfo_rootx(), y=event.y_root-self.winfo_rooty()))

    def _cancel_header(self, event):
        if event.widget is self and self._header_timer:
            self.after_cancel(self._header_timer)
            self._header_timer = None

    def _schedule_header(self, event=None):
        if self._header_timer:
            self.after_cancel(self._header_timer)
        self._header_timer = self.after_idle(self._round_header)

    def _round_header(self):
        self._header_timer = None
        if not self.winfo_exists():
            return
        width = self.winfo_width()
        # Ask Tk for the actual heading boundary: fonts, scaling and platform
        # all affect its height. Do not assume it equals the row height.
        ys = [y for y in range(min(self.winfo_height(), t.px(100)))
              if self.identify_region(min(width-1, t.px(20)), y) in ('heading', 'separator')]
        if not ys or width < 4:
            for corner in self._header_corners:
                corner.place_forget()
            return
        top, bottom = min(ys), max(ys)+1
        radius = min(t.px(9), (bottom-top)//2, width//2)
        key = (radius, t.FIELD, t.CARD)
        if key != self._header_key:
            self._header_key = key
            size = radius*2+1
            surface = Image.new('RGBA', (size, size), t.CARD)
            surface.alpha_composite(rounded_surface(size, size, radius, t.FIELD))
            self._header_images = [ImageTk.PhotoImage(surface.crop(box), master=self) for box in (
                (0, 0, radius, radius), (size-radius, 0, size, radius),
                (0, size-radius, radius, size), (size-radius, size-radius, size, size))]
            for corner, photo in zip(self._header_corners, self._header_images):
                corner.configure(image=photo, bg=t.CARD)
        for corner, (x, y) in zip(self._header_corners,
                ((0, top), (width-radius, top), (0, bottom-radius), (width-radius, bottom-radius))):
            corner.place(x=x, y=y, width=radius, height=radius)
            corner.lift()


def label(parent, text='', *, size=10, color=None, bold=False, **kwargs):
    widget = tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color or t.INK,
                      font=(t.FAMILY, t.size(size), 'bold' if bold else 'normal'),
                      anchor='w', **kwargs)
    # Remembered so a scale or theme change can rebuild the same type hierarchy.
    widget.base_size, widget.base_bold = size, bold
    return widget


class Preview(tk.Canvas):
    def __init__(self, parent, on_pixel=None, **kwargs):
        super().__init__(parent, bg=t.PREVIEW, highlightthickness=1,
                         highlightbackground=t.BORDER, **kwargs)
        self.image = None
        self.photo = None
        self._image_key = None
        self.point = None
        self.on_pixel = on_pixel
        self.on_region = None
        self.region = None
        self.drag_start = None
        self.bind('<Configure>', lambda _: self.redraw())
        self.bind('<Button-1>', self._click)
        self.bind('<B1-Motion>', self._drag_region)
        self.bind('<ButtonRelease-1>', self._end_region)

    def refresh(self):
        self.configure(bg=t.PREVIEW, highlightbackground=t.BORDER)
        self.redraw()

    def set_image(self, image):
        self.image = image
        self._image_key = None
        self.point = None
        self.region = None
        self.redraw()

    def redraw(self):
        self.delete('all')
        width, height = self.winfo_width(), self.winfo_height()
        if width < 4 or height < 4:
            return
        if self.image is None:
            cx, cy = width / 2, height / 2
            self.create_rectangle(cx-26, cy-65, cx+26, cy-29, outline=t.BORDER, width=2)
            self.create_polygon(cx-6, cy-56, cx-6, cy-38, cx+10, cy-47, fill=t.ACCENT)
            self.create_text(cx, cy+1, text='Your next highlight starts here.', fill=t.INK,
                             font=('', t.size(16), 'bold'), width=max(100, width-60))
            self.create_text(cx, cy+39, text='Open a recording to explore the frames and choose a range.',
                             fill=t.MUTED, font=('', t.size(10)), width=max(100, width-80))
            return
        x, y, w, h = image_rect(self.image.width, self.image.height, width, height)
        key = (id(self.image), w, h)
        if key != self._image_key:
            self.photo = ImageTk.PhotoImage(self.image.resize((w, h), Image.Resampling.LANCZOS), master=self)
            self._image_key = key
        self.create_image(x, y, anchor='nw', image=self.photo)
        if self.region:
            rx, ry, rw, rh = self.region
            self.create_rectangle(x+rx*w, y+ry*h, x+(rx+rw)*w, y+(ry+rh)*h, outline=t.ACCENT, width=2)
        if self.point:
            px, py = self.point
            px, py = x + (px+.5) * w / self.image.width, y + (py+.5) * h / self.image.height
            self.create_oval(px-7, py-7, px+7, py+7, outline='white', width=2)
            self.create_line(px-14, py, px+14, py, fill=t.ACCENT)
            self.create_line(px, py-14, px, py+14, fill=t.ACCENT)

    def _click(self, event):
        if self.image is None or (self.on_pixel is None and self.on_region is None):
            return
        point = source_pixel(event.x, event.y, self.image.width, self.image.height,
                             self.winfo_width(), self.winfo_height())
        if point:
            if self.on_region:
                self.drag_start = point
                self.region = None
                return
            self.point = point
            self.on_pixel(*point, self.image.getpixel(point))
            self.redraw()

    def _drag_region(self, event):
        if not self.drag_start or self.image is None:
            return
        x, y, width, height = image_rect(self.image.width, self.image.height,
                                        self.winfo_width(), self.winfo_height())
        px = min(self.image.width-1, max(0, int((event.x-x)*self.image.width/max(1, width))))
        py = min(self.image.height-1, max(0, int((event.y-y)*self.image.height/max(1, height))))
        ax, ay = self.drag_start
        self.region = (min(ax, px)/self.image.width, min(ay, py)/self.image.height,
                       (abs(ax-px)+1)/self.image.width, (abs(ay-py)+1)/self.image.height)
        self.redraw()

    def _end_region(self, event):
        if self.drag_start:
            self._drag_region(event)
            self.drag_start = None
            if self.region and self.on_region:
                self.on_region(self.region)


class AutoScrollbar(ttk.Scrollbar):
    """A packed scrollbar that only occupies space when content overflows."""

    def set(self, first, last):
        super().set(first, last)
        needed = float(first) > 0.000001 or float(last) < 0.999999
        if not needed and self.winfo_manager() == 'pack':
            self._pack_options = self.pack_info()
            siblings = self.master.pack_slaves()
            index = siblings.index(self)
            if index + 1 < len(siblings):
                self._pack_options['before'] = siblings[index + 1]
            self.pack_forget()
        elif needed and not self.winfo_manager() and hasattr(self, '_pack_options'):
            self.pack(**self._pack_options)


class ScrollForm(tk.Frame):
    def __init__(self, parent, *, stretch=False):
        super().__init__(parent, bg=t.BG)
        self.canvas = tk.Canvas(self, bg=t.BG, highlightthickness=0)
        bar = AutoScrollbar(self, orient='vertical', command=self.canvas.yview,
                            style='Page.Vertical.TScrollbar')
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y', padx=(t.px(10), t.px(4)), pady=t.px(4))
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = tk.Frame(self.canvas, bg=t.BG)
        self.window = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        def update_region(_):
            bounds = self.canvas.bbox('all')
            self.canvas.configure(scrollregion=bounds)
            if bounds and bounds[3] - bounds[1] <= self.canvas.winfo_height():
                self.canvas.yview_moveto(0)
        self.body.bind('<Configure>', update_region)
        def resize(event):
            options = {'width': event.width}
            if stretch:
                options['height'] = max(self.body.winfo_reqheight(), event.height)
            self.canvas.itemconfigure(self.window, **options)
        self.canvas.bind('<Configure>', resize)
        if stretch:
            self.body.bind('<Configure>', lambda e: self.canvas.itemconfigure(
                self.window, height=max(self.body.winfo_reqheight(), self.canvas.winfo_height())), add='+')
        self.wheel_bindings = [(sequence, self.bind_all(sequence, self._wheel, add='+'))
                               for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>')]

    def destroy(self):
        for sequence, binding in self.wheel_bindings:
            self._root()._unbind(('bind', 'all', sequence), binding)
        super().destroy()

    def _wheel(self, event):
        first, last = self.canvas.yview()
        if first <= 0 and last >= 1:
            return
        target = self.winfo_containing(event.x_root, event.y_root)
        while target is not None:
            if target is self:
                delta = -1 if getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0 else 1
                self.canvas.yview_scroll(delta * 3, 'units')
                return
            target = getattr(target, 'master', None)
