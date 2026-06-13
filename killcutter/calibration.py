"""Interactive OpenCV helpers for re-finding the scan region and trigger pixels.

These open GUI windows and print suggested values to paste into
:mod:`killcutter.constants`. Used by ``python -m killcutter calibrate``.
"""

import cv2

from killcutter import ui
from killcutter.errors import VideoError
from killcutter.timecode import format_clock


def _grab_frame(video_path, seek_secs):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise VideoError(f"Could not open: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = total / fps if fps > 0 else 0
    seek_secs = min(seek_secs, max(0, duration - 1))
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(seek_secs * fps))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise VideoError("Could not read a frame at the requested timestamp.")
    return frame, duration, seek_secs


def calibrate_region(video_path, seek_secs) -> None:
    """Drag a box around the banner; prints the region to use."""
    frame, duration, seek_secs = _grab_frame(video_path, seek_secs)
    print(ui.paint(f"  Showing frame at {format_clock(seek_secs)} "
                   f"(duration {format_clock(duration)})", ui.GREY))
    print(ui.paint("  Drag a box around the ENEMY DOWNED banner, then press ENTER.\n", ui.DIM))

    rect = cv2.selectROI("Calibrate: drag around the banner, then ENTER",
                         frame, fromCenter=False, showCrosshair=True)
    cv2.destroyAllWindows()
    if rect == (0, 0, 0, 0):
        print(ui.paint("  No region selected.", ui.AMBER))
        return

    x, y, w, h = (int(v) for v in rect)
    print("\n  " + ui.badge("REGION", bg=ui.GREEN) + " "
          + ui.paint(f"--region {x} {y} {w} {h}", ui.WHITE))
    print("  " + ui.paint(f"DEFAULT_REGION = ({x}, {y}, {w}, {h})", ui.DIM))


def calibrate_pixel(video_path, seek_secs, region) -> None:
    """Click on the banner ROI (6x zoom) to find a reliable trigger pixel."""
    frame, _, _ = _grab_frame(video_path, seek_secs)
    x, y, w, h = region
    roi = frame[y:y + h, x:x + w]
    zoom = 6
    big = cv2.resize(roi, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST)
    clicked = {}
    win = "Pick trigger pixel (click on white text, Q to quit)"

    def on_click(event, cx, cy, flags, _):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        px, py = cx // zoom, cy // zoom
        ax, ay = x + px, y + py
        clicked["pos"] = (ax, ay)
        b, g, r = roi[min(py, h - 1), min(px, w - 1)]
        print(ui.paint(f"  ROI ({px}, {py}) → screen ({ax}, {ay})  RGB({r}, {g}, {b})", ui.GREY))
        cv2.circle(big, (cx, cy), 4, (0, 255, 0), -1)

    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_click)
    print(ui.paint("  Click a pixel that sits on reliably-white banner text. Press Q when done.\n", ui.DIM))
    while True:
        cv2.imshow(win, big)
        if cv2.waitKey(50) & 0xFF == ord("q"):
            break
    cv2.destroyAllWindows()

    if "pos" in clicked:
        ax, ay = clicked["pos"]
        print("\n  " + ui.badge("PIXEL", bg=ui.GREEN) + " "
              + ui.paint(f"TRIGGER_PIXEL = ({ax}, {ay})", ui.WHITE))
