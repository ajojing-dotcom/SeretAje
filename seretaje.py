"""SeretAje: tahan Shift sambil menyeret file, lepas di cincin untuk mengubah atau mengolahnya."""

import io
import json
import math
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF = True
except Exception:
    HEIF = False

from PySide6.QtCore import QLockFile, QObject, QPointF, QRectF, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import (QAction, QColor, QCursor, QFont, QGuiApplication, QIcon, QImage,
                           QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QShortcut)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QColorDialog, QComboBox, QDialog,
                               QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMenu, QMessageBox, QProgressBar, QPushButton,
                               QSlider, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

APP = "SeretAje"
IS_WIN = sys.platform == "win32"
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".ico"}
if HEIF:
    IMG_EXT |= {".heic", ".heif"}

# ---------------------------------------------------------------- tampilan

LIGHT = dict(bg="#F7F2EA", surface="#FFFFFF", ink="#231B14", muted="#6B5E52", line="#E2D8CB",
             accent="#C2541F", on_accent="#FFFFFF", canvas="#E9E0D3")
DARK = dict(bg="#1E1915", surface="#29221C", ink="#F3ECE3", muted="#B5A796", line="#3D342C",
            accent="#E5743A", on_accent="#1E1915", canvas="#14110E")
T = LIGHT
FONT = "Segoe UI Variable Text"


def system_dark():
    if not IS_WIN:
        return False
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def qss(t):
    return f"""
    QDialog {{ background:{t['bg']}; }}
    QWidget {{ color:{t['ink']}; font-family:'{FONT}','Segoe UI',sans-serif; font-size:13px; }}
    QLabel {{ background:transparent; }}
    QLabel[muted="true"] {{ color:{t['muted']}; }}
    QLabel#title {{ font-size:17px; font-weight:600; }}
    QLabel#group {{ color:{t['muted']}; font-size:12px; font-weight:600; padding-top:6px; }}
    QPushButton {{ background:{t['surface']}; color:{t['ink']}; border:1px solid {t['line']};
                   border-radius:6px; padding:6px 12px; min-height:22px; }}
    QPushButton:hover {{ border-color:{t['muted']}; }}
    QPushButton:checked {{ background:{t['ink']}; color:{t['bg']}; border-color:{t['ink']}; }}
    QPushButton:focus {{ outline:none; border:2px solid {t['accent']}; }}
    QPushButton:disabled {{ color:{t['muted']}; background:{t['bg']}; }}
    QPushButton#primary {{ background:{t['accent']}; color:{t['on_accent']}; border-color:{t['accent']};
                           font-weight:600; padding:6px 18px; }}
    QPushButton#primary:focus {{ border:2px solid {t['ink']}; }}
    QPushButton#primary:disabled {{ background:{t['line']}; color:{t['muted']}; border-color:{t['line']}; }}
    QPushButton#swatch {{ padding:0; min-height:0; border-radius:5px; }}
    QPushButton#swatch:checked {{ border:3px solid {t['ink']}; }}
    QSlider::groove:horizontal {{ height:4px; background:{t['line']}; border-radius:2px; }}
    QSlider::sub-page:horizontal {{ background:{t['ink']}; border-radius:2px; }}
    QSlider::handle:horizontal {{ background:{t['surface']}; border:2px solid {t['ink']};
                                  width:14px; height:14px; margin:-7px 0; border-radius:8px; }}
    QSlider:focus::handle:horizontal {{ border-color:{t['accent']}; }}
    QFrame#toast {{ background:{t['surface']}; border:1px solid {t['line']}; border-radius:10px; }}
    QProgressBar {{ background:{t['line']}; border:none; border-radius:2px; max-height:4px; }}
    QProgressBar::chunk {{ background:{t['accent']}; border-radius:2px; }}
    QMenu {{ background:{t['surface']}; border:1px solid {t['line']}; padding:4px; }}
    QMenu::item {{ padding:6px 18px; border-radius:4px; }}
    QMenu::item:selected {{ background:{t['bg']}; }}
    QLineEdit, QComboBox {{ background:{t['surface']}; color:{t['ink']}; border:1px solid {t['line']};
                            border-radius:6px; padding:5px 8px; min-height:22px; }}
    QLineEdit:focus, QComboBox:focus {{ border:2px solid {t['accent']}; }}
    QComboBox QAbstractItemView {{ background:{t['surface']}; color:{t['ink']}; selection-background-color:{t['bg']};
                                   selection-color:{t['ink']}; border:1px solid {t['line']}; }}
    QListWidget {{ background:{t['canvas']}; border:none; border-radius:8px; padding:8px; outline:none; }}
    QListWidget:focus {{ border:2px solid {t['accent']}; }}
    QListWidget::item {{ color:{t['ink']}; border:2px solid transparent; border-radius:6px; padding:4px; }}
    QListWidget::item:selected {{ background:{t['surface']}; color:{t['ink']}; border:2px solid {t['accent']}; }}
    QListWidget::item:hover {{ background:{t['surface']}; }}
    """


# ---------------------------------------------------------------- pengaturan

def config_dir():
    d = Path(os.environ.get("APPDATA") or Path.home() / ".config") / APP
    d.mkdir(parents=True, exist_ok=True)
    return d


DEFAULTS = {"aktif": True, "explorer_saja": True, "sapaan_awal": True, "gabung": {}}


def load_config():
    try:
        data = json.loads((config_dir() / "config.json").read_text(encoding="utf-8"))
        return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_config(cfg):
    try:
        (config_dir() / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except OSError:
        pass


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = pyw if pyw.exists() else Path(sys.executable)
    return f'"{exe}" "{Path(__file__).resolve()}"'


def get_autostart():
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP)
            return True
    except OSError:
        return False


def set_autostart(on):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, APP)
            except OSError:
                pass


# ---------------------------------------------------------------- olah file

def kind_of(p):
    ext = Path(p).suffix.lower()
    if ext in IMG_EXT:
        return "image"
    if ext == ".pdf" and fitz is not None:
        return "pdf"
    return "other"


def format_name(p):
    ext = Path(p).suffix.lower().lstrip(".")
    return {"jpeg": "JPG", "tif": "TIFF", "heif": "HEIC"}.get(ext, ext.upper())


def formats_for(paths):
    kinds = {kind_of(p) for p in paths}
    if not paths or "other" in kinds:
        return []
    if kinds == {"pdf"}:
        return ["JPG", "PNG"]
    if kinds == {"image"}:
        own = {format_name(p) for p in paths}
        pool = ["JPG", "PNG", "WEBP", "PDF", "ICO"]
        if len(own) == 1:
            pool = [f for f in pool if f not in own]
        return pool[:4]
    return ["PDF"]


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024


def out_path(src, tag, ext):
    src = Path(src)
    stem = src.stem + (f" - {tag}" if tag else "")
    p = src.with_name(stem + ext)
    i = 2
    while p.exists():
        p = src.with_name(f"{stem} ({i}){ext}")
        i += 1
    return p


def has_alpha(im):
    if im.mode in ("RGBA", "LA"):
        return im.getchannel("A").getextrema()[0] < 255
    return im.mode == "P" and "transparency" in im.info


def open_image(p):
    im = Image.open(p)
    im.load()
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if has_alpha(im) else "RGB")
    return im


def flatten(im, color=(255, 255, 255)):
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, color)
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    return im.convert("RGB")


def pdf_page_count(p):
    with fitz.open(p) as doc:
        return doc.page_count


