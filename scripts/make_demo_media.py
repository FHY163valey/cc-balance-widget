"""Capture a real demo strip on a labelled synthetic taskbar-style backdrop."""
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from native_capture import capture_tk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cc_balance_widget.widget import App


def main():
    output = ROOT / "docs/images"
    output.mkdir(parents=True, exist_ok=True)
    app = App(demo=True)
    frames = []
    font = ImageFont.truetype("segoeui.ttf", 15)
    small = ImageFont.truetype("segoeui.ttf", 12)
    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.root.update()
            time.sleep(0.01)

    def frame(caption, x=24):
        screenshot = capture_tk(app.root).convert("RGBA")
        pixels = screenshot.load()
        for y in range(screenshot.height):
            for column in range(screenshot.width):
                r, g, b, _ = pixels[column, y]
                if max(r, g, b) < 8:
                    pixels[column, y] = (0, 0, 0, 0)
        image = Image.new("RGB", (720, 138), "#151618")
        draw = ImageDraw.Draw(image)
        draw.text((22, 12), "CC Balance Widget", font=font, fill="#f0f0f0")
        draw.text((22, 36), caption, font=small, fill="#b9bec5")
        draw.rectangle((0, 70, 720, 113), fill="#242629")
        draw.line((0, 70, 720, 70), fill="#42454a")
        image.paste(screenshot, (x, 78), screenshot)
        draw.text((22, 118), "Demo values only | Native widget capture on a synthetic taskbar backdrop",
                  font=small, fill="#989ea6")
        return image

    try:
        app.move(100, 180)
        pump(0.6)
        preview = frame("Two balances. One configurable reset countdown.")
        preview.save(output / "preview.png")
        frames.extend([preview] * 5)
        for index in range(10):
            app.move(100 + index * 10, 180)
            pump(0.05)
            frames.append(frame("Drag the strip", 24 + index * 10))
        app.refresh()
        pump(0.04)
        busy = frame("Refresh: immediate busy feedback", 114)
        frames.extend([busy] * 4)
        pump(0.6)
        frames.extend([frame("Demo refresh complete", 114)] * 4)
        app.state["color"] = "#64d9c1"
        app.apply_color()
        pump(0.1)
        frames.extend([frame("Change the numbers' color; brand icons stay unchanged", 114)] * 7)
        frames[0].save(output / "demo.gif", save_all=True, append_images=frames[1:],
                       duration=180, loop=0, disposal=2, optimize=False)
        print(f"Captured demo-only media: {app.root.winfo_width()}x{app.root.winfo_height()} strip, {len(frames)} frames")
    finally:
        app.close()


if __name__ == "__main__":
    main()
