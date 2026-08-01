"""诊断：检查根目录下的样本视频能否打开/读取，并尝试完整转换

运行: python tests/diag_video.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import MattingParams, OutputConfig
from app.pipeline import convert_video
from app.video import VideoReader


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    videos = [f for f in glob.glob(os.path.join(root, "*")) if f.lower().endswith((".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".ts"))]
    if not videos:
        print("根目录下没有找到视频文件")
        return
    for path in videos:
        print("=" * 60)
        print("文件:", os.path.basename(path))
        print("大小:", os.path.getsize(path) / 1024 / 1024, "MB")

        r = VideoReader(path)
        if not r.open():
            print("打开失败:", r.error)
            continue
        print(f"fps={r.fps}  frame_count={r.frame_count}  {r.width}x{r.height}")

        # 尝试逐帧读取若干帧，检查解码
        ok_count = 0
        fails = 0
        for idx, frame in r.iter_frames():
            if frame is None:
                fails += 1
            else:
                ok_count += 1
            if idx >= 10:
                break
        print(f"前 11 帧读取: 成功 {ok_count}, 失败 {fails}")
        r.close()

        # 尝试完整转换（白底抠图，GIF）
        out = os.path.join(root, "tests", "_out", "diag_result.gif")
        params = MattingParams(bg_color=(255, 255, 255), tolerance=30, feather=8)
        cfg = OutputConfig(out_format="GIF")
        res = convert_video(path, out, params, cfg)
        print("转换结果:", res)
        if res["ok"]:
            print("输出:", out, os.path.getsize(out) / 1024, "KB")


if __name__ == "__main__":
    main()
