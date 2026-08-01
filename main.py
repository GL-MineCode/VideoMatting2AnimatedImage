"""GB/BB 视频转动态图 - 程序入口"""
import sys
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox

from app.main_window import MainWindow


def _excepthook(exc_type, exc_value, exc_tb):
    """捕获未处理的异常并弹窗显示，便于反馈错误"""
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(msg, file=sys.stderr)
    try:
        QMessageBox.critical(None, "程序异常", f"发生未处理的异常：\n\n{msg}")
    except Exception:
        pass


sys.excepthook = _excepthook


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("GB/BB 视频转动态图")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
