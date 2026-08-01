"""单个视频的完整转换流程"""
import math
import os

from . import encoder
from .config import FPS_ORIGINAL, FPS_MAX
from .matting import apply_matting
from .video import VideoReader


def convert_video(src, dst, params, outcfg, clip_begin=0, clip_end=-1,
                  progress_cb=None, cancel_check=None):
    """转换单个视频 -> dict(ok, error, cancelled, frames, width, height, fps, size)

    clip_begin: 起始帧索引（含）
    clip_end:   结束帧索引（含），<0 表示到视频末尾
    progress_cb(current_index, total_frames)
    cancel_check() -> bool，返回 True 表示取消
    """
    reader = VideoReader(src)
    if not reader.open():
        return {"ok": False, "error": reader.error}

    fps = reader.fps or 0.0
    start = max(0, int(clip_begin))
    end_excl = None if clip_end is None or clip_end < 0 else int(clip_end) + 1

    # 输出帧率：最大帧率模式下按 maxfps 抽帧
    if fps > 0 and outcfg.fps_mode == FPS_MAX:
        maxfps = max(1, int(outcfg.maxfps))
        step = max(1, int(math.ceil(fps / maxfps)))
        out_fps = fps / step
    else:
        step = 1
        out_fps = fps
    duration_ms = max(1, int(round(1000.0 / out_fps))) if out_fps > 0 else 100

    frames = []
    try:
        count = reader.frame_count or 0
        end = count if end_excl is None else min(count, end_excl)
        total = max(0, end - start)
        for idx, frame_bgr in reader.iter_frames(step=step, start=start, end=end_excl):
            if cancel_check and cancel_check():
                return {"ok": False, "error": "已取消", "cancelled": True}
            frame_rgb = frame_bgr[:, :, ::-1]  # BGR -> RGB
            rgba = apply_matting(frame_rgb, params)
            rgba = encoder.scale_frame(rgba, outcfg.scale_mode, outcfg.scale_value)
            frames.append(rgba)
            if progress_cb:
                progress_cb(idx - start + 1, total if total > 0 else idx - start + 1)
    finally:
        reader.close()

    if not frames:
        return {"ok": False, "error": "视频中未读取到任何帧"}

    try:
        encoder.encode_frames(
            frames, dst, outcfg.out_format,
            duration_ms=duration_ms,
            loop=outcfg.loop,
            keep_rgba=outcfg.keep_rgba,
            fill_color=outcfg.fill_color,
        )
    except Exception as exc:
        return {"ok": False, "error": f"编码失败: {exc}"}

    size = os.path.getsize(dst) if os.path.exists(dst) else 0
    h, w = frames[0].shape[:2]
    return {"ok": True, "cancelled": False, "frames": len(frames),
            "width": w, "height": h, "fps": out_fps, "size": size}
