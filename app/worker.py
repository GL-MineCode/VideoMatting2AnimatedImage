"""批量转换工作线程"""
import traceback

from PyQt6.QtCore import QThread, pyqtSignal

from .pipeline import convert_video


class BatchWorker(QThread):
    video_started = pyqtSignal(int, str)         # (行号, 源文件)
    video_progress = pyqtSignal(int, int, int)   # (行号, 当前帧, 总帧)
    video_finished = pyqtSignal(int, bool, str)  # (行号, 是否成功, 信息)
    all_finished = pyqtSignal()

    def __init__(self, jobs, outcfg, parent=None):
        super().__init__(parent)
        self.jobs = jobs          # [(row, src, dst, params), ...]
        self.outcfg = outcfg
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            for row, src, dst, params, clip_begin, clip_end in self.jobs:
                if self._cancel:
                    break
                self.video_started.emit(row, src)
                try:
                    result = convert_video(
                        src, dst, params, self.outcfg,
                        clip_begin=clip_begin, clip_end=clip_end,
                        progress_cb=lambda cur, total: self.video_progress.emit(row, cur, total),
                        cancel_check=lambda: self._cancel,
                    )
                except Exception:
                    # 转换内部异常：带上完整堆栈上报，避免线程静默崩溃
                    result = {"ok": False, "error": "内部异常:\n" + traceback.format_exc()}
                if result.get("cancelled"):
                    break
                if result.get("ok"):
                    msg = (f"{result['frames']} 帧 {result['width']}x{result['height']} "
                           f"{result.get('size', 0) / 1024:.1f} KB")
                else:
                    msg = result.get("error") or "未知错误"
                self.video_finished.emit(row, bool(result.get("ok")), msg)
        finally:
            self.all_finished.emit()
