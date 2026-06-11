"""
ttkbootstrap 效果演示 - 抢答软件 UI 预览
直接运行此文件即可看到效果
"""

import tkinter as tk
from tkinter import ttk

# ============================================================
# 手动实现 ttkbootstrap 风格的主题（无需 pip 安装）
# 以下代码模拟了 ttkbootstrap 的 SUPERHERO（暗色）主题
# ============================================================

def apply_dark_theme(root):
    """应用暗色主题"""
    style = ttk.Style(root)
    style.theme_use("clam")

    # 配色方案 - 类似 ttkbootstrap SUPERHERO 主题
    colors = {
        "bg": "#2b2b2b",
        "fg": "#ffffff",
        "select_bg": "#0078d4",
        "select_fg": "#ffffff",
        "button_bg": "#3c3c3c",
        "button_fg": "#ffffff",
        "button_active": "#0078d4",
        "entry_bg": "#3c3c3c",
        "entry_fg": "#ffffff",
        "frame_bg": "#1e1e1e",
        "label_fg": "#cccccc",
        "accent": "#0078d4",
        "success": "#4CAF50",
        "danger": "#f44336",
        "warning": "#FF9800",
        "info": "#2196F3",
    }

    # 配置各个控件样式
    style.configure("TLabel", background=colors["bg"], foreground=colors["fg"],
                    font=("微软雅黑", 10))
    style.configure("TFrame", background=colors["bg"])
    style.configure("TLabelframe", background=colors["bg"], foreground=colors["fg"],
                    font=("微软雅黑", 10))
    style.configure("TLabelframe.Label", background=colors["bg"], foreground=colors["accent"],
                    font=("微软雅黑", 10, "bold"))

    style.configure("TButton", background=colors["button_bg"], foreground=colors["button_fg"],
                    font=("微软雅黑", 10), borderwidth=1, focusthickness=0)
    style.map("TButton",
              background=[("active", colors["button_active"]), ("pressed", "#005a9e")],
              foreground=[("active", "white")])

    style.configure("Success.TButton", background=colors["success"], foreground="white",
                    font=("微软雅黑", 10, "bold"))
    style.map("Success.TButton",
              background=[("active", "#66BB6A"), ("pressed", "#388E3C")])

    style.configure("Danger.TButton", background=colors["danger"], foreground="white",
                    font=("微软雅黑", 10, "bold"))
    style.map("Danger.TButton",
              background=[("active", "#ef5350"), ("pressed", "#d32f2f")])

    style.configure("Warning.TButton", background=colors["warning"], foreground="white",
                    font=("微软雅黑", 10, "bold"))
    style.map("Warning.TButton",
              background=[("active", "#FFB74D"), ("pressed", "#F57C00")])

    style.configure("Info.TButton", background=colors["info"], foreground="white",
                    font=("微软雅黑", 10, "bold"))
    style.map("Info.TButton",
              background=[("active", "#42A5F5"), ("pressed", "#1565C0")])

    # Entry
    style.configure("TEntry", fieldbackground=colors["entry_bg"], foreground=colors["entry_fg"],
                    insertcolor="white", font=("微软雅黑", 10))
    style.map("TEntry",
              fieldbackground=[("focus", "#3c3c3c")],
              bordercolor=[("focus", colors["accent"])])

    # Combobox
    style.configure("TCombobox", fieldbackground=colors["entry_bg"], foreground=colors["entry_fg"],
                    font=("微软雅黑", 10), arrowcolor="white")
    style.map("TCombobox",
              fieldbackground=[("readonly", colors["entry_bg"])])

    # Treeview
    style.configure("Treeview", background=colors["frame_bg"], foreground=colors["fg"],
                    fieldbackground=colors["frame_bg"], font=("微软雅黑", 9))
    style.configure("Treeview.Heading", background=colors["button_bg"], foreground=colors["fg"],
                    font=("微软雅黑", 9, "bold"))
    style.map("Treeview",
              background=[("selected", colors["select_bg"])],
              foreground=[("selected", colors["select_fg"])])

    # Scrollbar
    style.configure("TScrollbar", background=colors["button_bg"], troughcolor=colors["frame_bg"],
                    arrowcolor="white")

    # Progressbar
    style.configure("TProgressbar", background=colors["accent"], troughcolor=colors["frame_bg"])

    # Checkbutton
    style.configure("TCheckbutton", background=colors["bg"], foreground=colors["fg"],
                    font=("微软雅黑", 10))
    style.map("TCheckbutton",
              background=[("active", colors["bg"])])

    # Radiobutton
    style.configure("TRadiobutton", background=colors["bg"], foreground=colors["fg"],
                    font=("微软雅黑", 10))

    return colors


