"""
focusee_render/render.py
========================
Core rendering engine. Reads all FocuSee project files and
produces a fully composited MP4 with background, rounded corners,
drop shadow, cursor overlay, click ripples, and zoom effects.
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import json
import subprocess
import os
import re
import sys
import shutil
import time


# ─────────────────────────────────────────────────────────────────────────────
# JSON LOADER  (handles FocuSee's trailing-comma quirk)
# ─────────────────────────────────────────────────────────────────────────────

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    # Remove trailing commas before ] or }  e.g. [..., ] → [...]
    cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
    return json.loads(cleaned)


# ─────────────────────────────────────────────────────────────────────────────
# MATH / INTERPOLATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def ease_in_out(t: float) -> float:
    """Smooth cubic ease-in-out. t must be in [0, 1]."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def clamp(val, lo, hi):
    return max(lo, min(hi, val))


# ─────────────────────────────────────────────────────────────────────────────
# IMAGE UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def pil_to_cv(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def cv_to_pil(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))


def make_rounded_mask(w: int, h: int, r: int) -> Image.Image:
    """Return a grayscale mask with rounded corners."""
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return mask


def make_drop_shadow(
    content_w: int,
    content_h: int,
    corner_r: int,
    opacity: float,
    blur_px: int = 28,
    offset_y: int = 10,
) -> tuple[Image.Image, int]:
    """
    Build a drop shadow layer.
    Returns (shadow_image_RGBA, padding) where padding is the extra
    pixels added around the shadow image on each side.
    """
    pad = blur_px + abs(offset_y) + 4
    total_w = content_w + pad * 2
    total_h = content_h + pad * 2
    img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    shadow_alpha = int(160 * opacity)
    draw = ImageDraw.Draw(img)
    sx, sy = pad, pad + offset_y
    draw.rounded_rectangle(
        [sx, sy, sx + content_w, sy + content_h],
        radius=corner_r,
        fill=(0, 0, 0, shadow_alpha),
    )
    img = img.filter(ImageFilter.GaussianBlur(blur_px // 3))
    return img, pad


# ─────────────────────────────────────────────────────────────────────────────
# CURSOR INTERPOLATION
# ─────────────────────────────────────────────────────────────────────────────

def interpolate_cursor(
    moves: list, target_proc_ms: float
) -> tuple[int, int, str]:
    """
    Binary-search the mousemoves list and linearly interpolate x/y.
    Returns (x, y, cursorId).
    """
    if not moves:
        return 960, 540, "arrow"

    if target_proc_ms <= moves[0]["processTimeMs"]:
        m = moves[0]
        return m["x"], m["y"], m["cursorId"]
    if target_proc_ms >= moves[-1]["processTimeMs"]:
        m = moves[-1]
        return m["x"], m["y"], m["cursorId"]

    lo, hi = 0, len(moves) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if moves[mid]["processTimeMs"] <= target_proc_ms:
            lo = mid
        else:
            hi = mid

    a, b = moves[lo], moves[hi]
    if b["processTimeMs"] == a["processTimeMs"]:
        return a["x"], a["y"], a["cursorId"]

    t = (target_proc_ms - a["processTimeMs"]) / (
        b["processTimeMs"] - a["processTimeMs"]
    )
    x = int(lerp(a["x"], b["x"], t))
    y = int(lerp(a["y"], b["y"], t))
    return x, y, a["cursorId"]


# ─────────────────────────────────────────────────────────────────────────────
# ZOOM
# ─────────────────────────────────────────────────────────────────────────────

def get_zoom_factor(
    zoom_tracks: list,
    elapsed_ms: float,
    total_dur_ms: float,
    ease_ms: float,
) -> float:
    """
    Return the zoom scale factor for the current frame.
    elapsed_ms = milliseconds since the recording started (0 … total_dur_ms).
    """
    for track in zoom_tracks:
        begin_ms = track["begin"] * total_dur_ms
        end_ms = track["end"] * total_dur_ms
        scale = track.get("zoomScale", 2.0)

        if begin_ms <= elapsed_ms <= end_ms:
            span = end_ms - begin_ms
            safe_ease = min(ease_ms, span / 2)  # never overlap
            # Ease in
            if elapsed_ms < begin_ms + safe_ease:
                t = (elapsed_ms - begin_ms) / safe_ease
                return lerp(1.0, scale, ease_in_out(t))
            # Ease out
            if elapsed_ms > end_ms - safe_ease:
                t = (end_ms - elapsed_ms) / safe_ease
                return lerp(1.0, scale, ease_in_out(t))
            return scale

    return 1.0


# ─────────────────────────────────────────────────────────────────────────────
# CLICK RIPPLES
# ─────────────────────────────────────────────────────────────────────────────

def get_active_ripples(
    clicks: list, proc_ms: float, ripple_ms: float
) -> list[tuple[int, int, float]]:
    """Return [(x, y, progress 0→1)] for every click currently animating."""
    result = []
    for c in clicks:
        if c.get("type") != "mouseDown":
            continue
        elapsed = proc_ms - c["processTimeMs"]
        if 0 <= elapsed <= ripple_ms:
            result.append((c["x"], c["y"], elapsed / ripple_ms))
    return result


def draw_ripples(
    canvas: Image.Image,
    ripples: list,
    disp_x: int,
    disp_y: int,
    scale_x: float,
    scale_y: float,
    zoom: float,
    zoom_vx: int,
    zoom_vy: int,
    zoom_vw: int,
    zoom_vh: int,
    disp_w: int,
    disp_h: int,
) -> None:
    """Draw concentric expanding rings for each active click."""
    draw = ImageDraw.Draw(canvas)
    for (rcx, rcy, progress) in ripples:
        # Map raw recording coords → display coords
        if zoom > 1.0:
            # Only draw if click is within the zoomed viewport
            if not (zoom_vx <= rcx <= zoom_vx + zoom_vw and
                    zoom_vy <= rcy <= zoom_vy + zoom_vh):
                continue
            rx_d = disp_x + int((rcx - zoom_vx) / zoom_vw * disp_w)
            ry_d = disp_y + int((rcy - zoom_vy) / zoom_vh * disp_h)
        else:
            rx_d = disp_x + int(rcx * scale_x)
            ry_d = disp_y + int(rcy * scale_y)

        base_alpha = int(220 * (1 - progress))
        for ring in range(3):
            ring_progress = min(1.0, progress + ring * 0.15)
            radius = int(70 * ring_progress * zoom)
            alpha = max(0, int(base_alpha * (1 - ring * 0.35)))
            if radius < 2 or alpha < 5:
                continue
            bbox = [rx_d - radius, ry_d - radius, rx_d + radius, ry_d + radius]
            width = max(1, 4 - ring)
            draw.ellipse(bbox, outline=(255, 210, 60), width=width)


# ─────────────────────────────────────────────────────────────────────────────
# PROGRESS BAR
# ─────────────────────────────────────────────────────────────────────────────

def progress_bar(current: int, total: int, elapsed_sec: float, width: int = 40):
    pct = current / max(total, 1)
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    fps_render = current / max(elapsed_sec, 0.001)
    remaining = (total - current) / max(fps_render, 0.001)
    print(
        f"\r  [{bar}] {pct*100:5.1f}%  "
        f"frame {current}/{total}  "
        f"{fps_render:.1f} fps  "
        f"ETA {int(remaining)}s   ",
        end="",
        flush=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RENDER FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def render(project_dir: str, output_path: str | None = None) -> str:
    """
    Render a FocuSee project folder into a final MP4.

    Parameters
    ----------
    project_dir : str
        Path to the .focusee project folder.
    output_path : str | None
        Where to save the rendered video. Defaults to
        <project_dir>/rendered_output.mp4

    Returns
    -------
    str
        Absolute path to the rendered output file.
    """

    project_dir = os.path.abspath(project_dir)
    if output_path is None:
        output_path = os.path.join(project_dir, "rendered_output.mp4")

    # ── Resolve paths ────────────────────────────────────────────────────────
    def p(*parts):
        return os.path.join(project_dir, *parts)

    RECORDING_VIDEO = p("recording", "display-0.mp4")
    AUDIO_FILE      = p("recording", "systemaudio-0.m4a")
    MOVES_FILE      = p("recording", "mousemoves-0.json")
    CLICKS_FILE     = p("recording", "mouseclicks-0.json")
    CURSOR_DEF_FILE = p("recording", "cursor.json")
    META_FILE       = p("recording", "metadata.json")
    CONFIG_FILE     = p("configure.focuseeproj")
    CURSOR_DIR      = p("recording", "cursors")

    # Prefer background_C (cropped) over background
    if os.path.exists(p("resource", "background_C.png")):
        BACKGROUND_IMG = p("resource", "background_C.png")
    elif os.path.exists(p("resource", "background.png")):
        BACKGROUND_IMG = p("resource", "background.png")
    else:
        BACKGROUND_IMG = None

    # ── Validate required files ───────────────────────────────────────────────
    required = [RECORDING_VIDEO, MOVES_FILE, CLICKS_FILE,
                CURSOR_DEF_FILE, META_FILE, CONFIG_FILE]
    missing = [f for f in required if not os.path.exists(f)]
    if missing:
        for m in missing:
            print(f"  ✗ Missing: {m}")
        raise FileNotFoundError(
            "Some required project files are missing. "
            "Make sure you are running this from inside a .focusee folder."
        )

    # ── Check ffmpeg ──────────────────────────────────────────────────────────
    ffmpeg_cmd = "ffmpeg"
    local_ffmpeg = os.path.join(project_dir, "ffmpeg.exe")
    if os.path.exists(local_ffmpeg):
        ffmpeg_cmd = local_ffmpeg
    elif shutil.which("ffmpeg") is None:
        raise EnvironmentError(
            "ffmpeg not found. Install it (https://ffmpeg.org) or place "
            "ffmpeg.exe in the project folder."
        )

    # ── Load JSON data ────────────────────────────────────────────────────────
    print("  Loading project data…")
    meta    = load_json(META_FILE)
    moves   = load_json(MOVES_FILE)
    clicks  = load_json(CLICKS_FILE)
    cur_def = load_json(CURSOR_DEF_FILE)
    config  = load_json(CONFIG_FILE)

    # ── Extract config values ─────────────────────────────────────────────────
    bg_cfg      = config.get("background", {})
    PADDING     = bg_cfg.get("padding", 0.05)
    CORNER_PCT  = bg_cfg.get("round", 0.04)
    SHADOW_OPQ  = bg_cfg.get("shadowOpacity", 1.0)
    zoom_tracks = config.get("zoomTracks", [])

    cursor_cfg  = config.get("cursor", {})
    CURSOR_SIZE = cursor_cfg.get("size", 3.0)      # 1.0 = 32px

    OUTPUT_FPS   = 30
    OUTPUT_W     = 1920
    OUTPUT_H     = 1080
    ZOOM_EASE_MS = 400
    RIPPLE_MS    = 600

    # ── Session timing ────────────────────────────────────────────────────────
    # Find the legacyDisplay session for bounds / duration
    display_session = None
    for recorder in meta.get("recorders", []):
        if recorder.get("type") == "legacyDisplay":
            display_session = recorder["sessions"][0]
            break
    if display_session is None:
        raise ValueError("Cannot find legacyDisplay session in metadata.json")

    proc_start_ms = display_session["processTimeStartMs"]
    total_dur_ms  = display_session["durationMs"]
    rec_w         = int(display_session["bounds"]["width"])
    rec_h         = int(display_session["bounds"]["height"])

    print(f"  Recording: {rec_w}×{rec_h}  {total_dur_ms/1000:.1f}s  "
          f"{len(zoom_tracks)} zoom events  {len([c for c in clicks if c.get('type')=='mouseDown'])} clicks")

    # ── Layout geometry ───────────────────────────────────────────────────────
    disp_w    = int(OUTPUT_W * (1 - 2 * PADDING))
    disp_h    = int(disp_w * rec_h / rec_w)
    disp_x    = (OUTPUT_W - disp_w) // 2
    disp_y    = (OUTPUT_H - disp_h) // 2
    corner_r  = int(disp_h * CORNER_PCT)
    scale_x   = disp_w / rec_w
    scale_y   = disp_h / rec_h

    print(f"  Canvas: {OUTPUT_W}×{OUTPUT_H}  "
          f"Display rect: {disp_w}×{disp_h} at ({disp_x},{disp_y})")

    # ── Pre-build static layers ───────────────────────────────────────────────
    round_mask = make_rounded_mask(disp_w, disp_h, corner_r)

    shadow_img, shadow_pad = make_drop_shadow(disp_w, disp_h, corner_r, SHADOW_OPQ)
    shadow_x = disp_x - shadow_pad
    shadow_y = disp_y - shadow_pad

    # Background
    if BACKGROUND_IMG:
        bg = Image.open(BACKGROUND_IMG).convert("RGB").resize(
            (OUTPUT_W, OUTPUT_H), Image.LANCZOS
        )
    else:
        # Fallback: dark gradient
        bg = Image.new("RGB", (OUTPUT_W, OUTPUT_H), (30, 30, 50))

    # ── Load cursors ──────────────────────────────────────────────────────────
    hotspots    = {}
    cursor_imgs = {}
    cursor_size_px = int(32 * CURSOR_SIZE)

    for cd in cur_def:
        cid = cd["id"]
        hotspots[cid] = (int(cd["hotSpot"]["x"]), int(cd["hotSpot"]["y"]))
        img_path = os.path.join(CURSOR_DIR, f"{cid}.png")
        if os.path.exists(img_path):
            cimg = Image.open(img_path).convert("RGBA")
            cimg = cimg.resize((cursor_size_px, cursor_size_px), Image.LANCZOS)
            cursor_imgs[cid] = cimg

    # ── Open source video ─────────────────────────────────────────────────────
    cap = cv2.VideoCapture(RECORDING_VIDEO)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {RECORDING_VIDEO}")

    total_frames = int(total_dur_ms / 1000 * OUTPUT_FPS)

    # ── Output writer (temp file, no audio yet) ───────────────────────────────
    raw_output = output_path.replace(".mp4", "_RAW.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(raw_output, fourcc, OUTPUT_FPS, (OUTPUT_W, OUTPUT_H))
    if not writer.isOpened():
        raise IOError(f"Cannot create output video: {raw_output}")

    print(f"  Rendering {total_frames} frames…")
    t_start = time.time()

    frame_idx = 0
    while frame_idx < total_frames:
        ret, src_frame = cap.read()
        if not ret:
            # Pad remaining frames with last frame if video ends early
            if frame_idx == 0:
                break
            src_frame = last_frame.copy()
        else:
            last_frame = src_frame.copy()

        # Current timestamps
        elapsed_ms = (frame_idx / OUTPUT_FPS) * 1000
        proc_ms    = proc_start_ms + elapsed_ms

        # ── Cursor position ───────────────────────────────────────────────────
        cx, cy, cur_id = interpolate_cursor(moves, proc_ms)

        # ── Zoom factor ───────────────────────────────────────────────────────
        zoom = get_zoom_factor(zoom_tracks, elapsed_ms, total_dur_ms, ZOOM_EASE_MS)

        # ── Prepare recording frame ───────────────────────────────────────────
        src_pil = cv_to_pil(src_frame)
        # Ensure source is correct resolution
        if src_pil.size != (rec_w, rec_h):
            src_pil = src_pil.resize((rec_w, rec_h), Image.LANCZOS)

        zoom_vx = zoom_vy = zoom_vw = zoom_vh = 0  # for ripple remapping

        if zoom > 1.0:
            view_w = int(rec_w / zoom)
            view_h = int(rec_h / zoom)
            vx = int(clamp(cx - view_w // 2, 0, rec_w - view_w))
            vy = int(clamp(cy - view_h // 2, 0, rec_h - view_h))
            zoom_vx, zoom_vy, zoom_vw, zoom_vh = vx, vy, view_w, view_h
            src_pil = src_pil.crop((vx, vy, vx + view_w, vy + view_h))
            src_pil = src_pil.resize((disp_w, disp_h), Image.LANCZOS)
            # Remap cursor into zoomed display space
            disp_cx = int((cx - vx) / view_w * disp_w)
            disp_cy = int((cy - vy) / view_h * disp_h)
        else:
            src_pil = src_pil.resize((disp_w, disp_h), Image.LANCZOS)
            disp_cx = int(cx * scale_x)
            disp_cy = int(cy * scale_y)

        # ── Composite canvas ──────────────────────────────────────────────────
        canvas = bg.copy()

        # Drop shadow
        canvas.paste(
            shadow_img.convert("RGB"),
            (shadow_x, shadow_y),
            shadow_img.split()[3],
        )

        # Recording with rounded corners
        canvas.paste(src_pil, (disp_x, disp_y), round_mask)

        # ── Click ripples ─────────────────────────────────────────────────────
        ripples = get_active_ripples(clicks, proc_ms, RIPPLE_MS)
        if ripples:
            draw_ripples(
                canvas, ripples,
                disp_x, disp_y, scale_x, scale_y,
                zoom, zoom_vx, zoom_vy, zoom_vw, zoom_vh,
                disp_w, disp_h,
            )

        # ── Cursor ────────────────────────────────────────────────────────────
        if cur_id in cursor_imgs:
            cimg = cursor_imgs[cur_id]
            hs   = hotspots.get(cur_id, (0, 0))
            hs_s = (int(hs[0] * CURSOR_SIZE), int(hs[1] * CURSOR_SIZE))
            px   = disp_x + disp_cx - hs_s[0]
            py   = disp_y + disp_cy - hs_s[1]
            try:
                canvas.paste(cimg, (px, py), cimg)
            except Exception:
                pass

        # ── Write frame ───────────────────────────────────────────────────────
        writer.write(pil_to_cv(canvas))
        frame_idx += 1

        if frame_idx % 15 == 0 or frame_idx == total_frames:
            progress_bar(frame_idx, total_frames, time.time() - t_start)

    cap.release()
    writer.release()
    print(f"\n  ✓ Frames rendered in {time.time() - t_start:.1f}s")

    # ── Merge audio ───────────────────────────────────────────────────────────
    if os.path.exists(AUDIO_FILE):
        print("  Merging audio…")
        cmd = [
            ffmpeg_cmd, "-y",
            "-i", raw_output,
            "-i", AUDIO_FILE,
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("  ⚠ ffmpeg stderr:", result.stderr[-600:])
            print(f"  Audio merge failed. Raw video saved at: {raw_output}")
        else:
            os.remove(raw_output)
            print(f"  ✓ Audio merged")
    else:
        print("  ⚠ No audio file found, skipping merge")
        os.rename(raw_output, output_path)

    abs_out = os.path.abspath(output_path)
    size_mb = os.path.getsize(abs_out) / 1_048_576
    print(f"\n  ✅  Done!  →  {abs_out}  ({size_mb:.1f} MB)")
    return abs_out
