import os
import sys
from pathlib import Path
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QPixmap, QPainter, QGuiApplication
from PySide6.QtSvg import QSvgRenderer
from PIL import Image

app = QGuiApplication(sys.argv)

assets_dir = Path("assets")
assets_dir.mkdir(exist_ok=True)

svg_code = """<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <!-- Left/Top Dark Green Speech Bubble -->
  <path fill="#5CB868" d="M 200 40 C 95 40 10 115 10 208 C 10 250 27 288 57 318 C 47 358 25 390 5 405 C 45 405 90 385 123 362 C 147 371 173 376 200 376 C 305 376 390 301 390 208 C 390 115 305 40 200 40 Z" />

  <!-- Hiragana 'あ' Text inside left bubble -->
  <text x="195" y="272" fill="#E8F7E8" font-family="'Segoe UI', 'MS Gothic', 'Yu Gothic', sans-serif" font-weight="bold" font-size="190" text-anchor="middle">あ</text>

  <!-- Right/Bottom Light Green Speech Bubble -->
  <path fill="#E8F7E8" d="M 325 180 C 230 180 150 248 150 332 C 150 370 166 404 193 431 C 184 467 164 496 146 510 C 182 510 223 492 253 471 C 275 479 299 484 325 484 C 420 484 500 416 500 332 C 500 248 420 180 325 180 Z" />

  <!-- Capital 'A' Text inside right bubble -->
  <text x="325" y="415" fill="#5CB868" font-family="'Segoe UI', 'Arial', sans-serif" font-weight="800" font-size="210" text-anchor="middle">A</text>
</svg>"""

svg_path = assets_dir / "app_icon.svg"
png_path = assets_dir / "app_icon.png"
ico_path = assets_dir / "app_icon.ico"

with open(svg_path, "w", encoding="utf-8") as f:
    f.write(svg_code)

byte_arr = QByteArray(svg_code.encode("utf-8"))
renderer = QSvgRenderer(byte_arr)

pixmap = QPixmap(512, 512)
pixmap.fill(Qt.GlobalColor.transparent)
painter = QPainter(pixmap)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
renderer.render(painter)
painter.end()

pixmap.save(str(png_path), "PNG")

img = Image.open(png_path)
img.save(ico_path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

# Generate Checkmark icons for QCheckBox (dark check & white check)
check_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
    <polyline points="20 6 9 17 4 12"/>
</svg>"""

for name, color in [("check_dark.png", "#12141A"), ("check_white.png", "#FFFFFF")]:
    r = QSvgRenderer(QByteArray(check_svg.format(color=color).encode("utf-8")))
    p = QPixmap(32, 32)
    p.fill(Qt.GlobalColor.transparent)
    ptr = QPainter(p)
    ptr.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(ptr)
    ptr.end()
    p.save(str(assets_dir / name), "PNG")

print("Generated icon files & checkmark icons successfully in assets/")