def render_pdf_page(p, index, dpi=150):
    with fitz.open(p) as doc:
        pix = doc[index].get_pixmap(dpi=dpi, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def save_image(im, path, quality=90):
    path = Path(path)
    ext = path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        flatten(im).save(path, "JPEG", quality=quality, optimize=True, progressive=True)
    elif ext == ".png":
        im.save(path, "PNG", optimize=True)
    elif ext == ".webp":
        im.save(path, "WEBP", quality=quality, method=6)
    elif ext == ".ico":
        side = max(im.size)
        sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        sq.paste(im.convert("RGBA"), ((side - im.width) // 2, (side - im.height) // 2))
        sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256) if s <= side] or [(16, 16)]
        sq.save(path, "ICO", sizes=sizes)
    elif ext == ".pdf":
        flatten(im).save(path, "PDF", resolution=150)
    else:
        im.save(path)
    return path


def edit_ext(src, im):
    """Ekstensi hasil olahan: ikuti file asal kalau bisa, PNG kalau perlu transparansi."""
    ext = Path(src).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        return ".png" if im.mode == "RGBA" and has_alpha(im) else ext
    return ext if ext in (".png", ".webp") else ".png"


def op_convert(paths, fmt, progress=lambda i, n: None):
    ext = "." + fmt.lower()
    outs = []
    if fmt == "PDF" and len(paths) > 1:
        out = out_path(paths[0], "gabungan", ".pdf")
        doc = fitz.open()
        for i, p in enumerate(paths):
            progress(i, len(paths))
            if kind_of(p) == "pdf":
                with fitz.open(p) as src:
                    doc.insert_pdf(src)
            else:
                buf = io.BytesIO()
                flatten(open_image(p)).save(buf, "JPEG", quality=92)
                with fitz.open(stream=buf.getvalue(), filetype="jpeg") as img:
                    with fitz.open("pdf", img.convert_to_pdf()) as one:
                        doc.insert_pdf(one)
        doc.save(out, garbage=3, deflate=True)
        doc.close()
        progress(len(paths), len(paths))
        return [out], f"{len(paths)} file digabung jadi satu PDF"
    for i, p in enumerate(paths):
        progress(i, len(paths))
        if kind_of(p) == "pdf":
            n = pdf_page_count(p)
            for k in range(n):
                tag = "" if n == 1 else f"hal {k + 1:02d}"
                outs.append(save_image(render_pdf_page(p, k, 200), out_path(p, tag, ext)))
        else:
            outs.append(save_image(open_image(p), out_path(p, "", ext)))
    progress(len(paths), len(paths))
    return outs, f"{len(outs)} file {fmt} dibuat" if len(outs) > 1 else outs[0].name


def op_compress(paths, progress=lambda i, n: None):
    outs, before_total, after_total, skipped = [], 0, 0, 0
    for i, p in enumerate(paths):
        progress(i, len(paths))
        before = Path(p).stat().st_size
        if kind_of(p) == "pdf":
            out = out_path(p, "kecil", ".pdf")
            with fitz.open(p) as doc:
                if hasattr(doc, "rewrite_images"):
                    try:
                        doc.rewrite_images(dpi_threshold=200, dpi_target=150, quality=70)
                    except Exception:
                        pass
                doc.save(out, garbage=4, deflate=True, clean=True)
        else:
            im = open_image(p)
            if max(im.size) > 2560:
                im.thumbnail((2560, 2560), Image.LANCZOS)
            ext = Path(p).suffix.lower()
            if ext == ".png":
                out = out_path(p, "kecil", ".png")
                q = im.quantize(colors=256, method=Image.FASTOCTREE if im.mode == "RGBA" else Image.MEDIANCUT)
                q.save(out, "PNG", optimize=True)
            elif ext == ".webp":
                out = save_image(im, out_path(p, "kecil", ".webp"), quality=72)
            else:
                out = save_image(im, out_path(p, "kecil", edit_ext(p, im) if ext in (".jpg", ".jpeg") else ".jpg"), quality=72)
        after = out.stat().st_size
        if after >= before * 0.97:
            out.unlink()
            skipped += 1
            continue
        outs.append(out)
        before_total += before
        after_total += after
    progress(len(paths), len(paths))
    if not outs:
        return [], "File sudah ringkas, tidak ada file baru"
    msg = f"{human_size(before_total)} jadi {human_size(after_total)}"
    if skipped:
        msg += f", {skipped} file sudah ringkas"
    return outs, msg


def op_strip(paths, progress=lambda i, n: None):
    outs, gps = [], 0
    for i, p in enumerate(paths):
        progress(i, len(paths))
        if kind_of(p) == "pdf":
            out = out_path(p, "bersih", ".pdf")
            with fitz.open(p) as doc:
                doc.set_metadata({})
                doc.del_xml_metadata()
                doc.save(out, garbage=4, deflate=True)
        else:
            with Image.open(p) as raw:
                if 0x8825 in raw.getexif():
                    gps += 1
                icc = raw.info.get("icc_profile")
            im = open_image(p)
            out = out_path(p, "bersih", edit_ext(p, im))
            kw = {"icc_profile": icc} if icc and out.suffix.lower() != ".webp" else {}
            if out.suffix.lower() in (".jpg", ".jpeg"):
                flatten(im).save(out, "JPEG", quality=95, **kw)
            else:
                im.save(out, **kw)
        outs.append(out)
    progress(len(paths), len(paths))
    msg = "Metadata dihapus"
    if gps:
        msg += ", termasuk lokasi GPS" if gps == 1 else f", termasuk lokasi GPS di {gps} file"
    return outs, msg


def apply_redact(im, boxes, mode):
    im = im.copy()
    draw = ImageDraw.Draw(im)
    for b in boxes:
        x0, y0 = max(0, int(b[0])), max(0, int(b[1]))
        x1, y1 = min(im.width, int(b[2])), min(im.height, int(b[3]))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        if mode == "hitam":
            draw.rectangle((x0, y0, x1, y1), fill="black")
            continue
        region = im.crop((x0, y0, x1, y1))
        w, h = region.size
        if mode == "piksel":
            block = max(6, min(w, h) // 5)
            region = region.resize((max(1, w // block), max(1, h // block)), Image.BILINEAR).resize((w, h), Image.NEAREST)
        else:
            small = region.resize((max(1, w // 8), max(1, h // 8)), Image.BILINEAR)
            region = small.resize((w, h), Image.BILINEAR).filter(ImageFilter.GaussianBlur(max(4, min(w, h) / 6)))
        im.paste(region, (x0, y0))
    return im


EDIT_DEFAULT = dict(rot=0, flip_h=False, flip_v=False, terang=0, kontras=0, warna=0, tajam=0, skala=100)


def apply_edit(im, s, resize=True):
    if s["rot"]:
        im = im.rotate(-90 * s["rot"], expand=True)
    if s["flip_h"]:
        im = ImageOps.mirror(im)
    if s["flip_v"]:
        im = ImageOps.flip(im)
    alpha = im.getchannel("A") if im.mode == "RGBA" else None
    rgb = im.convert("RGB")
    for key, enh in (("terang", ImageEnhance.Brightness), ("kontras", ImageEnhance.Contrast),
                     ("warna", ImageEnhance.Color), ("tajam", ImageEnhance.Sharpness)):
        if s[key]:
            rgb = enh(rgb).enhance(1 + s[key] / 100)
    if alpha is not None:
        rgb.putalpha(alpha)
    if resize and s["skala"] != 100:
        k = s["skala"] / 100
        rgb = rgb.resize((max(1, round(rgb.width * k)), max(1, round(rgb.height * k))), Image.LANCZOS)
    return rgb


GRADIENTS = [
    ("Senja", ("#FFC371", "#FF7A45", "#E8505B", "#9D5CC9")),
    ("Laut", ("#9BE3F0", "#3D8BDB", "#5CC9E8", "#1D4E89")),
    ("Daun", ("#D8F3C4", "#6BBF59", "#A8DE8A", "#2D6A4F")),
    ("Pasir", ("#F8EBD3", "#E9C46A", "#F4A261", "#B9773E")),
    ("Malam", ("#3A3D5C", "#6B5F8A", "#1C1C2E", "#4A4E69")),
    ("Jambu", ("#FFE1E8", "#FF8FAB", "#FFC2D1", "#E0567E")),
]
SOLIDS = [("Putih", "#FFFFFF"), ("Krem", "#F7F2EA"), ("Abu", "#D6D3CF"), ("Hitam", "#141414"), ("Biru", "#1F5FBF")]
LATAR_DEFAULT = dict(bg=("grad", GRADIENTS[0][1]), pad=10, radius=3, shadow=40, ratio=None)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def make_background(w, h, bg):
    kind, val = bg
    if kind == "none":
        return Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if kind == "solid":
        return Image.new("RGBA", (w, h), hex_rgb(val) + (255,))
    corners = Image.new("RGB", (2, 2))
    corners.putdata([hex_rgb(c) for c in val])
    return corners.resize((w, h), Image.BILINEAR, box=(0.5, 0.5, 1.5, 1.5)).convert("RGBA")


def rounded_mask(size, radius):
    w, h = size
    ss = 2 if max(w, h) < 3000 else 1
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=radius * ss, fill=255)
    return m.resize((w, h), Image.LANCZOS) if ss > 1 else m


def compose_background(im, o):
    im = im.convert("RGBA")
    w, h = im.size
    longest = max(w, h)
    pad = int(longest * o["pad"] / 100)
    W, H = w + 2 * pad, h + 2 * pad
    if o["ratio"]:
        if W / H < o["ratio"]:
            W = int(round(H * o["ratio"]))
        else:
            H = int(round(W / o["ratio"]))
    canvas = make_background(W, H, o["bg"])
    x, y = (W - w) // 2, (H - h) // 2
    mask = rounded_mask((w, h), int(min(w, h) * o["radius"] / 100))
    if o["shadow"]:
        s = o["shadow"] / 100
        sh = Image.new("L", (W, H), 0)
        sh.paste(mask.point(lambda v: int(v * 0.55 * s)), (x, y + int(longest * 0.012 * s)))
        sh = sh.filter(ImageFilter.GaussianBlur(max(2, longest * 0.025 * s)))
        canvas = Image.composite(Image.new("RGBA", (W, H), (0, 0, 0, 255)), canvas, sh) if o["bg"][0] != "none" \
            else Image.merge("RGBA", (*Image.new("RGB", (W, H), 0).split(), sh))
    im.putalpha(ImageChops.multiply(im.getchannel("A"), mask))
    canvas.alpha_composite(im, (x, y))
    return canvas


def pil_to_qimage(im):
    im = im.convert("RGBA")
    return QImage(im.tobytes("raw", "RGBA"), im.width, im.height, im.width * 4,
                  QImage.Format.Format_RGBA8888).copy()


def qimage_to_pil(qi):
    qi = qi.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombuffer("RGBA", (qi.width(), qi.height()), bytes(qi.constBits()),
                            "raw", "RGBA", qi.bytesPerLine(), 1).copy()


def fit_preview(im, limit=1400):
    if max(im.size) <= limit:
        return im.copy()
    p = im.copy()
    p.thumbnail((limit, limit), Image.LANCZOS)
    return p


def friendly(e):
    if isinstance(e, PermissionError):
        return "File sedang dipakai program lain, atau folder ini tidak bisa ditulisi."
    if isinstance(e, UnidentifiedImageError):
        return "File gambar ini tidak bisa dibaca."
    if isinstance(e, FileNotFoundError):
        return "File asal sudah dipindah atau dihapus."
    if isinstance(e, MemoryError):
        return "Gambar terlalu besar untuk diolah."
    text = str(e).strip() or e.__class__.__name__
    return text[:180]


def reveal(path):
    path = Path(path)
    if IS_WIN:
        subprocess.Popen(f'explorer /select,"{path}"')
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])


# ---------------------------------------------------------------- cincin

ACTIONS = [
    ("kecilkan", "Kecilkan", "Kecilkan ukuran file"),
    ("metadata", "Metadata", "Hapus metadata (EXIF, GPS)"),
    ("edit", "Edit", "Putar, cerahkan, ubah ukuran"),
    ("tandai", "Tandai", "Coret, panah, kotak, teks"),
    ("latar", "Latar", "Pasang di atas latar"),
    ("potong", "Potong", "Potong bagian yang perlu"),
    ("sensor", "Sensor", "Tutup bagian rahasia"),
]


def sector_path(c, r1, r2, a0, span):
    """Potongan cincin. a0 dalam derajat searah jarum jam dari arah jam 12."""
    outer = QRectF(c.x() - r2, c.y() - r2, 2 * r2, 2 * r2)
    inner = QRectF(c.x() - r1, c.y() - r1, 2 * r1, 2 * r1)
    qa = 90 - a0
    path = QPainterPath()
    path.arcMoveTo(outer, qa)
    path.arcTo(outer, qa, -span)
    path.arcTo(inner, qa - span, span)
    path.closeSubpath()
    return path


def draw_glyph(p, key, c, s, col):
    p.save()
    p.translate(c)
    h = s / 2
    pen = QPen(col, 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    P = QPointF
    if key == "kecilkan":
        for sx, sy in ((-1, -1), (1, 1)):
            p.drawLine(P(sx * h, sy * h), P(sx * h * .2, sy * h * .2))
            p.drawPolyline([P(sx * h * .2, sy * h * .75), P(sx * h * .2, sy * h * .2), P(sx * h * .75, sy * h * .2)])
    elif key == "metadata":
        p.drawPolygon(QPolygonF([P(-h, 0), P(-h * .35, -h * .7), P(h, -h * .7), P(h, h * .7), P(-h * .35, h * .7)]))
        p.drawEllipse(P(-h * .3, 0), h * .14, h * .14)
    elif key == "edit":
        for y, kx in ((-.6, .45), (0, -.35), (.6, .15)):
            p.drawLine(P(-h, y * h), P(h, y * h))
            p.setBrush(col)
            p.drawEllipse(P(kx * h, y * h), h * .22, h * .22)
            p.setBrush(Qt.BrushStyle.NoBrush)
    elif key == "tandai":
        thick = QPen(pen)
        thick.setWidthF(2.6)
        p.setPen(thick)
        p.drawLine(P(-h * .55, h * .35), P(h * .8, -h * 1.0))
        p.setPen(pen)
        wave = QPainterPath(P(-h, h * .85))
        wave.cubicTo(P(-h * .4, h * .45), P(h * .2, h * 1.2), P(h, h * .75))
        p.drawPath(wave)
    elif key == "latar":
        p.drawRoundedRect(QRectF(-h, -h, 2 * h, 2 * h), 3, 3)
        p.setBrush(col)
        p.drawRect(QRectF(-h * .45, -h * .45, h * .9, h * .9))
    elif key == "potong":
        p.drawPolyline([P(-h * .55, -h), P(-h * .55, h * .55), P(h, h * .55)])
        p.drawPolyline([P(-h, -h * .55), P(h * .55, -h * .55), P(h * .55, h)])
    elif key == "sensor":
        p.drawLine(P(-h, -h * .65), P(h, -h * .65))
        p.drawLine(P(-h, h * .65), P(h * .4, h * .65))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRect(QRectF(-h, -h * .22, 2 * h, h * .44))
    p.restore()


def pick_drop_action(e):
    """Selalu salin, jangan pindahkan: Shift di Explorer berarti 'pindah', file asal harus tetap aman."""
    possible = e.possibleActions()
    if possible & Qt.DropAction.CopyAction:
        return Qt.DropAction.CopyAction
    if possible & Qt.DropAction.LinkAction:
        return Qt.DropAction.LinkAction
    return None


class Ring(QWidget):
    dropped = Signal(str, str, list)

    R, HUB, GAP, PAD, CAP = 150, 62, 7, 26, 48

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        side = 2 * (self.R + self.PAD)
        self.setFixedSize(side, side + self.CAP)
        self.center = QPointF(side / 2, side / 2)
        self.paths, self.formats, self.hover = [], [], None
        self.actions_ok = True
        self.pinned = False
        self.pin_timer = QTimer(self, singleShot=True, interval=30000, timeout=self.hide)

    def popup_near(self, pos, pinned=False):
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        half = self.R + self.PAD
        cx = pos.x() + self.R + 40
        if cx + half > geo.right():
            cx = pos.x() - self.R - 40
        cx = min(max(cx, geo.left() + half), geo.right() - half)
        cy = min(max(pos.y(), geo.top() + half), geo.bottom() - half - self.CAP)
        self.move(int(cx - half), int(cy - half))
        self.paths, self.formats, self.hover, self.actions_ok = [], [], None, True
        self.pinned = pinned
        if pinned:
            self.pin_timer.start()
        self.show()
        self.raise_()
        self.update()

    def hide_if_idle(self):
        if not self.pinned:
            self.hide()

    def hideEvent(self, e):
        self.pinned = False
        self.pin_timer.stop()
        super().hideEvent(e)

    def mousePressEvent(self, e):
        self.hide()

    def hit(self, pt):
        dx, dy = pt.x() - self.center.x(), pt.y() - self.center.y()
        d = math.hypot(dx, dy)
        a = (math.degrees(math.atan2(dy, dx)) + 90) % 360
        if d <= self.HUB:
            if not self.formats:
                return None
            n = len(self.formats)
            return ("format", self.formats[int(a // (360 / n)) % n])
        if self.HUB + self.GAP <= d <= self.R and self.actions_ok:
            step = 360 / len(ACTIONS)
            return ("aksi", ACTIONS[int(((a + step / 2) % 360) // step)][0])
        return None

    def dragEnterEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        paths = [p for p in paths if os.path.isfile(p)]
        if not paths:
            e.ignore()
            return
        action = pick_drop_action(e)
        if action is None:
            e.ignore()
            return
        self.paths = paths
        self.formats = formats_for(paths)
        self.actions_ok = "other" not in {kind_of(p) for p in paths}
        self.hover = self.hit(e.position())
        if self.pinned:
            self.pin_timer.start()
        self.update()
        e.setDropAction(action)
        e.accept()

    def dragMoveEvent(self, e):
        self._track(e)

    def _track(self, e):
        target = self.hit(e.position())
        if target != self.hover:
            self.hover = target
            self.update()
        action = pick_drop_action(e)
        if target and action is not None:
            e.setDropAction(action)
            e.accept()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self.hover = None
        self.update()

    def dropEvent(self, e):
        target, action = self.hit(e.position()), pick_drop_action(e)
        if not target or action is None:
            e.ignore()
            return
        e.setDropAction(action)
        e.accept()
        paths = list(self.paths)
        self.hide()
        # Explorer menunggu sampai dropEvent selesai, jadi pekerjaan berat dijalankan setelahnya.
        QTimer.singleShot(0, lambda: self.dropped.emit(target[0], target[1], paths))

    def caption(self):
        if not self.paths:
            return "Seret file ke sini, klik untuk tutup" if self.pinned else "Lepas di salah satu pilihan"
        if not self.actions_ok:
            return "Jenis file ini belum didukung"
        n = len(self.paths)
        name = Path(self.paths[0]).name
        who = (name if len(name) <= 30 else name[:27] + "...") if n == 1 else f"{n} file"
        if self.hover is None:
            return who
        kind, key = self.hover
        if kind == "format":
            if key == "PDF":
                return f"Atur dan gabung jadi PDF, {who}" if all(kind_of(p) == "image" for p in self.paths) \
                    else f"Gabung jadi satu PDF, {who}"
            return f"Ubah ke {key}, {who}"
        return f"{next(a[2] for a in ACTIONS if a[0] == key)}, {who}"

    def paintEvent(self, _):
        t = T
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c, R, HUB = self.center, self.R, self.HUB
        p.setPen(Qt.PenStyle.NoPen)
        # Bayangan tipis: cincin melayang di atas jendela lain, perlu dipisah dari latar apa pun.
        for k in range(12, 0, -2):
            p.setBrush(QColor(0, 0, 0, 7))
            p.drawEllipse(c + QPointF(0, 5), R + k, R + k)
        base = QColor(t["surface"])
        base.setAlpha(248)
        p.setBrush(base)
        p.setPen(QPen(QColor(t["line"]), 1))
        p.drawEllipse(c, R, R)

        step = 360 / len(ACTIONS)
        enabled = self.actions_ok
        label_font = QFont(FONT)
        label_font.setPixelSize(12)
        label_font.setWeight(QFont.Weight.DemiBold)
        p.setFont(label_font)
        for i, (key, label, _) in enumerate(ACTIONS):
            hovered = self.hover == ("aksi", key)
            path = sector_path(c, HUB + self.GAP, R - 6, i * step - step / 2 + 1.4, step - 2.8)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t["accent"] if hovered else t["bg"]))
            p.drawPath(path)
            ink = QColor(t["on_accent"] if hovered else (t["ink"] if enabled else t["muted"]))
            mid = (HUB + self.GAP + R - 6) / 2
            ang = math.radians(i * step - 90)
            pos = c + QPointF(math.cos(ang) * mid, math.sin(ang) * mid)
            draw_glyph(p, key, pos + QPointF(0, -9), 16, ink)
            p.setPen(ink)
            p.drawText(QRectF(pos.x() - 44, pos.y() + 5, 88, 18), Qt.AlignmentFlag.AlignCenter, label)

        # Pusat cincin: tombol ubah format, aksi utama, jadi diberi warna paling kontras.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t["ink"]))
        p.drawEllipse(c, HUB, HUB)
        hub_font = QFont(FONT)
        hub_font.setPixelSize(13)
        hub_font.setWeight(QFont.Weight.Bold)
        small = QFont(FONT)
        small.setPixelSize(11)
        n = len(self.formats)
        if n:
            wedge = 360 / n
            for i, fmt in enumerate(self.formats):
                hovered = self.hover == ("format", fmt)
                if hovered:
                    p.setBrush(QColor(t["accent"]))
                    if n == 1:
                        p.drawEllipse(c, HUB, HUB)
                    else:
                        pie = QPainterPath(c)
                        pie.arcTo(QRectF(c.x() - HUB, c.y() - HUB, 2 * HUB, 2 * HUB), 90 - i * wedge, -wedge)
                        pie.closeSubpath()
                        p.drawPath(pie)
                if n == 1:
                    pos = c
                else:
                    ang = math.radians(i * wedge + wedge / 2 - 90)
                    pos = c + QPointF(math.cos(ang) * HUB * .55, math.sin(ang) * HUB * .55)
                p.setPen(QColor(t["on_accent"] if hovered else t["bg"]))
                if n == 1:
                    p.setFont(small)
                    p.drawText(QRectF(pos.x() - 50, pos.y() - 22, 100, 18), Qt.AlignmentFlag.AlignCenter, "Ubah ke")
                    p.setFont(hub_font)
                    p.drawText(QRectF(pos.x() - 50, pos.y() - 4, 100, 22), Qt.AlignmentFlag.AlignCenter, fmt)
                else:
                    p.setFont(hub_font)
                    p.drawText(QRectF(pos.x() - 30, pos.y() - 11, 60, 22), Qt.AlignmentFlag.AlignCenter, fmt)
                p.setPen(Qt.PenStyle.NoPen)
            if n > 1:
                p.setPen(QPen(QColor(t["surface"]), 2))
                for i in range(n):
                    ang = math.radians(i * wedge - 90)
                    p.drawLine(c, c + QPointF(math.cos(ang) * HUB, math.sin(ang) * HUB))
        else:
            p.setPen(QColor(t["bg"]))
            p.setFont(small)
            p.drawText(QRectF(c.x() - HUB, c.y() - 20, 2 * HUB, 40), Qt.AlignmentFlag.AlignCenter,
                       "Ubah\nformat" if not self.paths else "Tidak ada\nformat")

        text = self.caption()
        cap_font = QFont(FONT)
        cap_font.setPixelSize(13)
        p.setFont(cap_font)
        tw = min(p.fontMetrics().horizontalAdvance(text) + 28, self.width() - 8)
        box = QRectF(c.x() - tw / 2, c.y() + R + 14, tw, 32)
        p.setBrush(QColor(t["surface"]))
        p.setPen(QPen(QColor(t["line"]), 1))
        p.drawRoundedRect(box, 8, 8)
        p.setPen(QColor(t["ink"]))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, int(tw - 20)))


# ---------------------------------------------------------------- notifikasi

class Toast(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        frame = QFrame(self)
        frame.setObjectName("toast")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight:600;")
        self.detail = QLabel()
        self.detail.setProperty("muted", True)
        self.detail.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.open_btn = QPushButton("Buka folder")
        self.open_btn.clicked.connect(self._open)
        close_btn = QPushButton("Tutup")
        close_btn.clicked.connect(self.hide)
        row.addWidget(self.open_btn)
        row.addStretch()
        row.addWidget(close_btn)
        for w in (self.title, self.detail, self.bar):
            lay.addWidget(w)
        lay.addLayout(row)
        self.setFixedWidth(320)
        self.last = None
        self.timer = QTimer(self, singleShot=True, timeout=self.hide)

    def _open(self):
        if self.last:
            reveal(self.last)
        self.hide()

    def _place(self, anchor):
        self.adjustSize()
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        g = screen.availableGeometry()
        x = min(max(anchor.x() - self.width() // 2, g.left() + 8), g.right() - self.width() - 8)
        y = min(max(anchor.y() - self.height() // 2, g.top() + 8), g.bottom() - self.height() - 8)
        self.move(x, y)
        self.show()
        self.raise_()

    def progress(self, title, i, n, anchor):
        self.timer.stop()
        self.title.setText(title)
        self.detail.setText(f"{i} dari {n} file")
        self.bar.setRange(0, max(n, 1))
        self.bar.setValue(i)
        self.bar.show()
        self.open_btn.hide()
        self._place(anchor)

    def done(self, outs, title, detail, anchor):
        self.title.setText(title)
        self.detail.setText(detail)
        self.bar.hide()
        self.last = outs[0] if outs else None
        self.open_btn.setVisible(bool(outs))
        self._place(anchor)
        self.timer.start(7000)

    def error(self, title, detail, anchor):
        self.done([], title, detail, anchor)
        self.timer.start(10000)

    def enterEvent(self, e):
        self.timer.stop()

    def leaveEvent(self, e):
        if not self.bar.isVisible() and self.isVisible():
            self.timer.start(4000)


class Worker(QThread):
    step = Signal(int, int)
    finished_ok = Signal(list, str)
    failed = Signal(str)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try:
            outs, msg = self.fn(*self.args, progress=lambda i, n: self.step.emit(i, n))
            self.finished_ok.emit([str(o) for o in outs], msg)
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(friendly(e))


# ---------------------------------------------------------------- jendela olah

class Canvas(QWidget):
    """Menampilkan pratinjau; koordinat mouse diterjemahkan ke koordinat gambar asli."""

    def __init__(self, handler):
        super().__init__()
        self.h = handler
        self.qimg = None
        self.full_size = (1, 1)
        self.setMinimumSize(480, 360)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_image(self, qimg, full_size):
        self.qimg, self.full_size = qimg, full_size
        self.update()

    def view_rect(self):
        if not self.qimg:
            return QRectF()
        area = QRectF(self.rect()).adjusted(16, 16, -16, -16)
        fw, fh = self.full_size
        k = min(area.width() / fw, area.height() / fh)
        w, h = fw * k, fh * k
        return QRectF(area.center().x() - w / 2, area.center().y() - h / 2, w, h)

    def to_img(self, pt):
        r = self.view_rect()
        fw, fh = self.full_size
        return QPointF((pt.x() - r.x()) * fw / r.width(), (pt.y() - r.y()) * fh / r.height())

    def to_view(self, pt):
        r = self.view_rect()
        fw, fh = self.full_size
        return QPointF(r.x() + pt.x() * r.width() / fw, r.y() + pt.y() * r.height() / fh)

    def img_rect_to_view(self, rc):
        return QRectF(self.to_view(rc.topLeft()), self.to_view(rc.bottomRight()))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(T["canvas"]))
        if not self.qimg:
            return
        r = self.view_rect()
        if self.qimg.hasAlphaChannel():
            # Kotak-kotak hanya di area gambar, supaya bagian transparan kelihatan.
            p.save()
            p.setClipRect(r)
            s = 10
            for yy in range(int(r.top()), int(r.bottom()) + s, s):
                for xx in range(int(r.left()), int(r.right()) + s, s):
                    light = ((xx - int(r.left())) // s + (yy - int(r.top())) // s) % 2 == 0
                    p.fillRect(xx, yy, s, s, QColor("#FFFFFF" if light else "#D9D4CD"))
            p.restore()
        p.drawImage(r, self.qimg)
        if hasattr(self.h, "overlay"):
            self.h.overlay(p, self)
        if self.hasFocus():
            p.setPen(QPen(QColor(T["accent"]), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(self.rect()).adjusted(1, 1, -1, -1))

    def mousePressEvent(self, e):
        if hasattr(self.h, "press") and self.qimg:
            self.h.press(self.to_img(e.position()), e.position(), e)
            self.update()

    def mouseMoveEvent(self, e):
        if hasattr(self.h, "move") and self.qimg:
            self.h.move(self.to_img(e.position()), e.position(), e)
            self.update()

    def mouseReleaseEvent(self, e):
        if hasattr(self.h, "release") and self.qimg:
            self.h.release(self.to_img(e.position()), e.position(), e)
            self.update()

    def keyPressEvent(self, e):
        if hasattr(self.h, "key") and self.h.key(e):
            self.update()
            return
        super().keyPressEvent(e)

    def resizeEvent(self, e):
        self.update()


def swatch_css(fill):
    """Gaya per tombol warna. Ditulis lengkap di sini karena gaya per-widget menimpa gaya :checked aplikasi."""
    return (f"QPushButton {{ {fill} border:1px solid {T['line']}; border-radius:5px; }}"
            f"QPushButton:checked {{ border:3px solid {T['ink']}; }}"
            f"QPushButton:focus {{ border:3px solid {T['accent']}; }}")


def group_label(text):
    lab = QLabel(text)
    lab.setObjectName("group")
    return lab


def toggle_row(options, current, on_pick):
    """Barisan tombol pilihan tunggal. options: [(label, nilai)]."""
    wrap = QWidget()
    grid = QGridLayout(wrap)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(6)
    group = QButtonGroup(wrap)
    for i, (label, value) in enumerate(options):
        b = QPushButton(label)
        b.setCheckable(True)
        b.setChecked(value == current)
        b.clicked.connect(lambda _=False, v=value: on_pick(v))
        group.addButton(b)
        grid.addWidget(b, i // 3, i % 3)
    wrap.group = group
    return wrap


def slider_row(label, lo, hi, value, on_change, suffix=""):
    wrap = QWidget()
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    head = QHBoxLayout()
    name = QLabel(label)
    val = QLabel(f"{value}{suffix}")
    val.setProperty("muted", True)
    head.addWidget(name)
    head.addStretch()
    head.addWidget(val)
    s = QSlider(Qt.Orientation.Horizontal)
    s.setRange(lo, hi)
    s.setValue(value)
    s.setAccessibleName(label)

    def changed(v):
        val.setText(f"{v}{suffix}")
        on_change(v)
    s.valueChanged.connect(changed)
    lay.addLayout(head)
    lay.addWidget(s)
    wrap.slider, wrap.val = s, val
    return wrap


class BaseDialog(QDialog):
    title = ""
    verb = "Simpan"
    multipage = True

    def __init__(self, src):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.src = Path(src)
        self.is_pdf = kind_of(src) == "pdf"
        self.pages = pdf_page_count(src) if self.is_pdf else 1
        self.page = 0
        self.outputs = []
        self.init_state()
        self.setWindowTitle(f"{self.title}: {self.src.name}")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)
        head = QHBoxLayout()
        t = QLabel(self.title)
        t.setObjectName("title")
        f = QLabel(self.src.name)
        f.setProperty("muted", True)
        head.addWidget(t)
        head.addSpacing(10)
        head.addWidget(f, 1)
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(18)
        self.canvas = Canvas(self)
        body.addWidget(self.canvas, 1)
        side_w = QWidget()
        side_w.setFixedWidth(260)
        self.side = QVBoxLayout(side_w)
        self.side.setContentsMargins(0, 0, 0, 0)
        self.side.setSpacing(8)
        body.addWidget(side_w)
        root.addLayout(body, 1)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.page_label = QLabel()
        self.page_label.setProperty("muted", True)
        if self.is_pdf and self.pages > 1 and self.multipage:
            self.prev_btn = QPushButton("Halaman sebelumnya")
            self.next_btn = QPushButton("Halaman berikutnya")
            self.prev_btn.clicked.connect(lambda: self.load_page(self.page - 1))
            self.next_btn.clicked.connect(lambda: self.load_page(self.page + 1))
            foot.addWidget(self.prev_btn)
            foot.addWidget(self.next_btn)
        foot.addWidget(self.page_label)
        foot.addStretch()
        cancel = QPushButton("Batal")
        cancel.clicked.connect(self.reject)
        self.ok_btn = QPushButton(self.verb)
        self.ok_btn.setObjectName("primary")
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self._save)
        foot.addWidget(cancel)
        foot.addWidget(self.ok_btn)
        root.addLayout(foot)

        self.build_controls()
        self.side.addStretch()
        self.load_page(0)
        self.resize(1080, 720)

    def init_state(self):
        pass

    def build_controls(self):
        pass

    def on_page(self):
        pass

    def load_page(self, i):
        self.page = max(0, min(i, self.pages - 1))
        self.full = render_pdf_page(self.src, self.page, 150) if self.is_pdf else open_image(self.src)
        self.preview = fit_preview(self.full)
        self.k = self.preview.width / self.full.width
        if self.is_pdf:
            note = f"Halaman {self.page + 1} dari {self.pages}"
            if not self.multipage and self.pages > 1:
                note += ", berlaku untuk semua halaman"
            self.page_label.setText(note)
            if hasattr(self, "prev_btn"):
                self.prev_btn.setEnabled(self.page > 0)
                self.next_btn.setEnabled(self.page < self.pages - 1)
        self.on_page()
        self.refresh()

    def render_preview(self):
        return self.preview

    def display_size(self):
        return self.full.size

    def refresh(self):
        self.canvas.set_image(pil_to_qimage(self.render_preview()), self.display_size())

    def page_tag(self, tag):
        return f"{tag} hal {self.page + 1}" if self.is_pdf and self.pages > 1 else tag

    def _save(self):
        try:
            self.outputs = [Path(o) for o in self.save()]
            self.accept()
        except Exception as e:
            traceback.print_exc()
            QMessageBox.warning(self, "Gagal menyimpan", friendly(e))


class CropDialog(BaseDialog):
    title = "Potong"
    verb = "Simpan potongan"
    multipage = False
    RATIOS = [("Bebas", None), ("1:1", 1.0), ("4:3", 4 / 3), ("3:4", 3 / 4), ("16:9", 16 / 9), ("A4", 1 / 1.4142)]

    def init_state(self):
        self.ratio = None
        self.sel = None
        self.drag = None

    def build_controls(self):
        self.side.addWidget(group_label("Rasio"))
        self.side.addWidget(toggle_row(self.RATIOS, None, self.set_ratio))
        self.size_label = QLabel()
        self.side.addWidget(group_label("Ukuran hasil"))
        self.side.addWidget(self.size_label)
        hint = QLabel("Seret di gambar untuk membuat kotak, tarik sudutnya untuk mengubah, "
                      "panah keyboard untuk menggeser.")
        hint.setWordWrap(True)
        hint.setProperty("muted", True)
        self.side.addWidget(hint)
        if self.is_pdf:
            pdf_note = QLabel("Untuk PDF, potongan yang sama dipakai di semua halaman.")
            pdf_note.setWordWrap(True)
            pdf_note.setProperty("muted", True)
            self.side.addWidget(pdf_note)
        reset = QPushButton("Pilih seluruh gambar")
        reset.clicked.connect(self.select_all)
        self.side.addWidget(reset)

    def on_page(self):
        if self.sel is None:
            self.select_all()

    def select_all(self):
        W, H = self.full.size
        self.sel = QRectF(0, 0, W, H)
        if self.ratio:
            self.set_ratio(self.ratio)
        self.update_info()
        self.canvas.update()

    def set_ratio(self, r):
        self.ratio = r
        if r and self.sel:
            W, H = self.full.size
            c = self.sel.center()
            w = min(self.sel.width(), self.sel.height() * r)
            w = max(w, min(W, H * r) * 0.3)
            h = w / r
            if w > W:
                w, h = W, W / r
            if h > H:
                h, w = H, H * r
            x = min(max(c.x() - w / 2, 0), W - w)
            y = min(max(c.y() - h / 2, 0), H - h)
            self.sel = QRectF(x, y, w, h)
        self.update_info()
        self.canvas.update()

    def update_info(self):
        if self.sel:
            self.size_label.setText(f"{round(self.sel.width())} × {round(self.sel.height())} px")

    def clamp(self, pt):
        W, H = self.full.size
        return QPointF(min(max(pt.x(), 0), W), min(max(pt.y(), 0), H))

    def from_anchor(self, a, pt):
        pt = self.clamp(pt)
        dx, dy = pt.x() - a.x(), pt.y() - a.y()
        if self.ratio:
            W, H = self.full.size
            sx, sy = (1 if dx >= 0 else -1), (1 if dy >= 0 else -1)
            w, h = abs(dx), abs(dy)
            if w / self.ratio > h:
                h = w / self.ratio
            else:
                w = h * self.ratio
            max_w = (W - a.x()) if sx > 0 else a.x()
            max_h = (H - a.y()) if sy > 0 else a.y()
            if w > max_w:
                w, h = max_w, max_w / self.ratio
            if h > max_h:
                h, w = max_h, max_h * self.ratio
            dx, dy = sx * w, sy * h
        return QRectF(a, QPointF(a.x() + dx, a.y() + dy)).normalized()

    def corners(self):
        s = self.sel
        return [s.topLeft(), s.topRight(), s.bottomRight(), s.bottomLeft()]

    def press(self, pt, vpos, e):
        for i, corner in enumerate(self.corners()):
            if (self.canvas.to_view(corner) - vpos).manhattanLength() < 16:
                self.drag = ("resize", self.corners()[(i + 2) % 4])
                return
        whole = self.sel.width() >= self.full.width - 1 and self.sel.height() >= self.full.height - 1
        if self.sel.contains(pt) and not whole:
            self.drag = ("move", pt - self.sel.topLeft())
        else:
            self.drag = ("new", self.clamp(pt))

    def move(self, pt, vpos, e):
        if not self.drag:
            near = any((self.canvas.to_view(c) - vpos).manhattanLength() < 16 for c in self.corners())
            shape = (Qt.CursorShape.SizeFDiagCursor if near else
                     Qt.CursorShape.SizeAllCursor if self.sel.contains(pt) else Qt.CursorShape.CrossCursor)
            self.canvas.setCursor(shape)
            return
        kind, ref = self.drag
        if kind == "move":
            W, H = self.full.size
            tl = pt - ref
            x = min(max(tl.x(), 0), W - self.sel.width())
            y = min(max(tl.y(), 0), H - self.sel.height())
            self.sel.moveTo(x, y)
        else:
            r = self.from_anchor(ref, pt)
            if r.width() > 2 and r.height() > 2:
                self.sel = r
        self.update_info()

    def release(self, pt, vpos, e):
        self.drag = None

    def key(self, e):
        step = 10 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        d = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0),
             Qt.Key.Key_Up: (0, -step), Qt.Key.Key_Down: (0, step)}.get(e.key())
        if not d:
            return False
        W, H = self.full.size
        x = min(max(self.sel.x() + d[0], 0), W - self.sel.width())
        y = min(max(self.sel.y() + d[1], 0), H - self.sel.height())
        self.sel.moveTo(x, y)
        return True

    def overlay(self, p, cv):
        r = cv.view_rect()
        s = cv.img_rect_to_view(self.sel)
        shade = QPainterPath()
        shade.addRect(r)
        hole = QPainterPath()
        hole.addRect(s)
        p.fillPath(shade.subtracted(hole), QColor(0, 0, 0, 130))
        p.setPen(QPen(QColor(255, 255, 255, 90), 1))
        for k in (1, 2):
            x = s.left() + s.width() * k / 3
            y = s.top() + s.height() * k / 3
            p.drawLine(QPointF(x, s.top()), QPointF(x, s.bottom()))
            p.drawLine(QPointF(s.left(), y), QPointF(s.right(), y))
        p.setPen(QPen(QColor("#FFFFFF"), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(s)
        p.setBrush(QColor("#FFFFFF"))
        p.setPen(QPen(QColor("#231B14"), 1))
        for c in (s.topLeft(), s.topRight(), s.bottomRight(), s.bottomLeft()):
            p.drawRect(QRectF(c.x() - 5, c.y() - 5, 10, 10))

    def save(self):
        s = self.sel
        if self.is_pdf:
            W, H = self.full.size
            fx0, fy0, fx1, fy1 = s.left() / W, s.top() / H, s.right() / W, s.bottom() / H
            out = out_path(self.src, "dipotong", ".pdf")
            with fitz.open(self.src) as doc:
                for page in doc:
                    pr = page.rect
                    r = fitz.Rect(pr.x0 + fx0 * pr.width, pr.y0 + fy0 * pr.height,
                                  pr.x0 + fx1 * pr.width, pr.y0 + fy1 * pr.height)
                    r = r * page.derotation_matrix
                    cb = page.cropbox
                    r = fitz.Rect(r.x0 + cb.x0, r.y0 + cb.y0, r.x1 + cb.x0, r.y1 + cb.y0) & page.mediabox
                    page.set_cropbox(r)
                doc.save(out, garbage=3, deflate=True)
            return [out]
        box = (round(s.left()), round(s.top()), round(s.right()), round(s.bottom()))
        im = self.full.crop(box)
        return [save_image(im, out_path(self.src, "dipotong", edit_ext(self.src, im)), quality=95)]


class RedactDialog(BaseDialog):
    title = "Sensor"
    verb = "Simpan hasil sensor"
    MODES = [("Blok hitam", "hitam"), ("Buram", "buram"), ("Piksel", "piksel")]

    def init_state(self):
        self.boxes = {}
        self.mode = "hitam"
        self.temp = None

    def build_controls(self):
        if self.is_pdf:
            note = QLabel("Teks di bawah blok hitam dihapus permanen dari PDF, bukan sekadar ditutup.")
            note.setWordWrap(True)
            self.side.addWidget(group_label("Cara sensor"))
            self.side.addWidget(note)
        else:
            self.side.addWidget(group_label("Cara sensor"))
            self.side.addWidget(toggle_row(self.MODES, self.mode, self.set_mode))
        self.count_label = QLabel()
        self.count_label.setProperty("muted", True)
        self.side.addWidget(self.count_label)
        row = QHBoxLayout()
        undo = QPushButton("Urungkan")
        undo.clicked.connect(self.undo)
        clear = QPushButton("Hapus semua")
        clear.clicked.connect(self.clear)
        row.addWidget(undo)
        row.addWidget(clear)
        self.side.addLayout(row)
        hint = QLabel("Seret kotak di atas bagian yang mau ditutup. Ctrl+Z untuk urungkan.")
        hint.setWordWrap(True)
        hint.setProperty("muted", True)
        self.side.addWidget(hint)
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.undo)

    def page_boxes(self):
        return self.boxes.setdefault(self.page, [])

    def set_mode(self, m):
        self.mode = m
        self.refresh()

    def undo(self):
        if self.page_boxes():
            self.page_boxes().pop()
            self.refresh()

    def clear(self):
        self.page_boxes().clear()
        self.refresh()

    def on_page(self):
        self.update_count()

    def update_count(self):
        total = sum(len(v) for v in self.boxes.values())
        here = len(self.boxes.get(self.page, []))
        text = f"{here} kotak di halaman ini" if self.is_pdf and self.pages > 1 else f"{here} kotak"
        if self.is_pdf and total != here:
            text += f", {total} di semua halaman"
        self.count_label.setText(text)

    def render_preview(self):
        if hasattr(self, "count_label"):
            self.update_count()
        k = self.k
        boxes = [(b.left() * k, b.top() * k, b.right() * k, b.bottom() * k) for b in self.boxes.get(self.page, [])]
        return apply_redact(self.preview, boxes, "hitam" if self.is_pdf else self.mode)

    def press(self, pt, vpos, e):
        self.temp = (pt, pt)

    def move(self, pt, vpos, e):
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)
        if self.temp:
            self.temp = (self.temp[0], pt)

    def release(self, pt, vpos, e):
        if not self.temp:
            return
        W, H = self.full.size
        r = QRectF(self.temp[0], pt).normalized().intersected(QRectF(0, 0, W, H))
        self.temp = None
        if self.canvas.img_rect_to_view(r).width() > 4 and self.canvas.img_rect_to_view(r).height() > 4:
            self.page_boxes().append(r)
            self.refresh()

    def overlay(self, p, cv):
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(T["accent"]), 1.5))
        for b in self.boxes.get(self.page, []):
            p.drawRect(cv.img_rect_to_view(b))
        if self.temp:
            pen = QPen(QColor(T["accent"]), 1.5, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(cv.img_rect_to_view(QRectF(self.temp[0], self.temp[1]).normalized()))

    def save(self):
        if not any(self.boxes.values()):
            raise ValueError("Belum ada kotak sensor. Seret kotak di atas bagian yang mau ditutup.")
        if self.is_pdf:
            out = out_path(self.src, "disensor", ".pdf")
            with fitz.open(self.src) as doc:
                for idx, boxes in self.boxes.items():
                    page = doc[idx]
                    zoom = 150 / 72
                    for b in boxes:
                        page.add_redact_annot(fitz.Rect(b.left() / zoom, b.top() / zoom,
                                                        b.right() / zoom, b.bottom() / zoom), fill=(0, 0, 0))
                    page.apply_redactions()
                doc.set_metadata({})
                doc.save(out, garbage=4, deflate=True, clean=True)
            return [out]
        boxes = [(b.left(), b.top(), b.right(), b.bottom()) for b in self.boxes.get(0, [])]
        im = apply_redact(self.full, boxes, self.mode)
        return [save_image(im, out_path(self.src, "disensor", edit_ext(self.src, im)), quality=95)]


def paint_shapes(p, shapes):
    for s in shapes:
        col = QColor(s["color"])
        w = s["width"]
        if s["tool"] == "stabilo":
            col.setAlpha(110)
            w *= 3.5
        pen = QPen(col, w)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap if s["tool"] == "stabilo" else Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        pts = s["pts"]
        if s["tool"] in ("pena", "stabilo"):
            if len(pts) == 1:
                p.drawPoint(pts[0])
            else:
                p.drawPolyline(pts)
        elif s["tool"] == "kotak" and len(pts) == 2:
            p.drawRect(QRectF(pts[0], pts[1]).normalized())
        elif s["tool"] == "panah" and len(pts) == 2:
            a, b = pts
            ang = math.atan2(b.y() - a.y(), b.x() - a.x())
            head = w * 4.5
            if math.hypot(b.x() - a.x(), b.y() - a.y()) < 2:
                continue
            base = QPointF(b.x() - math.cos(ang) * head * .8, b.y() - math.sin(ang) * head * .8)
            p.drawLine(a, base)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawPolygon(QPolygonF([
                b,
                QPointF(b.x() - head * math.cos(ang - .45), b.y() - head * math.sin(ang - .45)),
                QPointF(b.x() - head * math.cos(ang + .45), b.y() - head * math.sin(ang + .45)),
            ]))
        elif s["tool"] == "teks":
            f = QFont(FONT)
            f.setPixelSize(max(8, int(w * 7)))
            f.setWeight(QFont.Weight.DemiBold)
            p.setFont(f)
            p.setPen(col)
            p.drawText(pts[0], s["text"])


class AnnotateDialog(BaseDialog):
    title = "Tandai"
    verb = "Simpan tanda"
    TOOLS = [("Pena", "pena"), ("Stabilo", "stabilo"), ("Panah", "panah"), ("Kotak", "kotak"), ("Teks", "teks")]
    COLORS = [("Merah", "#D93025"), ("Kuning", "#F2C200"), ("Biru", "#1F6FEB"), ("Hitam", "#111111"), ("Putih", "#FFFFFF")]

    def init_state(self):
        self.shapes = []
        self.tool = "panah"
        self.color = "#D93025"
        self.thick = 4
        self.cur = None

    def build_controls(self):
        self.side.addWidget(group_label("Alat"))
        self.side.addWidget(toggle_row(self.TOOLS, self.tool, lambda v: setattr(self, "tool", v)))
        self.side.addWidget(group_label("Warna"))
        row = QHBoxLayout()
        row.setSpacing(6)
        grp = QButtonGroup(self)
        for name, hexc in self.COLORS:
            b = QPushButton()
            b.setObjectName("swatch")
            b.setCheckable(True)
            b.setFixedSize(32, 32)
            b.setToolTip(name)
            b.setAccessibleName(f"Warna {name}")
            b.setChecked(hexc == self.color)
            b.setStyleSheet(swatch_css(f"background:{hexc};"))
            b.clicked.connect(lambda _=False, c=hexc: setattr(self, "color", c))
            grp.addButton(b)
            row.addWidget(b)
        row.addStretch()
        self.side.addLayout(row)
        self.side.addWidget(slider_row("Tebal", 1, 12, self.thick, lambda v: setattr(self, "thick", v)))
        row2 = QHBoxLayout()
        undo = QPushButton("Urungkan")
        undo.clicked.connect(self.undo)
        clear = QPushButton("Hapus semua")
        clear.clicked.connect(self.clear)
        row2.addWidget(undo)
        row2.addWidget(clear)
        self.side.addLayout(row2)
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.undo)

    def unit(self):
        return max(self.full.size) / 600

    def on_page(self):
        self.shapes.clear()

    def undo(self):
        if self.shapes:
            self.shapes.pop()
            self.canvas.update()

    def clear(self):
        self.shapes.clear()
        self.canvas.update()

    def press(self, pt, vpos, e):
        width = self.thick * self.unit()
        if self.tool == "teks":
            text, ok = QInputDialog.getText(self, "Tambah teks", "Tulis teks:")
            if ok and text.strip():
                self.shapes.append(dict(tool="teks", color=self.color, width=width, pts=[pt], text=text.strip()))
            return
        self.cur = dict(tool=self.tool, color=self.color, width=width, pts=[pt] if self.tool in ("pena", "stabilo") else [pt, pt])
        self.shapes.append(self.cur)

    def move(self, pt, vpos, e):
        self.canvas.setCursor(Qt.CursorShape.IBeamCursor if self.tool == "teks" else Qt.CursorShape.CrossCursor)
        if not self.cur:
            return
        if self.cur["tool"] in ("pena", "stabilo"):
            self.cur["pts"].append(pt)
        else:
            self.cur["pts"][1] = pt

    def release(self, pt, vpos, e):
        self.cur = None

    def overlay(self, p, cv):
        r = cv.view_rect()
        W, H = self.full.size
        p.save()
        p.setClipRect(r)
        p.translate(r.topLeft())
        p.scale(r.width() / W, r.height() / H)
        paint_shapes(p, self.shapes)
        p.restore()

    def save(self):
        if not self.shapes:
            raise ValueError("Belum ada tanda yang dibuat.")
        qi = pil_to_qimage(self.full)
        p = QPainter(qi)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        paint_shapes(p, self.shapes)
        p.end()
        im = qimage_to_pil(qi)
        if self.full.mode == "RGB":
            im = im.convert("RGB")
        ext = ".png" if self.is_pdf else edit_ext(self.src, im)
        return [save_image(im, out_path(self.src, self.page_tag("ditandai"), ext), quality=95)]


class EditDialog(BaseDialog):
    title = "Edit"
    verb = "Simpan editan"

    def init_state(self):
        self.st = dict(EDIT_DEFAULT)
        self.debounce = QTimer(self, singleShot=True, interval=60, timeout=self.refresh)

    def build_controls(self):
        self.side.addWidget(group_label("Putar dan balik"))
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, (label, fn) in enumerate((
            ("Putar kiri", lambda: self.bump("rot", -1)), ("Putar kanan", lambda: self.bump("rot", 1)),
            ("Cermin datar", lambda: self.flip("flip_h")), ("Cermin tegak", lambda: self.flip("flip_v")),
        )):
            b = QPushButton(label)
            b.clicked.connect(fn)
            grid.addWidget(b, i // 2, i % 2)
        self.side.addLayout(grid)
        self.side.addWidget(group_label("Warna"))
        self.sliders = {}
        for key, label in (("terang", "Kecerahan"), ("kontras", "Kontras"), ("warna", "Saturasi"), ("tajam", "Ketajaman")):
            row = slider_row(label, -100, 100, 0, lambda v, k=key: self.set_val(k, v))
            self.sliders[key] = row
            self.side.addWidget(row)
        self.side.addWidget(group_label("Ukuran"))
        self.scale_row = toggle_row([("100%", 100), ("75%", 75), ("50%", 50), ("25%", 25)], 100,
                                    lambda v: self.set_val("skala", v))
        self.side.addWidget(self.scale_row)
        self.size_label = QLabel()
        self.size_label.setProperty("muted", True)
        self.side.addWidget(self.size_label)
        reset = QPushButton("Kembalikan semula")
        reset.clicked.connect(self.reset)
        self.side.addWidget(reset)

    def bump(self, key, d):
        self.st[key] = (self.st[key] + d) % 4
        self.refresh()

    def flip(self, key):
        self.st[key] = not self.st[key]
        self.refresh()

    def set_val(self, key, v):
        self.st[key] = v
        self.debounce.start()

    def reset(self):
        self.st = dict(EDIT_DEFAULT)
        for row in self.sliders.values():
            row.slider.blockSignals(True)
            row.slider.setValue(0)
            row.slider.blockSignals(False)
            row.val.setText("0")
        for b in self.scale_row.group.buttons():
            b.setChecked(b.text() == "100%")
        self.refresh()

    def display_size(self):
        w, h = self.full.size
        return (h, w) if self.st["rot"] % 2 else (w, h)

    def render_preview(self):
        w, h = self.display_size()
        k = self.st["skala"] / 100
        if hasattr(self, "size_label"):
            self.size_label.setText(f"Hasil: {round(w * k)} × {round(h * k)} px")
        return apply_edit(self.preview, self.st, resize=False)

    def save(self):
        im = apply_edit(self.full, self.st)
        ext = ".png" if self.is_pdf else edit_ext(self.src, im)
        return [save_image(im, out_path(self.src, self.page_tag("diedit"), ext), quality=95)]


class LatarDialog(BaseDialog):
    title = "Latar"
    verb = "Simpan dengan latar"
    RATIOS = [("Pas", None), ("1:1", 1.0), ("4:5", 4 / 5), ("16:9", 16 / 9), ("9:16", 9 / 16)]

    def init_state(self):
        self.o = dict(LATAR_DEFAULT)
        self.debounce = QTimer(self, singleShot=True, interval=50, timeout=self.refresh)

    def build_controls(self):
        self.side.addWidget(group_label("Latar"))
        grid = QGridLayout()
        grid.setSpacing(6)
        self.bg_group = QButtonGroup(self)
        swatches = [(n, ("grad", c)) for n, c in GRADIENTS] + [(n, ("solid", c)) for n, c in SOLIDS]
        swatches.append(("Transparan", ("none", None)))
        for i, (name, bg) in enumerate(swatches):
            b = QPushButton()
            b.setObjectName("swatch")
            b.setCheckable(True)
            b.setFixedSize(36, 36)
            b.setToolTip(name)
            b.setAccessibleName(f"Latar {name}")
            b.setChecked(bg == self.o["bg"])
            if bg[0] == "grad":
                css = (f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {bg[1][0]},"
                       f"stop:0.5 {bg[1][1]},stop:1 {bg[1][3]});")
            elif bg[0] == "solid":
                css = f"background:{bg[1]};"
            else:
                css = ("background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #FFFFFF,stop:0.49 #FFFFFF,"
                       "stop:0.51 #D9D4CD,stop:1 #D9D4CD);")
            b.setStyleSheet(swatch_css(css))
            b.clicked.connect(lambda _=False, v=bg: self.set_opt("bg", v, now=True))
            self.bg_group.addButton(b)
            grid.addWidget(b, i // 6, i % 6)
        self.side.addLayout(grid)
        pick = QPushButton("Pilih warna lain")
        pick.clicked.connect(self.pick_color)
        self.side.addWidget(pick)
        self.side.addWidget(slider_row("Jarak tepi", 0, 40, self.o["pad"], lambda v: self.set_opt("pad", v), "%"))
        self.side.addWidget(slider_row("Sudut membulat", 0, 20, self.o["radius"], lambda v: self.set_opt("radius", v), "%"))
        self.side.addWidget(slider_row("Bayangan", 0, 100, self.o["shadow"], lambda v: self.set_opt("shadow", v), "%"))
        self.side.addWidget(group_label("Rasio"))
        self.side.addWidget(toggle_row(self.RATIOS, None, lambda v: self.set_opt("ratio", v, now=True)))

    def pick_color(self):
        c = QColorDialog.getColor(QColor("#FFFFFF"), self, "Warna latar")
        if c.isValid():
            for b in self.bg_group.buttons():
                b.setChecked(False)
            self.set_opt("bg", ("solid", c.name()), now=True)

    def set_opt(self, key, v, now=False):
        self.o[key] = v
        self.refresh() if now else self.debounce.start()

    def render_preview(self):
        return compose_background(self.preview, self.o)

    def display_size(self):
        return None

    def refresh(self):
        im = self.render_preview()
        self.canvas.set_image(pil_to_qimage(im), im.size)

    def save(self):
        im = compose_background(self.full, self.o)
        return [save_image(im, out_path(self.src, self.page_tag("latar"), ".png"))]


# ---------------------------------------------------------------- gabung gambar jadi PDF

PAPERS = {"a4": (210, 297), "f4": (215, 330), "letter": (215.9, 279.4), "legal": (215.9, 355.6), "a5": (148, 210)}
PAPER_CHOICES = [("A4 (210 × 297 mm)", "a4"), ("F4 / Folio (215 × 330 mm)", "f4"),
                 ("Letter (216 × 279 mm)", "letter"), ("Legal (216 × 356 mm)", "legal"),
                 ("A5 (148 × 210 mm)", "a5"), ("Mengikuti ukuran gambar", "fit")]
QUALITY = {"tinggi": (3000, 92), "sedang": (2000, 82), "kecil": (1300, 60)}
GABUNG_DEFAULT = dict(paper="a4", orient="auto", per=1, margin=10, fit="contain", q="sedang")
MM = 72 / 25.4


def gabung_layout(sizes, s):
    """sizes: ukuran tiap gambar setelah diputar. Hasil: daftar halaman {W, H, cells} dalam mm."""
    m = s["margin"]
    fit_mode = s["paper"] == "fit"
    per = 1 if fit_mode else s["per"]
    pages = []
    for i in range(0, len(sizes), per):
        group = list(range(i, min(i + per, len(sizes))))
        cells = []
        if fit_mode:
            w0, h0 = sizes[group[0]]
            a = w0 / h0
            W = 297 if a >= 1 else 210
            cw = W - 2 * m
            ch = cw / a
            H = ch + 2 * m
            cells.append(dict(idx=group[0], x=m, y=m, w=cw, h=ch, crop=False))
        else:
            pw, ph = PAPERS[s["paper"]]
            n_land = sum(1 for k in group if sizes[k][0] > sizes[k][1])
            most_land = n_land * 2 > len(group)
            if s["orient"] == "p":
                land = False
            elif s["orient"] == "l":
                land = True
            else:
                land = (not most_land) if per == 2 else most_land
            W, H = (ph, pw) if land else (pw, ph)
            cols = 2 if per == 4 or (per == 2 and land) else 1
            rows = 2 if per == 4 or (per == 2 and not land) else 1
            gap = max(4, m / 2) if m > 0 else 0
            cW = (W - 2 * m - gap * (cols - 1)) / cols
            cH = (H - 2 * m - gap * (rows - 1)) / rows
            for j, k in enumerate(group):
                cx = m + (j % cols) * (cW + gap)
                cy = m + (j // cols) * (cH + gap)
                if s["fit"] == "cover":
                    cells.append(dict(idx=k, x=cx, y=cy, w=cW, h=cH, crop=True))
                else:
                    a = sizes[k][0] / sizes[k][1]
                    w = min(cW, cH * a)
                    h = w / a
                    cells.append(dict(idx=k, x=cx + (cW - w) / 2, y=cy + (cH - h) / 2, w=w, h=h, crop=False))
        pages.append(dict(W=W, H=H, cells=cells))
    return pages


def cover_crop(im, aspect):
    w, h = im.size
    if w / h > aspect:
        nw = int(round(h * aspect))
        return im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    nh = int(round(w / aspect))
    return im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))


def gabung_build(items, s, out, progress=lambda i, n: None):
    sizes = [it.size() for it in items]
    pages = gabung_layout(sizes, s)
    cap, quality = QUALITY[s["q"]]
    doc = fitz.open()
    done = 0
    for pg in pages:
        page = doc.new_page(width=pg["W"] * MM, height=pg["H"] * MM)
        for c in pg["cells"]:
            im = flatten(items[c["idx"]].full())
            if c["crop"]:
                im = cover_crop(im, c["w"] / c["h"])
            if max(im.size) > cap:
                im.thumbnail((cap, cap), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=quality, optimize=True)
            rect = fitz.Rect(c["x"] * MM, c["y"] * MM, (c["x"] + c["w"]) * MM, (c["y"] + c["h"]) * MM)
            page.insert_image(rect, stream=buf.getvalue(), keep_proportion=False)
            done += 1
            progress(done, len(items))
    doc.save(out, garbage=3, deflate=True)
    doc.close()
    return out


class GabungItem:
    _seq = 0

    def __init__(self, path=None, image=None, name=None):
        GabungItem._seq += 1
        self.id = GabungItem._seq
        self.path = path
        self._image = image
        self.name = name or Path(path).name
        src = image if image is not None else open_image(path)
        self.base_size = src.size
        self.thumb_src = fit_preview(src, 360)
        self.rot = 0

    def size(self):
        w, h = self.base_size
        return (h, w) if self.rot % 180 else (w, h)

    def rotated(self, im):
        return im.rotate(-self.rot, expand=True) if self.rot else im

    def full(self):
        return self.rotated(self._image if self._image is not None else open_image(self.path))

    def thumb(self):
        return self.rotated(self.thumb_src)


class GabungList(QListWidget):
    """Daftar gambar. Bisa diurutkan dengan seret, dan menerima file baru dari Explorer."""
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(120, 120))
        self.setGridSize(QSize(150, 172))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Snap)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setWordWrap(True)
        self.setSpacing(6)
        self.setAcceptDrops(True)

    def _external(self, e):
        return e.mimeData().hasUrls() and e.source() is not self

    def dragEnterEvent(self, e):
        if self._external(e):
            e.setDropAction(Qt.DropAction.CopyAction)
            e.accept()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if self._external(e):
            e.setDropAction(Qt.DropAction.CopyAction)
            e.accept()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if self._external(e):
            paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            e.setDropAction(Qt.DropAction.CopyAction)
            e.accept()
            self.files_dropped.emit(paths)
        else:
            super().dropEvent(e)


class GabungDialog(QDialog):
    def __init__(self, paths=()):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Gabung gambar jadi PDF")
        self.items = []
        self.outputs = []
        self.manual_name = False
        saved = load_config().get("gabung") or {}
        self.s = {k: saved.get(k, v) for k, v in GABUNG_DEFAULT.items()}
        if self.s["paper"] not in PAPERS and self.s["paper"] != "fit":
            self.s["paper"] = "a4"
        if self.s["q"] not in QUALITY:
            self.s["q"] = "sedang"
        self.default_folder = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)
        head = QHBoxLayout()
        title = QLabel("Gabung gambar jadi PDF")
        title.setObjectName("title")
        head.addWidget(title)
        head.addStretch()
        add = QPushButton("Tambah gambar")
        add.clicked.connect(self.pick_files)
        head.addWidget(add)
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(18)
        root.addLayout(body, 1)

        side_w = QWidget()
        side_w.setFixedWidth(270)
        side = QVBoxLayout(side_w)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(6)
        side.addWidget(group_label("Ukuran kertas"))
        self.paper = QComboBox()
        for label, val in PAPER_CHOICES:
            self.paper.addItem(label, val)
        self.paper.setCurrentIndex([v for _, v in PAPER_CHOICES].index(self.s["paper"]))
        self.paper.currentIndexChanged.connect(lambda _: self.set_opt("paper", self.paper.currentData()))
        side.addWidget(self.paper)
        side.addWidget(group_label("Arah kertas"))
        self.orient_row = toggle_row([("Otomatis", "auto"), ("Tegak", "p"), ("Mendatar", "l")],
                                     self.s["orient"], lambda v: self.set_opt("orient", v))
        side.addWidget(self.orient_row)
        side.addWidget(group_label("Gambar per halaman"))
        self.per_row = toggle_row([("1", 1), ("2", 2), ("4", 4)], self.s["per"], lambda v: self.set_opt("per", v))
        side.addWidget(self.per_row)
        side.addWidget(group_label("Tepi kertas"))
        side.addWidget(toggle_row([("Tanpa", 0), ("5 mm", 5), ("10 mm", 10), ("20 mm", 20)],
                                  self.s["margin"], lambda v: self.set_opt("margin", v)))
        side.addWidget(group_label("Posisi gambar"))
        self.fit_row = toggle_row([("Tampil utuh", "contain"), ("Penuhi halaman", "cover")],
                                  self.s["fit"], lambda v: self.set_opt("fit", v))
        side.addWidget(self.fit_row)
        side.addWidget(self.hint("Penuhi halaman memotong sedikit pinggir gambar."))
        side.addWidget(group_label("Kualitas gambar"))
        side.addWidget(toggle_row([("Tinggi", "tinggi"), ("Sedang", "sedang"), ("Kecil", "kecil")],
                                  self.s["q"], lambda v: self.set_opt("q", v)))
        side.addWidget(self.hint("Kualitas lebih rendah menghasilkan PDF lebih kecil."))
        side.addWidget(group_label("Nama file"))
        name_row = QHBoxLayout()
        self.fname = QLineEdit()
        self.fname.setAccessibleName("Nama file PDF")
        self.fname.textEdited.connect(self.on_name_edit)
        name_row.addWidget(self.fname, 1)
        name_row.addWidget(QLabel(".pdf"))
        side.addLayout(name_row)
        side.addWidget(self.hint("Otomatis dari nama gambar pertama sampai tanda _ . Bisa diketik ulang."))
        side.addStretch()
        body.addWidget(side_w)

        center = QVBoxLayout()
        center.setSpacing(8)
        tools = QHBoxLayout()
        tools.setSpacing(6)
        self.count = QLabel()
        self.count.setProperty("muted", True)
        tools.addWidget(self.count)
        tools.addStretch()
        self.tool_btns = []
        for label, fn in (("Urutkan nama A–Z", self.sort_az), ("Balik urutan", self.reverse),
                          ("Hapus semua", self.clear_all)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            tools.addWidget(b)
            self.tool_btns.append(b)
        center.addLayout(tools)

        self.stack = QStackedWidget()
        self.empty = QLabel("Belum ada gambar.\n\nSeret gambar ke sini, tempel dari papan klip (Ctrl+V),\n"
                            "atau klik Tambah gambar. Bisa JPG, PNG, WebP, GIF, BMP.")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setProperty("muted", True)
        self.empty.setAcceptDrops(False)
        empty_wrap = DropArea(self.add_paths)
        lay = QVBoxLayout(empty_wrap)
        lay.addWidget(self.empty)
        self.list = GabungList()
        self.list.files_dropped.connect(self.add_paths)
        self.list.model().rowsMoved.connect(lambda *a: QTimer.singleShot(0, self.sync_order))
        self.list.itemSelectionChanged.connect(self.update_sel)
        self.stack.addWidget(empty_wrap)
        self.stack.addWidget(self.list)
        center.addWidget(self.stack, 3)

        sel_row = QHBoxLayout()
        sel_row.setSpacing(6)
        self.sel_label = QLabel()
        self.sel_label.setProperty("muted", True)
        sel_row.addWidget(self.sel_label, 1)
        self.sel_btns = {}
        for key, label, fn in (("prev", "Geser ke depan", lambda: self.shift(-1)),
                               ("next", "Geser ke belakang", lambda: self.shift(1)),
                               ("rot", "Putar", self.rotate_sel), ("del", "Hapus", self.delete_sel)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            sel_row.addWidget(b)
            self.sel_btns[key] = b
        center.addLayout(sel_row)

        self.pages_title = group_label("Pratinjau halaman")
        center.addWidget(self.pages_title)
        self.pages_view = QListWidget()
        self.pages_view.setViewMode(QListWidget.ViewMode.IconMode)
        self.pages_view.setFlow(QListWidget.Flow.LeftToRight)
        self.pages_view.setWrapping(False)
        self.pages_view.setIconSize(QSize(110, 150))
        self.pages_view.setFixedHeight(200)
        self.pages_view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.pages_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pages_view.setMovement(QListWidget.Movement.Static)
        center.addWidget(self.pages_view)
        body.addLayout(center, 1)

        foot = QHBoxLayout()
        self.status = QLabel()
        self.status.setProperty("muted", True)
        foot.addWidget(self.status, 1)
        cancel = QPushButton("Tutup")
        cancel.clicked.connect(self.reject)
        self.save_btn = QPushButton("Simpan PDF")
        self.save_btn.setObjectName("primary")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.save)
        foot.addWidget(cancel)
        foot.addWidget(self.save_btn)
        root.addLayout(foot)

        QShortcut(QKeySequence.StandardKey.Paste, self, activated=self.paste)
        QShortcut(QKeySequence.StandardKey.Delete, self.list, activated=self.delete_sel)
        self.apply_paper_lock()
        self.add_paths(list(paths))
        self.resize(1180, 780)

    def hint(self, text):
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setProperty("muted", True)
        return lab

    def set_opt(self, key, v):
        self.s[key] = v
        cfg = load_config()
        cfg["gabung"] = dict(self.s)
        save_config(cfg)
        self.apply_paper_lock()
        self.render_pages()

    def apply_paper_lock(self):
        fit = self.s["paper"] == "fit"
        for row in (self.orient_row, self.per_row, self.fit_row):
            row.setEnabled(not fit)

    # ---- isi daftar

    def add_paths(self, paths):
        bad = []
        for p in paths:
            if kind_of(p) != "image":
                bad.append(Path(p).name)
                continue
            try:
                self.items.append(GabungItem(path=p))
                if self.default_folder is None:
                    self.default_folder = Path(p).parent
            except Exception:
                bad.append(Path(p).name)
        self.rebuild()
        if bad:
            self.say(f"Dilewati karena bukan gambar atau tidak terbaca: {', '.join(bad[:3])}"
                     + (f" dan {len(bad) - 3} lainnya" if len(bad) > 3 else ""), err=True)

    def pick_files(self):
        exts = " ".join(f"*{e}" for e in sorted(IMG_EXT))
        start = str(self.default_folder or Path.home())
        paths, _ = QFileDialog.getOpenFileNames(self, "Pilih gambar", start, f"Gambar ({exts})")
        if paths:
            self.add_paths(paths)

    def paste(self):
        cb = QGuiApplication.clipboard()
        md = cb.mimeData()
        if md.hasUrls():
            self.add_paths([u.toLocalFile() for u in md.urls() if u.isLocalFile()])
            return
        qi = cb.image()
        if qi.isNull():
            self.say("Papan klip tidak berisi gambar.", err=True)
            return
        n = sum(1 for it in self.items if it.path is None) + 1
        self.items.append(GabungItem(image=qimage_to_pil(qi).convert("RGB"), name=f"tempelan {n}.png"))
        self.rebuild()

    def rebuild(self, keep_ids=()):
        self.list.blockSignals(True)
        self.list.clear()
        for i, it in enumerate(self.items):
            li = QListWidgetItem(QIcon(QPixmap.fromImage(pil_to_qimage(it.thumb()))), f"{i + 1}. {it.name}")
            li.setData(Qt.ItemDataRole.UserRole, it.id)
            li.setToolTip(it.name)
            self.list.addItem(li)
            if it.id in keep_ids:
                li.setSelected(True)
        self.list.blockSignals(False)
        self.stack.setCurrentIndex(1 if self.items else 0)
        for b in self.tool_btns:
            b.setEnabled(bool(self.items))
        self.save_btn.setEnabled(bool(self.items))
        self.auto_name()
        self.update_sel()
        self.render_pages()

    def sync_order(self):
        by_id = {it.id: it for it in self.items}
        order = [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]
        self.items = [by_id[i] for i in order if i in by_id]
        self.rebuild(keep_ids=self.selected_ids())

    def selected_ids(self):
        return {li.data(Qt.ItemDataRole.UserRole) for li in self.list.selectedItems()}

    def update_sel(self):
        ids = self.selected_ids()
        n = len(ids)
        for b in self.sel_btns.values():
            b.setVisible(n > 0)
        if n == 0:
            self.sel_label.setText("Klik gambar untuk memilih, seret untuk mengubah urutan."
                                   if self.items else "Tambahkan gambar untuk mulai.")
        elif n == 1:
            i = next(k for k, it in enumerate(self.items) if it.id in ids)
            self.sel_label.setText(f"Gambar {i + 1} dari {len(self.items)}: {self.items[i].name}")
        else:
            self.sel_label.setText(f"{n} dari {len(self.items)} gambar dipilih")
        self.sel_btns["prev"].setEnabled(self.can_shift(-1, ids))
        self.sel_btns["next"].setEnabled(self.can_shift(1, ids))

    def can_shift(self, d, ids):
        for i, it in enumerate(self.items):
            j = i + d
            if it.id in ids and 0 <= j < len(self.items) and self.items[j].id not in ids:
                return True
        return False

    def shift(self, d):
        ids = self.selected_ids()
        n = len(self.items)
        rng = range(1, n) if d < 0 else range(n - 2, -1, -1)
        for i in rng:
            j = i + d
            if self.items[i].id in ids and self.items[j].id not in ids:
                self.items[i], self.items[j] = self.items[j], self.items[i]
        self.rebuild(keep_ids=ids)

    def rotate_sel(self):
        ids = self.selected_ids()
        for it in self.items:
            if it.id in ids:
                it.rot = (it.rot + 90) % 360
        self.rebuild(keep_ids=ids)

    def delete_sel(self):
        ids = self.selected_ids()
        if not ids:
            return
        if len(ids) > 1 and QMessageBox.question(self, "Hapus gambar", f"Hapus {len(ids)} gambar dari daftar?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.items = [it for it in self.items if it.id not in ids]
        self.rebuild()

    def sort_az(self):
        self.items.sort(key=lambda it: natural_key(it.name))
        self.rebuild(keep_ids=self.selected_ids())

    def reverse(self):
        self.items.reverse()
        self.rebuild(keep_ids=self.selected_ids())

    def clear_all(self):
        if QMessageBox.question(self, "Hapus semua", f"Kosongkan daftar ({len(self.items)} gambar)?") \
                == QMessageBox.StandardButton.Yes:
            self.items.clear()
            self.rebuild()

    # ---- nama dan pratinjau

    def default_name(self):
        from datetime import date
        return f"gabungan-{date.today():%Y-%m-%d}"

    def on_name_edit(self, text):
        self.manual_name = bool(text.strip())
        if not self.manual_name:
            self.auto_name()

    def auto_name(self):
        if self.manual_name:
            return
        v = ""
        if self.items:
            v = Path(self.items[0].name).stem.split("_")[0].strip()
        self.fname.setText(v or self.default_name())

    def render_pages(self):
        self.pages_view.clear()
        self.pages_title.setVisible(bool(self.items))
        self.pages_view.setVisible(bool(self.items))
        if not self.items:
            self.count.setText("")
            return
        pages = gabung_layout([it.size() for it in self.items], self.s)
        self.count.setText(f"{len(self.items)} gambar, {len(pages)} halaman")
        thumbs = {it.id: it.thumb() for it in self.items}
        for pi, pg in enumerate(pages):
            k = 150 / max(pg["W"], pg["H"])
            W, H = max(1, round(pg["W"] * k)), max(1, round(pg["H"] * k))
            sheet = Image.new("RGB", (W, H), "white")
            for c in pg["cells"]:
                im = thumbs[self.items[c["idx"]].id]
                if c["crop"]:
                    im = cover_crop(im, c["w"] / c["h"])
                cw, ch = max(1, round(c["w"] * k)), max(1, round(c["h"] * k))
                sheet.paste(flatten(im).resize((cw, ch), Image.LANCZOS), (round(c["x"] * k), round(c["y"] * k)))
            ImageDraw.Draw(sheet).rectangle((0, 0, W - 1, H - 1), outline="#BDB3A6")
            li = QListWidgetItem(QIcon(QPixmap.fromImage(pil_to_qimage(sheet))), f"Hal. {pi + 1}")
            self.pages_view.addItem(li)

    def say(self, text, err=False):
        self.status.setText(text)
        self.status.setStyleSheet(f"color:{T['accent']};" if err else "")

    # ---- simpan

    def save(self):
        if not self.items:
            return
        name = "".join(ch for ch in self.fname.text().strip() if ch not in '<>:"/\\|?*') or self.default_name()
        folder = self.default_folder or Path.home() / "Desktop"
        if not folder.exists():
            folder = Path.home()
        out = out_path(folder / f"{name}.pdf", "", ".pdf")
        self.save_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        def step(i, n):
            self.say(f"Menyusun gambar {i} dari {n}...")
            QApplication.processEvents()
        try:
            gabung_build(self.items, self.s, out, progress=step)
        except Exception as e:
            traceback.print_exc()
            self.say(f"Gagal menyimpan: {friendly(e)}", err=True)
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.save_btn.setEnabled(True)
        self.outputs = [out]
        self.say(f"Tersimpan: {out.name} ({human_size(out.stat().st_size)})")
        self.accept()


class DropArea(QWidget):
    """Tampilan kosong yang tetap menerima gambar dari Explorer."""

    def __init__(self, on_paths):
        super().__init__()
        self.on_paths = on_paths
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.setDropAction(Qt.DropAction.CopyAction)
            e.accept()

    def dragMoveEvent(self, e):
        self.dragEnterEvent(e)

    def dropEvent(self, e):
        e.setDropAction(Qt.DropAction.CopyAction)
        e.accept()
        self.on_paths([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(T["line"]), 1.5, Qt.PenStyle.DashLine))
        p.setBrush(QColor(T["surface"]))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 10, 10)


def natural_key(name):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


DIALOGS = {"potong": CropDialog, "sensor": RedactDialog, "tandai": AnnotateDialog,
           "edit": EditDialog, "latar": LatarDialog}


# ---------------------------------------------------------------- pemantau Shift + seret

class Watcher(QObject):
    """Memeriksa tombol mouse dan Shift tiap 20 ms. Kalau file sedang diseret dengan Shift, cincin muncul."""

    STARTERS = {"CabinetWClass", "ExploreWClass", "Progman", "WorkerW", "#32770"}

    def __init__(self, ring, cfg):
        super().__init__()
        import ctypes
        from ctypes import wintypes
        self.ring, self.cfg = ring, cfg
        self.u = ctypes.windll.user32
        self.u.WindowFromPoint.argtypes = [wintypes.POINT]
        self.u.WindowFromPoint.restype = wintypes.HWND
        self.u.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.u.GetAncestor.restype = wintypes.HWND
        self.u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.u.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        self.u.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.u.GetAsyncKeyState.restype = ctypes.c_short
        self.ctypes, self.wintypes = ctypes, wintypes
        self.down = self.ok = self.fired = False
        self.start = None
        self.timer = QTimer(self, interval=20, timeout=self.tick)
        self.timer.start()

    def pressed(self, vk):
        return bool(self.u.GetAsyncKeyState(vk) & 0x8000)

    def from_explorer(self):
        pt = self.wintypes.POINT()
        self.u.GetCursorPos(self.ctypes.byref(pt))
        hwnd = self.u.WindowFromPoint(pt)
        if not hwnd:
            return False
        root = self.u.GetAncestor(hwnd, 2) or hwnd
        buf = self.ctypes.create_unicode_buffer(256)
        self.u.GetClassNameW(root, buf, 256)
        return buf.value in self.STARTERS

    def tick(self):
        if not self.cfg["aktif"] or self.ring.pinned:
            self.down = False
            return
        down = self.pressed(0x01)
        if down and not self.down:
            self.down, self.fired = True, False
            self.start = QCursor.pos()
            mine = QApplication.topLevelAt(self.start) is not None
            self.ok = not mine and (not self.cfg["explorer_saja"] or self.from_explorer())
        elif down and self.down:
            if not self.fired and self.ok and self.pressed(0x10):
                if (QCursor.pos() - self.start).manhattanLength() > 14:
                    self.fired = True
                    self.ring.popup_near(QCursor.pos())
        elif not down and self.down:
            self.down = False
            if self.fired:
                # Jeda sedikit: dropEvent dari Explorer bisa tiba sesudah tombol dilepas.
                QTimer.singleShot(450, self.ring.hide_if_idle)


# ---------------------------------------------------------------- shortcut Windows

SHORTCUTS = [
    # (folder, nama, argumen, tombol pintas). Tombol pintas hanya di Start Menu: Windows menolak
    # pintasan sama yang terpasang di dua .lnk sekaligus.
    ("Desktop", "SeretAje", "", ""),
    ("Desktop", "Gabung Gambar jadi PDF", "--gabung", ""),
    ("Programs", "SeretAje", "", "CTRL+ALT+S"),
    ("Programs", "Gabung Gambar jadi PDF", "--gabung", "CTRL+ALT+G"),
]


def make_icon_file():
    """Tulis ikon sementara (huruf S di lingkaran) sebagai .ico untuk shortcut."""
    from PIL import ImageFont
    path = config_dir() / f"{APP}.ico"
    size = 256
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((8, 8, size - 8, size - 8), fill=LIGHT["accent"])
    font = None
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(name, 150)
            break
        except OSError:
            continue
    font = font or ImageFont.load_default()
    d.text((size / 2, size / 2 + 4), "S", fill="white", font=font, anchor="mm")
    im.save(path, "ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


def launch_target():
    if getattr(sys, "frozen", False):
        return Path(sys.executable), "", Path(sys.executable).parent
    pyw = Path(sys.executable).with_name("pythonw.exe")
    script = Path(__file__).resolve()
    return (pyw if pyw.exists() else Path(sys.executable)), f'"{script}"', script.parent


def make_shortcuts():
    """Buat shortcut di Desktop dan Start Menu lewat WScript.Shell. Hasil: daftar nama yang dibuat."""
    if not IS_WIN:
        raise OSError("Shortcut hanya bisa dibuat di Windows.")
    ico = make_icon_file()
    exe, base_args, workdir = launch_target()

    def q(v):
        return "'" + str(v).replace("'", "''") + "'"
    lines = ["$sh = New-Object -ComObject WScript.Shell"]
    for folder, name, arg, key in SHORTCUTS:
        args = " ".join(a for a in (base_args, arg) if a)
        lines += [
            f"$dir = [Environment]::GetFolderPath({q(folder)})",
            f"$s = $sh.CreateShortcut((Join-Path $dir {q(name + '.lnk')}))",
            f"$s.TargetPath = {q(exe)}",
            f"$s.Arguments = {q(args)}",
            f"$s.WorkingDirectory = {q(workdir)}",
            f"$s.IconLocation = {q(str(ico) + ',0')}",
            f"$s.Description = {q('Tahan Shift sambil menyeret file' if not arg else 'Gabung beberapa gambar jadi satu PDF')}",
        ] + ([f"$s.Hotkey = {q(key)}"] if key else []) + ["$s.Save()"]
    # Lewat file .ps1 (UTF-8 dengan BOM) supaya tanda kutip dan nama folder berhuruf khusus aman.
    ps1 = config_dir() / "buat-shortcut.ps1"
    ps1.write_text("\r\n".join(lines + ["exit 0"]), encoding="utf-8-sig")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
                       capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise OSError((r.stderr or r.stdout or "PowerShell menolak membuat shortcut.").strip()[:180])
    return [f"{n} ({'Desktop' if f == 'Desktop' else 'Start Menu'})" for f, n, _, _ in SHORTCUTS]


# ---------------------------------------------------------------- pengendali

def tray_icon_placeholder():
    """[LOGO] sementara: huruf S di lingkaran. Ganti dengan ikon resmi kalau sudah ada."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(LIGHT["accent"]))
    p.drawEllipse(2, 2, 60, 60)
    f = QFont(FONT)
    f.setPixelSize(36)
    f.setWeight(QFont.Weight.Bold)
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "S")
    p.end()
    return QIcon(pm)


class Controller(QObject):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.ring = Ring()
        self.ring.dropped.connect(self.handle)
        self.toast = Toast()
        self.workers = []
        self.anchor = QCursor.pos()
        self.watcher = Watcher(self.ring, self.cfg) if IS_WIN else None
        self.build_tray()

    def build_tray(self):
        self.tray = QSystemTrayIcon(tray_icon_placeholder(), self)
        self.tray.setToolTip(f"{APP}: tahan Shift sambil menyeret file")
        menu = QMenu()
        self.act_on = QAction("Aktif", menu, checkable=True, checked=self.cfg["aktif"])
        self.act_on.toggled.connect(lambda v: self.set_cfg("aktif", v))
        self.act_explorer = QAction("Hanya dari File Explorer dan Desktop", menu, checkable=True,
                                    checked=self.cfg["explorer_saja"])
        self.act_explorer.toggled.connect(lambda v: self.set_cfg("explorer_saja", v))
        show = QAction("Tampilkan cincin sekarang", menu)
        show.triggered.connect(lambda: self.ring.popup_near(QCursor.pos(), pinned=True))
        menu.addAction(self.act_on)
        menu.addAction(self.act_explorer)
        if IS_WIN:
            auto = QAction("Jalankan saat Windows menyala", menu, checkable=True, checked=get_autostart())
            auto.toggled.connect(self.toggle_autostart)
            menu.addAction(auto)
        menu.addSeparator()
        menu.addAction(show)
        gabung = QAction("Gabung gambar jadi PDF", menu)
        gabung.triggered.connect(lambda: self.open_gabung())
        menu.addAction(gabung)
        menu.addSeparator()
        if IS_WIN:
            sc = QAction("Buat shortcut di Desktop dan Start Menu", menu)
            sc.triggered.connect(self.create_shortcuts)
            menu.addAction(sc)
            menu.addSeparator()
        quit_act = QAction("Keluar", menu)
        quit_act.triggered.connect(QApplication.quit)
        menu.addAction(quit_act)
        self.menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray)
        self.tray.show()
        if self.cfg["sapaan_awal"]:
            self.tray.showMessage(APP, "Sudah jalan. Tahan Shift sambil menyeret file untuk memunculkan pilihan.",
                                  QSystemTrayIcon.MessageIcon.Information, 6000)
            self.set_cfg("sapaan_awal", False)

    def on_tray(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.ring.popup_near(QCursor.pos(), pinned=True)

    def set_cfg(self, key, v):
        self.cfg[key] = v
        save_config(self.cfg)

    def create_shortcuts(self):
        try:
            make_shortcuts()
        except Exception as e:
            traceback.print_exc()
            self.toast.error("Shortcut gagal dibuat", friendly(e), QCursor.pos())
            return
        self.toast.done([], "Shortcut dibuat", "Ada di Desktop dan Start Menu. Ctrl+Alt+S membuka cincin, "
                        "Ctrl+Alt+G membuka Gabung PDF.", QCursor.pos())

    def command(self, cmd):
        if cmd == "gabung":
            QTimer.singleShot(0, self.open_gabung)
        else:
            self.ring.popup_near(QCursor.pos(), pinned=True)

    def toggle_autostart(self, on):
        try:
            set_autostart(on)
        except OSError as e:
            self.toast.error("Gagal mengubah pengaturan", friendly(e), QCursor.pos())

    def handle(self, kind, key, paths):
        self.anchor = self.ring.geometry().center()
        if kind == "format" and key == "PDF" and all(kind_of(p) == "image" for p in paths):
            self.open_gabung(paths)
        elif kind == "format":
            self.run(f"Mengubah ke {key}", op_convert, paths, key)
        elif key == "kecilkan":
            self.run("Mengecilkan", op_compress, paths)
        elif key == "metadata":
            self.run("Menghapus metadata", op_strip, paths)
        else:
            self.open_dialogs(key, paths)

    def run(self, title, fn, *args):
        w = Worker(fn, *args)
        w.step.connect(lambda i, n: self.toast.progress(title, i, n, self.anchor))
        w.finished_ok.connect(lambda outs, msg: self.toast.done(outs, "Selesai" if outs else "Tidak ada perubahan", msg, self.anchor))
        w.failed.connect(lambda msg: self.toast.error("Gagal", msg, self.anchor))
        w.finished.connect(lambda: self.workers.remove(w))
        self.workers.append(w)
        w.start()

    def open_gabung(self, paths=()):
        try:
            dlg = GabungDialog(paths)
        except Exception as e:
            traceback.print_exc()
            self.toast.error("Tidak bisa membuka Gabung PDF", friendly(e), self.anchor)
            return
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.outputs:
            out = dlg.outputs[0]
            self.toast.done(dlg.outputs, "PDF tersimpan", f"{out.name}, {human_size(out.stat().st_size)}",
                            dlg.geometry().center())

    def open_dialogs(self, key, paths):
        saved = []
        for p in paths:
            try:
                dlg = DIALOGS[key](p)
            except Exception as e:
                traceback.print_exc()
                self.toast.error(f"Tidak bisa membuka {Path(p).name}", friendly(e), self.anchor)
                continue
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
            if dlg.exec() == QDialog.DialogCode.Accepted:
                saved += dlg.outputs
        if saved:
            detail = saved[0].name if len(saved) == 1 else f"{len(saved)} file tersimpan"
            self.toast.done(saved, "Tersimpan", detail, self.anchor)


def main():
    global T
    if "--buat-shortcut" in sys.argv:
        try:
            for name in make_shortcuts():
                print("Dibuat:", name)
            print("Tombol pintas: Ctrl+Alt+S membuka cincin, Ctrl+Alt+G membuka Gabung PDF.")
            return 0
        except Exception as e:
            print("Gagal membuat shortcut:", friendly(e))
            return 1

    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setQuitOnLastWindowClosed(False)
    T = DARK if system_dark() else LIGHT
    app.setStyleSheet(qss(T))

    cmd = "gabung" if "--gabung" in sys.argv else "cincin"
    server_name = f"{APP}-{os.environ.get('USERNAME') or os.environ.get('USER') or 'pengguna'}"
    lock = QLockFile(str(Path(tempfile.gettempdir()) / f"{APP}.lock"))
    if not lock.tryLock(100):
        # Sudah jalan: teruskan perintah ke jendela yang ada, jadi shortcut dan tombol pintas tetap bekerja.
        sock = QLocalSocket()
        sock.connectToServer(server_name)
        if sock.waitForConnected(800):
            sock.write(cmd.encode())
            sock.flush()
            sock.waitForBytesWritten(800)
            sock.disconnectFromServer()
        else:
            QMessageBox.information(None, APP, f"{APP} sudah berjalan. Cari ikonnya di area jam (system tray).")
        return 0
    if fitz is None:
        QMessageBox.warning(None, APP, "PyMuPDF belum terpasang, jadi fitur PDF dimatikan.\n"
                                       "Pasang dengan: pip install pymupdf")
    ctl = Controller()

    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    server.listen(server_name)

    def on_conn():
        conn = server.nextPendingConnection()
        if conn is None:
            return

        def read():
            data = bytes(conn.readAll()).decode(errors="ignore").strip()
            if data:
                ctl.command(data)
        conn.readyRead.connect(read)
        conn.disconnected.connect(conn.deleteLater)
        if conn.bytesAvailable():
            read()
    server.newConnection.connect(on_conn)

    if "--gabung" in sys.argv:
        ctl.command("gabung")
    elif "--cincin" in sys.argv:
        ctl.command("cincin")
    code = app.exec()
    server.close()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
