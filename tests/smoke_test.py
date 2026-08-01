"""核心逻辑冒烟测试（不依赖 GUI）

运行: python tests/smoke_test.py
验证: 色度抠图 alpha 计算、GIF/WEBP/APNG 编码、RGBA 保留、缩放。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import MattingParams, OutputConfig, FORMAT_GIF, FORMAT_WEBP, FORMAT_APNG
from app.matting import apply_matting, composite_over_checker, sample_color
from app.encoder import encode_frames, scale_frame
from app.pipeline import convert_video
from app.config import SCALE_WIDTH

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out")
os.makedirs(OUT, exist_ok=True)


def make_frames(n=16, size=(120, 160)):
    """白色背景 + 移动的红色方块（无 alpha 通道）。size=(h, w)"""
    h, w = size
    frames = []
    for i in range(n):
        frame = np.full((h, w, 3), 255, dtype=np.uint8)  # 白底
        x0 = 10 + i * 5
        y0 = 30
        x1 = min(x0 + 40, w - 1)
        y1 = y0 + 50
        frame[y0:y1, x0:x1] = (220, 30, 30)  # 红方块
        frames.append(frame)
    return frames


def check(name, cond):
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        raise SystemExit(f"冒烟测试失败: {name}")


def main():
    params = MattingParams(bg_color=(255, 255, 255), tolerance=30, feather=8)
    frames = make_frames()

    # 1) 抠图 alpha
    rgba = apply_matting(frames[0], params)
    check("apply_matting 输出 RGBA 形状", rgba.shape == (120, 160, 4))
    white_px = rgba[5, 5]
    red_px = rgba[35, 20]
    check("白色背景像素被抠为透明", white_px[3] < 8)
    check("红色主体保持不透明", red_px[3] > 200)
    check("红色主体颜色保留", abs(int(red_px[0]) - 220) < 30)
    check("sample_color 返回白色", sample_color(frames[0], 5, 5) == (255, 255, 255))
    ck = composite_over_checker(rgba)
    check("棋盘格预览形状", ck.shape == (120, 160, 3))

    # 2) 三种格式编码（RGBA）
    rgba_frames = [apply_matting(f, params) for f in frames]
    for fmt, ext in [(FORMAT_GIF, "gif"), (FORMAT_WEBP, "webp"), (FORMAT_APNG, "png")]:
        dst = os.path.join(OUT, f"test.{ext}")
        encode_frames(rgba_frames, dst, fmt, duration_ms=50, loop=0, keep_rgba=True)
        check(f"{fmt} 编码成功且非空", os.path.exists(dst) and os.path.getsize(dst) > 0)

    # 3) 不保留 RGBA -> 合成填充色
    dst = os.path.join(OUT, "test_filled.webp")
    encode_frames(rgba_frames, dst, FORMAT_WEBP, duration_ms=50, loop=0,
                  keep_rgba=False, fill_color=(0, 255, 0))
    check("WEBP 合成填充色成功", os.path.exists(dst) and os.path.getsize(dst) > 0)

    # 4) 缩放
    scaled = scale_frame(rgba_frames[0], SCALE_WIDTH, 64)
    check("缩放到指定宽度", scaled.shape == (48, 64, 4))

    # 5) pipeline 完整流程（合成一个假视频文件）
    from app.video import bgr_to_rgb  # noqa: F401
    import cv2

    vpath = os.path.join(OUT, "src.mp4")
    writer = cv2.VideoWriter(vpath, cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 120))
    for f in frames:
        writer.write(f[:, :, ::-1])  # RGB -> BGR
    writer.release()

    outcfg = OutputConfig(out_format=FORMAT_WEBP, keep_rgba=True)
    dst = os.path.join(OUT, "pipeline.webp")
    res = convert_video(vpath, dst, params, outcfg)
    check("pipeline 转换成功", res["ok"] and res["frames"] == 16, )
    check("pipeline 尺寸", res["width"] == 160 and res["height"] == 120)

    # 6) maxfps 抽帧 + 缩放（源 10fps -> maxfps 5 -> step=2 -> 8 帧）
    outcfg2 = OutputConfig(out_format=FORMAT_GIF, fps_mode="最大帧率", maxfps=5,
                           scale_mode=SCALE_WIDTH, scale_value=80)
    dst2 = os.path.join(OUT, "pipeline2.gif")
    res2 = convert_video(vpath, dst2, params, outcfg2)
    check("maxfps抽帧+缩放 pipeline",
          res2["ok"] and res2["frames"] == 8 and res2["width"] == 80)

    # 7) 读回验证：动画帧数与透明信息
    from PIL import Image

    g = Image.open(os.path.join(OUT, "test.gif"))
    check("GIF 为多帧动画", g.n_frames >= 2)
    check("GIF 带透明索引", g.info.get("transparency") is not None)

    a = Image.open(os.path.join(OUT, "test.png"))
    check("APNG 为多帧动画", a.n_frames >= 2)
    a.seek(1)
    check("APNG 模式含 alpha", a.mode in ("RGBA", "LA"))

    w = Image.open(os.path.join(OUT, "test.webp"))
    check("WEBP 为多帧动画", w.n_frames >= 2)
    w.seek(0)
    check("WEBP 模式含 alpha", w.mode in ("RGBA", "LA"))

    # 8) 剪辑范围
    dst3 = os.path.join(OUT, "pipeline_clip.gif")
    outcfg3 = OutputConfig(out_format=FORMAT_GIF)
    res3 = convert_video(vpath, dst3, params, outcfg3, clip_begin=2, clip_end=7)
    check("剪辑范围 pipeline", res3["ok"] and res3["frames"] == 6)

    # 9) maxfps 抽帧：源 10fps -> maxfps 5 -> step=2 -> 8 帧
    dst4 = os.path.join(OUT, "pipeline_maxfps.webp")
    outcfg4 = OutputConfig(out_format=FORMAT_WEBP, fps_mode="最大帧率", maxfps=5)
    res4 = convert_video(vpath, dst4, params, outcfg4)
    check("maxfps 抽帧", res4["ok"] and res4["frames"] == 8
          and abs(res4["fps"] - 5) < 1e-6)

    # 10) 去边 (border_erase)：顶部一行人为涂绿，应被清为透明
    frame_e = frames[0].copy()
    frame_e[0, :, :] = (0, 180, 60)  # 顶部一行涂绿（模拟顶部绿缝）
    p_erase = MattingParams(bg_color=(255, 255, 255), tolerance=30, feather=8,
                            border_erase=1)
    rgba_e = apply_matting(frame_e, p_erase)
    check("去边清除顶部绿线", rgba_e[0, 5, 3] < 8)
    p_noerase = MattingParams(bg_color=(255, 255, 255), tolerance=30, feather=8,
                              border_erase=0)
    rgba_ne = apply_matting(frame_e, p_noerase)
    check("不启用去边时绿线保留", rgba_ne[0, 5, 3] > 200)

    print("\n全部通过 ✓")


if __name__ == "__main__":
    main()
