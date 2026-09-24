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
        self.photo = ImageTk.PhotoImage(rounded_surface(
            width, height, t.px(18), self.color, t.BORDER), master=self)
        self.background.delete('all')
        self.background.create_image(0, 0, anchor='nw', image=self.photo)



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
        self.point = None
        self.on_pixel = on_pixel
        self.bind('<Configure>', lambda _: self.redraw())
        self.bind('<Button-1>', self._click)

    def refresh(self):
        self.configure(bg=t.PREVIEW, highlightbackground=t.BORDER)
        self.redraw()

    def set_image(self, image):
        self.image = image
        self.point = None
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
        self.photo = ImageTk.PhotoImage(self.image.resize((w, h), Image.Resampling.LANCZOS), master=self)
        self.create_image(x, y, anchor='nw', image=self.photo)
        if self.point:
            px, py = self.point
            px, py = x + (px+.5) * w / self.image.width, y + (py+.5) * h / self.image.height
            self.create_oval(px-7, py-7, px+7, py+7, outline='white', width=2)
            self.create_line(px-14, py, px+14, py, fill=t.ACCENT)
            self.create_line(px, py-14, px, py+14, fill=t.ACCENT)

    def _click(self, event):
        if self.image is None or self.on_pixel is None:
            return
        point = source_pixel(event.x, event.y, self.image.width, self.image.height,
                             self.winfo_width(), self.winfo_height())
        if point:
            self.point = point
            self.on_pixel(*point, self.image.getpixel(point))
            self.redraw()


class ScrollForm(tk.Frame):
    def __init__(self, parent, *, stretch=False):
        super().__init__(parent, bg=t.BG)
        self.canvas = tk.Canvas(self, bg=t.BG, highlightthickness=0)
        bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = tk.Frame(self.canvas, bg=t.BG)
        self.window = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda _: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        def resize(event):
            options = {'width': event.width}
            if stretch:
                options['height'] = max(self.body.winfo_reqheight(), event.height)
            self.canvas.itemconfigure(self.window, **options)
        self.canvas.bind('<Configure>', resize)
        if stretch:
            self.body.bind('<Configure>', lambda e: self.canvas.itemconfigure(
                self.window, height=max(self.body.winfo_reqheight(), self.canvas.winfo_height())), add='+')
        self.bind_all('<MouseWheel>', self._wheel, add='+')
        self.bind_all('<Button-4>', self._wheel, add='+')
        self.bind_all('<Button-5>', self._wheel, add='+')

    def _wheel(self, event):
        target = self.winfo_containing(event.x_root, event.y_root)
        while target is not None:
            if target is self:
                delta = -1 if getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0 else 1
                self.canvas.yview_scroll(delta * 3, 'units')
                return
            target = getattr(target, 'master', None)
