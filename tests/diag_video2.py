"""深度诊断：测试三种格式 + 按 UI 规则生成的长文件名输出到源目录

运行: python tests/diag_video2.py
"""
import glob
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import MattingParams, OutputConfig, FORMAT_GIF, FORMAT_WEBP, FORMAT_APNG, FORMAT_EXT
from app.pipeline import convert_video


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    videos = glob.glob(os.path.join(root, "*.mp4"))
    if not videos:
        print("根目录没有 mp4")
        return
    path = videos[0]
    stem = os.path.splitext(os.path.basename(path))[0]
    print("源文件名长度:", len(os.path.basename(path)))

    params = MattingParams(bg_color=(255, 255, 255), tolerance=30, feather=8)

    for fmt in (FORMAT_GIF, FORMAT_WEBP, FORMAT_APNG):
        dst = os.path.join(root, f"{stem}.{FORMAT_EXT[fmt]}")
        print("-" * 50)
        print(f"格式 {fmt} -> 输出: {os.path.basename(dst)}")
        print("  完整路径长度:", len(dst))
        try:
            cfg = OutputConfig(out_format=fmt, keep_rgba=True)
            res = convert_video(path, dst, params, cfg)
            print("  结果:", res)
            if res["ok"]:
                print("  文件大小:", os.path.getsize(dst) / 1024, "KB")
        except Exception:
            print("  抛出异常!")
            traceback.print_exc()


if __name__ == "__main__":
    main()
