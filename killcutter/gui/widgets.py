"""Small reusable desktop components: cards, frame canvas, scrollable forms."""
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

from . import theme as t
from .state import image_rect, source_pixel


class Card(tk.Frame):
    def __init__(self, parent, padding=18, **kwargs):
        super().__init__(parent, bg=t.BG, **kwargs)
        self.background = tk.Canvas(self, bg=t.BG, highlightthickness=0)
        self.background.place(x=0, y=0, relwidth=1, relheight=1)
        self.content = tk.Frame(self, bg=t.CARD)
        self.content.pack(fill='both', expand=True, padx=padding, pady=padding)
        self.background.bind('<Configure>', self._draw)

    def _draw(self, event):
        w, h, r = event.width - 1, event.height - 1, 16
        self.background.delete('all')
        self.background.create_polygon(r, 1, w-r, 1, w, 1, w, r, w, h-r, w, h,
                                       w-r, h, r, h, 1, h, 1, h-r, 1, r, 1, 1,
                                       smooth=True, fill=t.CARD, outline=t.BORDER)


def label(parent, text='', *, size=10, color=t.INK, bold=False, **kwargs):
    widget = tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                      font=('', size, 'bold' if bold else 'normal'), anchor='w', **kwargs)
    return widget


class Preview(tk.Canvas):
    def __init__(self, parent, on_pixel=None, **kwargs):
        super().__init__(parent, bg='#101116', highlightthickness=1,
                         highlightbackground=t.BORDER, **kwargs)
        self.image = None
        self.photo = None
        self.point = None
        self.on_pixel = on_pixel
        self.bind('<Configure>', lambda _: self.redraw())
        self.bind('<Button-1>', self._click)

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
                             font=('', 16, 'bold'), width=max(100, width-60))
            self.create_text(cx, cy+39, text='Open a recording to explore the frames and choose a range.',
                             fill=t.MUTED, font=('', 10), width=max(100, width-80))
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
    def __init__(self, parent):
        super().__init__(parent, bg=t.BG)
        self.canvas = tk.Canvas(self, bg=t.BG, highlightthickness=0)
        bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = tk.Frame(self.canvas, bg=t.BG)
        self.window = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda _: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.window, width=e.width))
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