def create_demo():
    root = tk.Tk()
    root.title("🎯 抢答软件 - ttkbootstrap 风格预览")
    root.geometry("1100x750")

    # 设置暗色主题背景
    root.configure(bg="#2b2b2b")
    colors = apply_dark_theme(root)

    # ========== 顶部标题栏 ==========
    title_bar = tk.Frame(root, bg="#1e1e1e", height=60)
    title_bar.pack(fill=tk.X)
    title_bar.pack_propagate(False)

    tk.Label(title_bar, text="🎯 抢答系统 · 主控端",
             font=("微软雅黑", 18, "bold"), bg="#1e1e1e", fg="#0078d4").pack(side=tk.LEFT, padx=20, pady=10)

    tk.Label(title_bar, text="比赛名称: 知识竞赛 2026",
             font=("微软雅黑", 10), bg="#1e1e1e", fg="#aaaaaa").pack(side=tk.RIGHT, padx=20, pady=10)

    # ========== 主体区域 ==========
    main_frame = tk.Frame(root, bg="#2b2b2b")
    main_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

    # ---- 左侧：选手面板 ----
    left_frame = tk.Frame(main_frame, bg="#1e1e1e", width=260)
    left_frame.pack(side=tk.LEFT, fill=tk.Y)
    left_frame.pack_propagate(False)

    # 选手标题
    tk.Label(left_frame, text="👥 选手管理",
             font=("微软雅黑", 12, "bold"), bg="#1e1e1e", fg="#0078d4").pack(anchor=tk.W, padx=15, pady=(15, 10))

    # 选手列表
    player_frame = tk.Frame(left_frame, bg="#252525")
    player_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    players = [
        ("🏆 IT", "120分", "#4CAF50", "第1名"),
        ("🥈 张三", "85分", "#2196F3", "第2名"),
        ("🥉 李四", "60分", "#FF9800", "第3名"),
        ("  王五", "35分", "#aaaaaa", ""),
        ("  赵六", "20分", "#aaaaaa", ""),
    ]

    for name, score, color, rank in players:
        p = tk.Frame(player_frame, bg="#2d2d2d", height=50)
        p.pack(fill=tk.X, padx=5, pady=3)
        p.pack_propagate(False)

        tk.Label(p, text=name, font=("微软雅黑", 11, "bold"),
                 bg="#2d2d2d", fg=color).pack(side=tk.LEFT, padx=10)

        tk.Label(p, text=score, font=("微软雅黑", 11),
                 bg="#2d2d2d", fg="#ffffff").pack(side=tk.RIGHT, padx=10)

        if rank:
            tk.Label(p, text=rank, font=("微软雅黑", 9),
                     bg="#2d2d2d", fg="#FFD700").pack(side=tk.RIGHT, padx=5)

    # 操作按钮
    btn_frame = tk.Frame(left_frame, bg="#1e1e1e")
    btn_frame.pack(fill=tk.X, padx=10, pady=10)

    ttk.Button(btn_frame, text="⚙ 设置", style="TButton").pack(fill=tk.X, pady=2)
    ttk.Button(btn_frame, text="🔄 重赛", style="Warning.TButton").pack(fill=tk.X, pady=2)
    ttk.Button(btn_frame, text="🏁 结束比赛", style="Danger.TButton").pack(fill=tk.X, pady=2)

    # ---- 右侧：内容面板 ----
    right_frame = tk.Frame(main_frame, bg="#2b2b2b")
    right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    # 信息栏
    info_bar = tk.Frame(right_frame, bg="#333333", height=45)
    info_bar.pack(fill=tk.X)
    info_bar.pack_propagate(False)

    info_items = [
        ("📚 题库", "知识问答 (25题)"),
        ("🎯 轮次", "第 3 轮"),
        ("✅ 已答", "8/25"),
        ("⏱ 倒计时", "15s"),
    ]
    for i, (label, value) in enumerate(info_items):
        f = tk.Frame(info_bar, bg="#333333")
        f.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        tk.Label(f, text=label, font=("微软雅黑", 9), bg="#333333", fg="#888888").pack()
        tk.Label(f, text=value, font=("微软雅黑", 11, "bold"), bg="#333333", fg="#ffffff").pack()

    # 横幅（抢答状态）
    banner = tk.Frame(right_frame, bg="#4CAF50", height=50)
    banner.pack(fill=tk.X)
    banner.pack_propagate(False)
    tk.Label(banner, text="🎉🎉🎉 [IT] 抢答成功！等待 [IT] 输入答案 ⏱ 15s 🎉🎉🎉",
             font=("微软雅黑", 12, "bold"), bg="#4CAF50", fg="white").pack(pady=10)

    # 题目区域
    question_frame = tk.Frame(right_frame, bg="#2b2b2b", padx=15, pady=10)
    question_frame.pack(fill=tk.BOTH, expand=True)

    # 题型标签
    tk.Label(question_frame, text="📝 选择题",
             font=("微软雅黑", 10, "bold"), bg="#2b2b2b", fg="#0078d4").pack(anchor=tk.W)

    # 题目文本
    q_text = tk.Text(question_frame, height=6, wrap=tk.WORD,
                     font=("微软雅黑", 12), bg="#1e1e1e", fg="#ffffff",
                     relief=tk.FLAT, padx=10, pady=10, borderwidth=0)
    q_text.insert(tk.END, "Python 中哪个关键字用于定义函数？")
    q_text.config(state=tk.DISABLED)
    q_text.pack(fill=tk.X, pady=(5, 10))

    # 操作按钮行
    op_row = tk.Frame(question_frame, bg="#2b2b2b")
    op_row.pack(fill=tk.X, pady=5)

    ttk.Button(op_row, text="◀ 上一题", style="TButton").pack(side=tk.LEFT, padx=2)
    ttk.Button(op_row, text="▶ 下一题", style="TButton").pack(side=tk.LEFT, padx=2)
    ttk.Button(op_row, text="🚀 开始抢答", style="Success.TButton").pack(side=tk.LEFT, padx=20)
    ttk.Button(op_row, text="■ 结束抢答", style="Danger.TButton").pack(side=tk.LEFT, padx=2)
    ttk.Button(op_row, text="👁 显示答案", style="Info.TButton").pack(side=tk.RIGHT, padx=2)

    # 参考答案
    ans_frame = tk.Frame(question_frame, bg="#1e1e1e", padx=10, pady=5)
    ans_frame.pack(fill=tk.X, pady=5)
    tk.Label(ans_frame, text="参考答案: def",
             font=("微软雅黑", 10), bg="#1e1e1e", fg="#4CAF50").pack(anchor=tk.W)

    # 底部日志按钮
    log_frame = tk.Frame(right_frame, bg="#2b2b2b", padx=15, pady=5)
    log_frame.pack(fill=tk.X)
    ttk.Button(log_frame, text="📋 日志", style="TButton").pack(side=tk.LEFT, padx=2)
    ttk.Button(log_frame, text="📋 抢答记录", style="TButton").pack(side=tk.LEFT, padx=2)

    # ========== 底部状态栏 ==========
    status = tk.Frame(root, bg="#1e1e1e", height=30)
    status.pack(fill=tk.X, side=tk.BOTTOM)
    status.pack_propagate(False)
    tk.Label(status, text="🟢 服务端运行中 | 👥 5 名选手在线 | 📡 端口: 8888",
             font=("微软雅黑", 9), bg="#1e1e1e", fg="#888888").pack(side=tk.LEFT, padx=15, pady=5)

    root.mainloop()


if __name__ == "__main__":
    create_demo()
