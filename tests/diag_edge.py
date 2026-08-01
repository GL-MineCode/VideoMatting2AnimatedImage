"""诊断：检查视频第一帧的顶部/边缘像素颜色 vs 背景绿，分析顶部绿缝成因

运行: python tests/diag_edge.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from app.video import VideoReader, bgr_to_rgb
from app.matting import compute_alpha, apply_matting
from app.config import MattingParams


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    v = glob.glob(os.path.join(root, "*.mp4"))[0]
    r = VideoReader(v)
    r.open()
    frame_bgr = r.read_frame(0)
    r.close()
    frame = bgr_to_rgb(frame_bgr)  # HxWx3 uint8
    h, w = frame.shape[:2]
    print(f"尺寸 {w}x{h}")

    # 在背景中部取几个样
    bg = frame[h // 2, w // 2]
    print("中部背景色:", bg.tolist())

    # 顶部第 0 行若干列的像素
    top = [frame[0, x].tolist() for x in range(0, w, max(1, w // 8))]
    print("第0行像素:", top)
    # 第1行、第2行
    for row in (1, 2):
        print(f"第{row}行:", [frame[row, x].tolist() for x in range(0, w, max(1, w // 8))])

    # 用中部背景色做抠图，看顶部各像素的 alpha
    params = MattingParams(bg_color=tuple(bg), tolerance=30, feather=8)
    alpha = compute_alpha(frame, params)
    print("\n容差30 羽化8 下，第0行 alpha:")
    print([round(float(alpha[0, x]), 3) for x in range(0, w, max(1, w // 8))])
    print("第1行 alpha:", [round(float(alpha[1, x]), 3) for x in range(0, w, max(1, w // 8))])

    # 提高容差看是否消除
    params2 = MattingParams(bg_color=tuple(bg), tolerance=60, feather=12)
    alpha2 = compute_alpha(frame, params2)
    print("\n容差60 羽化12 下，第0行 alpha:")
    print([round(float(alpha2[0, x]), 3) for x in range(0, w, max(1, w // 8))])

    # 全图 alpha 分布（有多少像素残留）
    for name, a in (("容差30", alpha), ("容差60", alpha2)):
        keep = np.mean(a > 0.05)
        print(f"{name}: alpha>0.05 占比 {keep*100:.1f}%")


if __name__ == "__main__":
    main()
