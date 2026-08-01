"""色度抠图核心算法（纯 numpy 实现，无 UI 依赖）

输入输出统一使用 RGB 颜色空间、HxWx3 或 HxWx4 的 uint8 numpy 数组。
"""
import numpy as np

from .config import MattingParams


def compute_distance(frame_rgb, bg_color):
    """计算每个像素到背景色的欧氏距离，返回 HxW float32"""
    bg = np.asarray(bg_color, dtype=np.float32).reshape(1, 1, 3)
    diff = frame_rgb.astype(np.float32) - bg
    return np.sqrt(np.sum(diff * diff, axis=2))


def compute_alpha(frame_rgb, params):
    """根据抠图参数计算 alpha 通道（float 0..1），形状 HxW

    距离 < tolerance          -> 0  (完全透明)
    距离 > tolerance + feather -> 1  (完全不透明)
    中间 -> smoothstep 平滑过渡
    """
    dist = compute_distance(frame_rgb, params.bg_color)
    inner = float(params.tolerance)
    outer = inner + max(0.0, float(params.feather))
    if outer <= inner:
        outer = inner + 1e-6
    t = np.clip((dist - inner) / (outer - inner), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)  # smoothstep


def apply_matting(frame_rgb, params):
    """输入 HxWx3 uint8 RGB，输出 HxWx4 uint8 RGBA"""
    alpha = compute_alpha(frame_rgb, params)
    alpha = _apply_border_erase(alpha, params.border_erase)
    alpha_u8 = (alpha * 255.0 + 0.5).astype(np.uint8)
    return np.dstack([frame_rgb, alpha_u8])


def _apply_border_erase(alpha, n):
    """将画面最外 n 像素环的 alpha 按距边缘距离渐变压到 0（去除边缘残留，如顶部绿缝）"""
    if n <= 0:
        return alpha
    h, w = alpha.shape
    yy = np.minimum(np.arange(h), h - 1 - np.arange(h))
    xx = np.minimum(np.arange(w), w - 1 - np.arange(w))
    dist = np.minimum(yy[:, None], xx[None, :]).astype(np.float32)
    ramp = np.clip(dist / float(n), 0.0, 1.0)
    return alpha * ramp


def sample_color(frame_rgb, x, y):
    """取样 (x, y) 处的颜色，返回 RGB tuple"""
    h, w = frame_rgb.shape[:2]
    x = max(0, min(w - 1, int(x)))
    y = max(0, min(h - 1, int(y)))
    r, g, b = frame_rgb[y, x]
    return (int(r), int(g), int(b))


def make_checkerboard(height, width, cell=12):
    """生成棋盘格背景（HxWx3 uint8 RGB），用于显示透明区域"""
    yy = (np.arange(height) // cell) % 2
    xx = (np.arange(width) // cell) % 2
    grid = (yy[:, None] + xx[None, :]) % 2
    light = np.array([255, 255, 255], dtype=np.uint8)
    dark = np.array([160, 160, 160], dtype=np.uint8)
    return np.where(grid[..., None] == 1, light, dark).astype(np.uint8)


def composite_over_background(rgba, background_rgb):
    """把 RGBA 合成到背景上，返回 HxWx3 uint8 RGB。

    background_rgb 可为单个 RGB 颜色（3 元组/数组），也可为 HxWx3 的背景图。
    """
    bg = np.asarray(background_rgb, dtype=np.float32)
    if bg.ndim == 1:
        bg = bg.reshape(1, 1, 3)
    alpha = rgba[..., 3:4].astype(np.float32) / 255.0
    fg = rgba[..., :3].astype(np.float32)
    out = fg * alpha + bg * (1.0 - alpha)
    return out.astype(np.uint8)


def composite_over_checker(rgba, cell=12):
    """把 RGBA 合成到棋盘格背景用于预览，返回 HxWx3 uint8 RGB"""
    h, w = rgba.shape[:2]
    checker = make_checkerboard(h, w, cell)
    return composite_over_background(rgba, checker)
