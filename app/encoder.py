"""输出编码：GIF / WEBP / APNG（基于 Pillow）"""
import numpy as np
from PIL import Image

from .config import (
    FORMAT_GIF,
    FORMAT_WEBP,
    FORMAT_APNG,
    SCALE_KEEP,
    SCALE_PERCENT,
    SCALE_WIDTH,
)
from .matting import composite_over_background


# ---------------------------------------------------------------- 缩放
def scale_frame(rgba, scale_mode, scale_value):
    """单帧缩放。输入/输出均为 HxWx4 uint8 RGBA（或 HxWx3 RGB）。"""
    if scale_mode == SCALE_KEEP:
        return rgba
    h, w = rgba.shape[:2]
    if scale_mode == SCALE_PERCENT:
        pct = max(1, int(scale_value))
        new_w = max(1, int(round(w * pct / 100.0)))
        new_h = max(1, int(round(h * pct / 100.0)))
    elif scale_mode == SCALE_WIDTH:
        new_w = max(1, int(scale_value))
        new_h = max(1, int(round(h * new_w / w)))
    else:
        return rgba
    img = Image.fromarray(rgba)
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    return np.asarray(img)


# ---------------------------------------------------------------- GIF
def _save_gif(frames, duration_ms, loop, out_path):
    """GIF：量化至 255 色调色板，第 256 项用作透明索引（1 位透明）。"""
    pil_frames = []
    for rgba in frames:
        alpha = rgba[..., 3]
        transparent_mask = alpha == 0
        rgb = Image.fromarray(rgba[..., :3], "RGB")
        q = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT,
                         dither=Image.Dither.FLOYDSTEINBERG)
        pal = q.getpalette()
        while len(pal) < 256 * 3:
            pal += [0, 0, 0]
        pal = pal[:256 * 3]
        arr = np.asarray(q).copy()
        arr[transparent_mask] = 255
        pimg = Image.fromarray(arr, "P")
        pimg.putpalette(pal)
        pimg.info["transparency"] = 255
        pil_frames.append(pimg)

    first = pil_frames[0]
    first.save(
        out_path, format="GIF", save_all=True,
        append_images=pil_frames[1:],
        duration=duration_ms, loop=loop,
        transparency=255, disposal=2,
    )


# ---------------------------------------------------------------- WEBP
def _save_webp(frames, duration_ms, loop, out_path, lossless=True, quality=100):
    mode = "RGBA" if frames[0].ndim == 3 and frames[0].shape[2] == 4 else "RGB"
    imgs = [Image.fromarray(f, mode) for f in frames]
    imgs[0].save(
        out_path, format="WEBP", save_all=True,
        append_images=imgs[1:], duration=duration_ms, loop=loop,
        lossless=lossless, quality=quality,
    )


# ---------------------------------------------------------------- APNG
def _save_apng(frames, duration_ms, loop, out_path):
    mode = "RGBA" if frames[0].ndim == 3 and frames[0].shape[2] == 4 else "RGB"
    imgs = [Image.fromarray(f, mode) for f in frames]
    imgs[0].save(
        out_path, format="PNG", save_all=True,
        append_images=imgs[1:], duration=duration_ms, loop=loop,
        default_image=True, disposal=2, blend=1,
    )


# ---------------------------------------------------------------- 入口
def encode_frames(frames, out_path, out_format, duration_ms, loop,
                  keep_rgba=True, fill_color=(255, 255, 255),
                  lossless=True, quality=100):
    """frames: list[HxWx4 uint8 RGBA]。按格式编码写盘。"""
    if not frames:
        raise ValueError("没有可编码的帧")

    # 不保留透明时先合成到填充色（GIF 始终走 1 位透明，不合成）
    if (not keep_rgba) and frames[0].shape[2] == 4 and out_format != FORMAT_GIF:
        fill = np.asarray(fill_color, dtype=np.uint8).reshape(1, 1, 3)
        frames = [composite_over_background(f, fill) for f in frames]

    if out_format == FORMAT_GIF:
        _save_gif(frames, duration_ms, loop, out_path)
    elif out_format == FORMAT_WEBP:
        _save_webp(frames, duration_ms, loop, out_path, lossless, quality)
    elif out_format == FORMAT_APNG:
        _save_apng(frames, duration_ms, loop, out_path)
    else:
        raise ValueError(f"不支持的输出格式: {out_format}")
