"""
PyQt6 效果演示 - 抢答软件 UI 预览
"""
import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QListWidget, QListWidgetItem,
    QTextEdit, QStatusBar, QGridLayout, QSizePolicy, QScrollArea
)
from PyQt6.QtCore import Qt, QSize, QTimer, QPropertyAnimation, pyqtProperty
from PyQt6.QtGui import QFont, QColor, QPalette, QPainter, QLinearGradient, QBrush, QPen, QIcon


# ============================================================
# 现代化圆角按钮
# ============================================================
class ModernButton(QPushButton):
    def __init__(self, text, color="#0078d4", hover_color="#1a8ae8", parent=None):
        super().__init__(text, parent)
        self._color = color
        self._hover_color = hover_color
        self.setFixedHeight(36)
        self.setMinimumWidth(80)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {self._darken(color)};
            }}
            QPushButton:disabled {{
                background-color: #555555;
                color: #888888;
            }}
        """)

    def _darken(self, color):
        c = QColor(color)
        c.setAlpha(c.alpha())
        return c.darker(130).name()


class PlayerCard(QFrame):
    """选手卡片"""
    def __init__(self, name, score, rank="", rank_color="#FFD700", parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setStyleSheet("""
            PlayerCard {
                background-color: #2d2d2d;
                border-radius: 8px;
                border: 1px solid #3a3a3a;
            }
            PlayerCard:hover {
                border: 1px solid #0078d4;
                background-color: #333333;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        # 排名
        if rank:
            rank_label = QLabel(rank)
            rank_label.setStyleSheet(f"color: {rank_color}; font-size: 13px; font-weight: bold;")
            rank_label.setFixedWidth(30)
            layout.addWidget(rank_label)

        # 名字
        name_label = QLabel(name)
        name_label.setStyleSheet("color: white; font-size: 13px; font-weight: bold;")
        layout.addWidget(name_label)

        layout.addStretch()

        # 分数
        score_label = QLabel(score)
        score_label.setStyleSheet("color: #4CAF50; font-size: 14px; font-weight: bold;")
        layout.addWidget(score_label)


class RankBadge(QLabel):
    """排名徽章"""
    def __init__(self, text, color="#FFD700", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(28, 28)
        self.setStyleSheet(f"""
            background-color: {color};
            color: #1a1a2e;
            border-radius: 14px;
            font-size: 12px;
            font-weight: bold;
        """)


# ============================================================
# 主窗口
# ============================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎯 抢答系统 · PyQt6 版")
        self.setMinimumSize(1200, 800)
        self.resize(1200, 800)

        # 全局样式
        self.setStyleSheet("""
            QMainWindow { background-color: #1a1a2e; }
            QLabel { color: #ffffff; }
            QListWidget {
                background-color: #252525;
                border: none;
                border-radius: 8px;
                padding: 5px;
                color: white;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
            }
            QListWidget::item:hover {
                background-color: #333333;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
            }
            QScrollBar:vertical {
                background-color: #1e1e1e;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #444444;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #0078d4;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # 中央组件
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 顶部标题栏
        self._create_title_bar(main_layout)

        # 主体区域
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        main_layout.addWidget(body, 1)

        # 左侧面板
        self._create_left_panel(body_layout)

        # 右侧内容区
        self._create_right_panel(body_layout)

        # 底部状态栏
        self._create_status_bar()

    def _create_title_bar(self, parent):
        bar = QFrame()
        bar.setFixedHeight(56)
        bar.setStyleSheet("background-color: #16213e; border-bottom: 1px solid #0f3460;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel("🎯 抢答系统 · 主控端")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #0078d4;")
        layout.addWidget(title)

        layout.addStretch()

        # 比赛状态
        status = QLabel("🟢 运行中")
        status.setStyleSheet("color: #4CAF50; font-size: 13px; padding: 4px 12px; "
                           "background-color: #1a3a1a; border-radius: 10px;")
        layout.addWidget(status)

        game_name = QLabel("知识竞赛 2026")
        game_name.setStyleSheet("color: #aaaaaa; font-size: 13px; padding-left: 15px;")
        layout.addWidget(game_name)

        parent.addWidget(bar)

    def _create_left_panel(self, parent):
        panel = QWidget()
        panel.setFixedWidth(260)
        panel.setStyleSheet("background-color: #1e1e2e; border-right: 1px solid #0f3460;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 15, 12, 15)
        layout.setSpacing(8)

        # 标题
        title = QLabel("👥 选手管理")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #0078d4; padding-bottom: 5px;")
        layout.addWidget(title)

        # 选手列表（使用卡片方式）
        players_data = [
            ("IT", "120分", "🥇", "#FFD700"),
            ("张三", "85分", "🥈", "#C0C0C0"),
            ("李四", "60分", "🥉", "#CD7F32"),
            ("王五", "35分", "", None),
            ("赵六", "20分", "", None),
        ]

        for name, score, rank_icon, rank_c in players_data:
            card = PlayerCard(name, score, rank_icon, rank_c or "#666666")
            layout.addWidget(card)

        layout.addStretch()

        # 操作按钮
        layout.addSpacing(10)

        settings_btn = ModernButton("⚙ 设置", "#555555", "#666666")
        layout.addWidget(settings_btn)

        restart_btn = ModernButton("🔄 重赛", "#FF9800", "#FFB74D")
        layout.addWidget(restart_btn)

        end_btn = ModernButton("🏁 结束比赛", "#f44336", "#ef5350")
        layout.addWidget(end_btn)

        parent.addWidget(panel)

    def _create_right_panel(self, parent):
        panel = QWidget()
        panel.setStyleSheet("background-color: #1a1a2e;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(10)

        # ---- 信息栏 ----
        info_bar = QFrame()
        info_bar.setFixedHeight(65)
        info_bar.setStyleSheet("background-color: #16213e; border-radius: 10px;")
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(15, 0, 15, 0)

        info_items = [
            ("📚 题库", "知识问答 (25题)"),
            ("🎯 轮次", "第 3 轮"),
            ("✅ 进度", "8/25"),
            ("⏱ 倒计时", "15s"),
        ]
        for label, value in info_items:
            item = QWidget()
            il = QVBoxLayout(item)
            il.setAlignment(Qt.AlignmentFlag.AlignCenter)
            il.setSpacing(2)
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #888888; font-size: 11px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            il.addWidget(lbl)
            val = QLabel(value)
            val.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            il.addWidget(val)
            info_layout.addWidget(item)

        layout.addWidget(info_bar)

        # ---- 横幅（抢答状态）----
        banner = QFrame()
        banner.setFixedHeight(50)
        banner.setStyleSheet("""
            background-color: #4CAF50;
            border-radius: 10px;
        """)
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(15, 0, 15, 0)
        banner_text = QLabel("🎉🎉🎉 [IT] 抢答成功！等待 [IT] 输入答案 ⏱ 15s 🎉🎉🎉")
        banner_text.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
        banner_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner_layout.addWidget(banner_text)
        layout.addWidget(banner)

        # ---- 题目区域 ----
        question_box = QFrame()
        question_box.setStyleSheet("""
            background-color: #1e1e2e;
            border-radius: 10px;
            border: 1px solid #2a2a3e;
        """)
        q_layout = QVBoxLayout(question_box)
        q_layout.setContentsMargins(20, 15, 20, 15)
        q_layout.setSpacing(10)

        # 题型
        type_label = QLabel("📝 选择题")
        type_label.setStyleSheet("color: #0078d4; font-size: 13px; font-weight: bold;")
        q_layout.addWidget(type_label)

        # 题目内容
        q_text = QTextEdit()
        q_text.setPlainText("Python 中哪个关键字用于定义函数？\n\nA. define    B. def    C. function    D. func")
        q_text.setMinimumHeight(120)
        q_text.setReadOnly(True)
        q_layout.addWidget(q_text)

        # 参考答案折叠区
        answer_bar = QFrame()
        answer_bar.setStyleSheet("background-color: #252538; border-radius: 6px;")
        a_layout = QHBoxLayout(answer_bar)
        a_layout.setContentsMargins(12, 8, 12, 8)
        ans_label = QLabel("参考答案: def  ✅")
        ans_label.setStyleSheet("color: #4CAF50; font-size: 13px; font-weight: bold;")
        a_layout.addWidget(ans_label)
        q_layout.addWidget(answer_bar)

        # ---- 操作按钮行 ----
        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent;")
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 5, 0, 5)
        btn_layout.setSpacing(8)

        btn_layout.addWidget(ModernButton("◀ 上一题", "#555555", "#666666"))
        btn_layout.addWidget(ModernButton("▶ 下一题", "#555555", "#666666"))

        btn_layout.addSpacing(30)

        btn_layout.addWidget(ModernButton("🚀 开始抢答", "#4CAF50", "#66BB6A"))

        # 倒计时显示
        timer_label = QLabel("⏱ 15s")
        timer_label.setStyleSheet("color: #FF9800; font-size: 16px; font-weight: bold; padding: 0 10px;")
        btn_layout.addWidget(timer_label)

        btn_layout.addWidget(ModernButton("■ 结束抢答", "#f44336", "#ef5350"))

        btn_layout.addStretch()

        btn_layout.addWidget(ModernButton("👁 显示答案", "#2196F3", "#42A5F5"))
        btn_layout.addWidget(ModernButton("📋 日志", "#555555", "#666666"))

        q_layout.addWidget(btn_row)

        layout.addWidget(question_box, 1)

        # ---- 底部抢答记录 ----
        record_bar = QFrame()
        record_bar.setFixedHeight(36)
        record_bar.setStyleSheet("""
            background-color: #252538;
            border-radius: 6px;
        """)
        r_layout = QHBoxLayout(record_bar)
        r_layout.setContentsMargins(15, 0, 15, 0)
        record_btn = QLabel("📋 抢答记录 (点击展开)")
        record_btn.setStyleSheet("color: #888888; font-size: 12px;")
        r_layout.addWidget(record_btn)
        layout.addWidget(record_bar)

    def _create_status_bar(self):
        status = QStatusBar()
        status.setStyleSheet("""
            QStatusBar {
                background-color: #16213e;
                color: #888888;
                font-size: 12px;
                padding: 2px 15px;
                border-top: 1px solid #0f3460;
            }
        """)
        status.showMessage("🟢 服务端运行中  |  👥 5 名选手在线  |  📡 端口: 8888")
        self.setStatusBar(status)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 暗色主题调色板
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1a1a2e"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#1e1e1e"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#252525"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#333333"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#3c3c3c"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ff0000"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#0078d4"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
