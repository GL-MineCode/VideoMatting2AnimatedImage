"""视频读取封装（基于 OpenCV）"""
import cv2


def bgr_to_rgb(frame):
    """OpenCV BGR -> RGB（copy 以去除负步长，便于 PIL/QImage 使用）"""
    return frame[:, :, ::-1].copy()


class VideoReader:
    """封装 cv2.VideoCapture，统一提供帧遍历与随机读取"""

    def __init__(self, path):
        self.path = path
        self.cap = None
        self.fps = 0.0
        self.frame_count = 0
        self.width = 0
        self.height = 0
        self.error = None

    def open(self):
        self.cap = cv2.VideoCapture(self.path)
        if not self.cap.isOpened():
            self.error = f"无法打开视频文件: {self.path}"
            self.cap = None
            return False
        self.fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        return True

    def iter_frames(self, step=1, start=0, end=None):
        """逐帧读取，按 step 抽帧。产出 (frame_index, frame_bgr)。

        start: 起始帧索引（含）；end: 结束帧索引（不含），None=全部。
        """
        if self.cap is None:
            return
        step = max(1, int(step))
        start = max(0, int(start))
        idx = 0
        while True:
            ok, frame = self.cap.read()
            if not ok:
                break
            if idx < start:
                idx += 1
                continue
            if end is not None and idx >= end:
                break
            if (idx - start) % step == 0:
                yield idx, frame
            idx += 1

    def read_frame(self, frame_index):
        """读取指定帧，返回 BGR 帧或 None"""
        if self.cap is None:
            return None
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frame_index)))
        ok, frame = self.cap.read()
        if not ok:
            return None
        return frame

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def __del__(self):
        self.close()
