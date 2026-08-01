"""复现 UI 完整流程：加载视频 -> 预览 -> 开始转换 -> 等待结果

运行: python tests/diag_ui.py
"""
import glob
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication, QMessageBox

import app.main_window as mw

# 避免 QMessageBox 阻塞
QMessageBox.information = staticmethod(lambda *a, **k: print("[msgbox]", a[1] if len(a) > 1 else ""))
QMessageBox.warning = staticmethod(lambda *a, **k: print("[warn]", a[2] if len(a) > 2 else ""))


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    videos = glob.glob(os.path.join(root, "*.mp4"))
    if not videos:
        print("根目录没有 mp4")
        return
    v = os.path.abspath(videos[0])

    app = QApplication(sys.argv)
    w = mw.MainWindow()
    w.show()
    app.processEvents()

    # 模拟添加视频（会触发预览加载）
    w._append_row(v)
    app.processEvents()
    print("预览加载后 current_row:", w.current_row,
          "有帧:", w.preview.has_frame(),
          "帧数:", w.current_reader.frame_count if w.current_reader else None)

    # 输出到临时目录
    outdir = os.path.join(root, "tests", "_out", "ui")
    os.makedirs(outdir, exist_ok=True)
    w.ed_dir.setText(outdir)

    # 模拟点击开始转换
    w._on_start()
    print("worker 启动:", w.worker is not None)
    w.worker.wait(180000)
    app.processEvents()

    for r in range(w.table.rowCount()):
        it = w.table.item(r, mw.MainWindow.COL_STATUS)
        print("行", r, "状态:", it.text() if it else None)

    print("总进度:", w.progress.value(), "/", w.progress.maximum())


if __name__ == "__main__":
    main()
