"""
抢答软件 - 主控端（服务端）
主持人在此控制题目、接收选手抢答、计分
支持题库导入（支持 TXT / CSV / JSON / XLSX 格式）
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import socket
import threading
import json
import os
import csv
import time
from datetime import datetime


DEBUG = True  # 设置为 False 可关闭 debug 日志

def debug_log(msg):
    if DEBUG:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:12]
        with open(os.path.join(os.path.dirname(__file__) or ".", "server_debug.log"), "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")


class QuizServer:
    def __init__(self, root):
        self.root = root
        self.root.title("抢答软件 - 主控端 v2.0")
        self.root.geometry("1000x700")
        self.root.resizable(True, True)

        self.server_socket = None
        self.running = False
        self.clients = {}
        self.lock = threading.Lock()
        self.round_num = 0
        self.round_active = False
        self.first_buzzer = None
        self.game_started = False  # 是否在比赛状态（非结束），控制客户端连接

        self.questions = []
        self.current_question_index = -1
        self.question_file_path = ""
        self.question_banks = {}         # 多个题库 {name: [questions]}
        self.active_bank_name = None     # 当前使用的题库名
        self._last_answer = ""  # 选手最后一次提交的答案
        self.auto_judge_var = tk.BooleanVar(value=True)  # 自动判题开关，默认开启

        # 分数配置
        self.correct_points = 2   # 答对加分
        self.wrong_points = 1     # 答错扣分
        self.answer_timeout = 15  # 答题超时秒数
        self.win_score = 20        # 获胜积分（0=不启用），默认20分
        self.win_rank_count = 3    # 决出前几名后比赛结束，默认3名
        self._timer_id = None     # 倒计时定时器ID
        self._timer_remaining = 0 # 剩余秒数
        self.game_over = False    # 是否已结束（第三名产生后）
        self.ranked_players = []  # 已锁定排名的选手列表 [(name, score, rank), ...]
        self.extend_limits = {}   # 选手每场比赛可延长次数 {name: remaining}
        self.extend_max = 1       # 每次比赛默认可延长次数
        self.extend_seconds = 15  # 每次延长秒数
        self.allow_repeat = False  # 题目是否可重复使用（默认不可重复）
        self.used_questions = set()  # 已使用过的题目索引

        self.host_ip = self._get_local_ip()
        self.heartbeat_interval = 5  # 心跳间隔（秒）
        self.game_name = "知识竞赛"       # 比赛名称，默认值

        # 题库持久化
        self.banks_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "question_banks.json")

        self._build_ui()
        self._load_banks()    # UI 构建完成后加载题库
        self._start_server()

    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"

    def _ask_game_name(self):
        """弹窗输入比赛名称，返回名称（取消则返回 None）"""
        dialog = tk.Toplevel(self.root)
        dialog.title("比赛名称")
        dialog.geometry("350x170")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 350) // 2
        y = (dialog.winfo_screenheight() - 170) // 2
        dialog.geometry(f"+{x}+{y}")

        result = [None]

        tk.Label(dialog, text="请输入本次比赛名称：", font=("微软雅黑", 12)).pack(pady=(20, 10))
        name_var = tk.StringVar(value="知识竞赛")
        entry = tk.Entry(dialog, textvariable=name_var, font=("微软雅黑", 12), width=25)
        entry.pack(pady=(0, 10))
        entry.select_range(0, tk.END)
        entry.focus()

        def confirm():
            val = name_var.get().strip()
            result[0] = val if val else "知识竞赛"
            dialog.destroy()

        def cancel():
            result[0] = None
            dialog.destroy()

        btn_row = tk.Frame(dialog)
        btn_row.pack(pady=5)
        tk.Button(btn_row, text="开始比赛", font=("微软雅黑", 10),
                  bg="#4CAF50", fg="white", width=10, command=confirm).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_row, text="取消", font=("微软雅黑", 10),
                  bg="#9E9E9E", fg="white", width=8, command=cancel).pack(side=tk.LEFT, padx=5)

        dialog.protocol("WM_DELETE_WINDOW", cancel)
        entry.bind("<Return>", lambda e: confirm())
        self.root.wait_window(dialog)
        return result[0]

    def _build_ui(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="导入题库...", command=self._import_questions, accelerator="Ctrl+O")
        file_menu.add_command(label="导出成绩", command=self._export_scores)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="题库格式说明", command=self._show_format_help)
        help_menu.add_command(label="关于", command=self._show_about)

        self.root.bind("<Control-o>", lambda e: self._import_questions())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # ========== 主页面 ==========
        self.home_frame = tk.Frame(self.root)
        self.home_frame.pack(fill=tk.BOTH, expand=True)

        status_bar = tk.Frame(self.home_frame, bg="#333")
        status_bar.pack(fill=tk.X)
        self.home_status = tk.Label(
            status_bar, text=f"🟢 服务器运行中 | IP: {self.host_ip}:8888",
            font=("微软雅黑", 10), bg="#333", fg="#fff", pady=8
        )
        self.home_status.pack()

        btn_container = tk.Frame(self.home_frame)
        btn_container.place(relx=0.5, rely=0.45, anchor="center")

        btn_font = ("微软雅黑", 16, "bold")
        btn_width = 14

        self.home_start_btn = tk.Button(
            btn_container, text="🚀 开始比赛", font=btn_font,
            bg="#FF5722", fg="white", width=btn_width, height=2,
            command=self._switch_to_game
        )
        self.home_start_btn.pack(pady=10)

        self.home_bank_btn = tk.Button(
            btn_container, text="📚 题库管理", font=btn_font,
            bg="#FF9800", fg="white", width=btn_width, height=2,
            command=self._switch_to_bank
        )
        self.home_bank_btn.pack(pady=10)

        self.home_settings_btn = tk.Button(
            btn_container, text="⚙ 设置", font=btn_font,
            bg="#607D8B", fg="white", width=btn_width, height=2,
            command=self._show_settings
        )
        self.home_settings_btn.pack(pady=10)

        # ========== 题库管理页面 ==========
        self.bank_page_frame = tk.Frame(self.root)

        bank_top = tk.Frame(self.bank_page_frame)
        bank_top.pack(fill=tk.X, padx=10, pady=(10, 0))
        tk.Button(
            bank_top, text="← 返回主页", font=("微软雅黑", 9),
            bg="#333", fg="white", command=self._switch_to_home_from_bank
        ).pack(side=tk.LEFT)
        tk.Label(bank_top, text="📚 题库管理", font=("微软雅黑", 14, "bold"),
                 fg="#FF9800").pack(side=tk.LEFT, padx=15)

        # 题库列表
        bank_list_frame = tk.LabelFrame(self.bank_page_frame, text="已导入的题库",
                                         font=("微软雅黑", 10))
        bank_list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.bank_listbox = tk.Listbox(
            bank_list_frame, font=("微软雅黑", 11),
            selectmode=tk.SINGLE, activestyle="none"
        )
        self.bank_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        bank_scroll = tk.Scrollbar(bank_list_frame, orient=tk.VERTICAL,
                                    command=self.bank_listbox.yview)
        self.bank_listbox.configure(yscrollcommand=bank_scroll.set)
        bank_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        self.bank_listbox.bind("<ButtonRelease-1>", self._on_bank_list_select)
        self.bank_listbox.bind("<Delete>", lambda e: self._remove_bank_from_list())

        # 底部按钮
        bank_btn_frame = tk.Frame(self.bank_page_frame)
        bank_btn_frame.pack(fill=tk.X, padx=10, pady=(0, 15))

        self.bank_import_btn = tk.Button(
            bank_btn_frame, text="📂 导入题库", font=("微软雅黑", 11),
            bg="#FF9800", fg="white", width=12, command=self._import_questions
        )
        self.bank_import_btn.pack(side=tk.LEFT, padx=5)

        self.bank_del_list_btn = tk.Button(
            bank_btn_frame, text="🗑 删除选中", font=("微软雅黑", 11),
            bg="#f44336", fg="white", width=12, command=self._remove_bank_from_list
        )
        self.bank_del_list_btn.pack(side=tk.LEFT, padx=5)

        # ========== 比赛页面 ==========
        self.game_frame = tk.Frame(self.root)

        game_top_bar = tk.Frame(self.game_frame)
        game_top_bar.pack(fill=tk.X, padx=8, pady=(4, 0))
        self.back_home_btn = tk.Button(
            game_top_bar, text="← 返回主页", font=("微软雅黑", 9),
            bg="#333", fg="white", command=self._switch_to_home
        )
        self.back_home_btn.pack(side=tk.LEFT)
        self.game_title_label = tk.Label(
            game_top_bar, text=f"🏆 {self.game_name}",
            font=("微软雅黑", 12, "bold"), fg="#FF5722"
        )
        self.game_title_label.pack(side=tk.LEFT, padx=15)

        top_frame = tk.Frame(self.game_frame, height=100)
        top_frame.pack(fill=tk.X, padx=8, pady=4)

        mid_frame = tk.Frame(self.game_frame)
        mid_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        bottom_frame = tk.Frame(self.game_frame, height=150)
        bottom_frame.pack(fill=tk.X, padx=8, pady=4)

        # === 顶部 ===
        status_frame = tk.LabelFrame(top_frame, text="服务器状态", font=("微软雅黑", 10))
        status_frame.pack(fill=tk.X)

        self.status_label = tk.Label(
            status_frame,
            text=f"IP: {self.host_ip} | 端口: 8888 | 题库: 未导入",
            font=("微软雅黑", 9)
        )
        self.status_label.pack(side=tk.LEFT, padx=8, pady=4)

        ctrl_frame = tk.Frame(status_frame)
        ctrl_frame.pack(side=tk.RIGHT, padx=8, pady=4)

        self.prev_btn = tk.Button(
            ctrl_frame, text="上一题 ◀", font=("微软雅黑", 10),
            bg="#2196F3", fg="white", width=10, state=tk.DISABLED, command=self._prev_question
        )
        self.prev_btn.pack(side=tk.LEFT, padx=2)

        self.next_round_btn = tk.Button(
            ctrl_frame, text="下一题 ▶", font=("微软雅黑", 10),
            bg="#4CAF50", fg="white", width=10, command=self._next_question
        )
        self.next_round_btn.pack(side=tk.LEFT, padx=2)

        self.start_buzz_btn = tk.Button(
            ctrl_frame, text="开始抢答 🚀", font=("微软雅黑", 10),
            bg="#FF5722", fg="white", width=10, state=tk.DISABLED, command=self._start_buzz
        )
        self.start_buzz_btn.pack(side=tk.LEFT, padx=2)

        self.stop_round_btn = tk.Button(
            ctrl_frame, text="结束抢答 ■", font=("微软雅黑", 10),
            bg="#f44336", fg="white", width=10, state=tk.DISABLED, command=self._stop_round
        )
        self.stop_round_btn.pack(side=tk.LEFT, padx=2)

        self.rank_btn = tk.Button(
            ctrl_frame, text="📊 积分榜", font=("微软雅黑", 9),
            bg="#9C27B0", fg="white", width=10, command=self._show_rankings
        )
        self.rank_btn.pack(side=tk.LEFT, padx=2)

        self.reset_score_btn = tk.Button(
            ctrl_frame, text="🔄 重置计分", font=("微软雅黑", 9),
            bg="#795548", fg="white", width=10, command=self._reset_scores
        )
        self.reset_score_btn.pack(side=tk.LEFT, padx=2)

        self.restart_btn = tk.Button(
            ctrl_frame, text="🆕 重赛", font=("微软雅黑", 9),
            bg="#E91E63", fg="white", width=8, command=self._restart_game
        )
        self.restart_btn.pack(side=tk.LEFT, padx=2)

        self.end_game_btn = tk.Button(
            ctrl_frame, text="🏁 结束比赛", font=("微软雅黑", 9),
            bg="#9E9E9E", fg="white", width=10, command=self._end_game
        )
        self.end_game_btn.pack(side=tk.LEFT, padx=2)

        # === 抢答结果横幅 ===
        banner_frame = tk.Frame(top_frame)
        banner_frame.pack(fill=tk.X, padx=8, pady=(0, 4))
        self.buzz_banner = tk.Label(
            banner_frame, text="⚠️ 请先导入题库",
            font=("微软雅黑", 18, "bold"),
            bg="#FF9800", fg="white",
            height=2
        )
        self.buzz_banner.pack(fill=tk.X)

        # === 中部左：题库 ===
        question_frame = tk.LabelFrame(mid_frame, text="📖 题库", font=("微软雅黑", 10))
        question_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))

        # 题库选择器
        bank_frame = tk.Frame(question_frame)
        bank_frame.pack(fill=tk.X, padx=5, pady=(3, 0))
        tk.Label(bank_frame, text="当前题库:", font=("微软雅黑", 9)).pack(side=tk.LEFT)
        self.bank_combo = ttk.Combobox(
            bank_frame, state="readonly", font=("微软雅黑", 9),
            width=20
        )
        self.bank_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.bank_combo.bind("<<ComboboxSelected>>", self._on_bank_select)
        self.bank_del_btn = tk.Button(
            bank_frame, text="✕", font=("微软雅黑", 8),
            width=2, command=self._remove_bank
        )
        self.bank_del_btn.pack(side=tk.RIGHT)

        progress_frame = tk.Frame(question_frame)
        progress_frame.pack(fill=tk.X, padx=5, pady=3)

        self.progress_label = tk.Label(progress_frame, text="进度: 0 / 0", font=("微软雅黑", 9))
        self.progress_label.pack(side=tk.LEFT)
        self.points_label = tk.Label(progress_frame, text="分值: --", font=("微软雅黑", 9), fg="orange")
        self.points_label.pack(side=tk.RIGHT)

        self.question_display = tk.Text(
            question_frame, font=("微软雅黑", 12), height=6,
            wrap=tk.WORD, bg="#FFF8E1", state=tk.DISABLED
        )
        self.question_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

        ans_frame = tk.Frame(question_frame)
        ans_frame.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(ans_frame, text="参考答案:", font=("微软雅黑", 9, "bold")).pack(side=tk.LEFT)
        self.answer_label = tk.Label(ans_frame, text="--", font=("微软雅黑", 10), fg="#1565C0")
        self.answer_label.pack(side=tk.LEFT, padx=10)
        self.show_answer_btn = tk.Button(
            ans_frame, text="显示答案 👁", font=("微软雅黑", 9), command=self._toggle_answer
        )
        self.show_answer_btn.pack(side=tk.RIGHT)
        self.answer_visible = False

        # === 抢答记录按钮（点击展开） ===
        self.record_btn = tk.Button(
            question_frame, text="📋 抢答记录", font=("微软雅黑", 9),
            command=self._toggle_record
        )
        self.record_btn.pack(anchor=tk.W, padx=5, pady=(0, 2))

        # === 抢答记录（默认隐藏） ===
        self.record_frame = tk.LabelFrame(question_frame, text="📋 抢答记录", font=("微软雅黑", 10))
        # 初始不 pack

        rec_columns = ("answer", "result", "correct")
        self.record_tree = ttk.Treeview(self.record_frame, columns=rec_columns, show="headings", height=8)
        self.record_tree.heading("answer", text="选手答案")
        self.record_tree.heading("result", text="结果")
        self.record_tree.heading("correct", text="正确答案")
        self.record_tree.column("answer", width=120, anchor="center")
        self.record_tree.column("result", width=80, anchor="center")
        self.record_tree.column("correct", width=120, anchor="center")
        rec_vsb = ttk.Scrollbar(self.record_frame, orient="vertical", command=self.record_tree.yview)
        self.record_tree.configure(yscrollcommand=rec_vsb.set)
        self.record_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        rec_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        # record_frame 本身不 pack，点击按钮才显示

        # === 中部右：选手 ===
        player_frame = tk.LabelFrame(mid_frame, text="👥 选手管理", font=("微软雅黑", 10))
        player_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(4, 0))

        columns = ("name", "score", "status")
        self.player_tree = ttk.Treeview(player_frame, columns=columns, show="headings", height=8)
        self.player_tree.heading("name", text="选手名")
        self.player_tree.heading("score", text="得分")
        self.player_tree.heading("status", text="状态")
        self.player_tree.column("name", width=100)
        self.player_tree.column("score", width=60, anchor="center")
        self.player_tree.column("status", width=70, anchor="center")
        p_vsb = ttk.Scrollbar(player_frame, orient="vertical", command=self.player_tree.yview)
        self.player_tree.configure(yscrollcommand=p_vsb.set)
        self.player_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        p_vsb.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        self.popup_menu = tk.Menu(self.root, tearoff=0)
        self.popup_menu.add_command(label="加分 (+1)", command=lambda: self._change_score(1))
        self.popup_menu.add_command(label="加分 (+5)", command=lambda: self._change_score(5))
        self.popup_menu.add_command(label="减分 (-1)", command=lambda: self._change_score(-1))
        self.popup_menu.add_command(label="减分 (-5)", command=lambda: self._change_score(-5))
        self.popup_menu.add_separator()
        self.popup_menu.add_command(label="🎯 设置分数", command=self._set_score)
        self.popup_menu.add_command(label="🚫 违规扣5分", command=self._foul_penalty)
        self.popup_menu.add_separator()
        self.popup_menu.add_command(label="✅ 答对加分", command=self._mark_correct)
        self.popup_menu.add_command(label="❌ 答错减分", command=self._mark_wrong)
        self.popup_menu.add_separator()
        self.popup_menu.add_command(label="禁赛/恢复", command=self._toggle_ban)
        self.popup_menu.add_command(label="断开连接", command=self._disconnect_player)
        self.player_tree.bind("<Button-3>", self._show_popup)

        msg_frame = tk.Frame(player_frame)
        msg_frame.pack(fill=tk.X, padx=5, pady=2)
        self.msg_entry = tk.Entry(msg_frame, font=("微软雅黑", 9))
        self.msg_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        self.msg_entry.insert(0, "发送消息给所有选手...")
        self.msg_entry.bind(
            "<FocusIn>",
            lambda e: self.msg_entry.delete(0, tk.END)
            if self.msg_entry.get() == "发送消息给所有选手..." else None
        )
        send_btn = tk.Button(msg_frame, text="发送", font=("微软雅黑", 9), bg="#2196F3", fg="white", command=self._send_message_to_all)
        send_btn.pack(side=tk.RIGHT)

        # === 底部：日志按钮 ===
        self.log_btn = tk.Button(
            bottom_frame, text="📋 日志", font=("微软雅黑", 9),
            command=self._toggle_log
        )
        self.log_btn.pack(anchor=tk.W, padx=5, pady=2)

        # === 日志区域（默认隐藏） ===
        self.log_frame = tk.LabelFrame(bottom_frame, text="系统日志", font=("微软雅黑", 10))
        # 初始不 pack，通过日志按钮控制
        self.log_area = scrolledtext.ScrolledText(
            self.log_frame, height=5, font=("微软雅黑", 9),
            bg="#1e1e1e", fg="#d4d4d4", state=tk.DISABLED
        )
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self._log(f"🚀 主控端 v2.0 启动，服务器 IP: {self.host_ip}")

    # ========== 页面切换 ==========

    def _switch_to_game(self):
        """切换到比赛页面（首次进入弹出名称，再次进入为继续比赛）"""
        if not self.question_banks:
            messagebox.showwarning("提示", "请先导入题库才能开始比赛\n点击「📚 题库管理」导入题库")
            return
        # 没有选中的题库时自动选第一个
        if not self.active_bank_name or not self.questions:
            first = list(self.question_banks.keys())[0]
            self._activate_bank(first)
        # 如果已经在比赛状态，直接切回去
        if self.game_started:
            self.game_frame.pack(fill=tk.BOTH, expand=True)
            self.home_frame.pack_forget()
            self._log("🎮 继续比赛")
            return
        name = self._ask_game_name()
        if name is None:  # 用户取消了
            return
        self.game_name = name
        self.root.title(f"抢答软件 - 主控端 | {self.game_name}")
        self.game_started = True
        self.home_frame.pack_forget()
        self.game_frame.pack(fill=tk.BOTH, expand=True)
        self.game_title_label.config(text=f"🏆 {self.game_name}")
        self._log(f"🎮 进入比赛模式 — 比赛名称: {self.game_name}")

    def _switch_to_home(self):
        """切换到主页面（保持比赛状态，客户端连接不受影响）"""
        if self.game_started:
            self.home_start_btn.config(text="▶ 继续比赛", bg="#4CAF50")
        else:
            self.home_start_btn.config(text="🚀 开始比赛", bg="#FF5722")
        self.game_frame.pack_forget()
        self.home_frame.pack(fill=tk.BOTH, expand=True)
        self._log("🏠 返回主页")

    def _switch_to_bank(self):
        """切换到题库管理页面"""
        self.home_frame.pack_forget()
        self._update_bank_listbox()
        self.bank_page_frame.pack(fill=tk.BOTH, expand=True)
        self._log("📚 进入题库管理")

    def _switch_to_home_from_bank(self):
        """从题库管理页面返回主页"""
        self.bank_page_frame.pack_forget()
        self.home_frame.pack(fill=tk.BOTH, expand=True)

    def _update_bank_listbox(self):
        """更新题库管理页面的列表"""
        self.bank_listbox.delete(0, tk.END)
        if not self.question_banks:
            self.bank_listbox.insert(tk.END, "(暂无题库，点击下方「导入题库」添加)")
            self.bank_del_list_btn.config(state=tk.DISABLED)
            self.bank_use_btn.config(state=tk.DISABLED)
            return
        for name, questions in self.question_banks.items():
            active = " ✅ 使用中" if name == self.active_bank_name else ""
            self.bank_listbox.insert(tk.END, f"  {name}（{len(questions)} 题）{active}")

    def _on_bank_list_select(self, event):
        """点击题库列表项"""
        sel = self.bank_listbox.curselection()
        if not sel:
            return
        self.bank_del_list_btn.config(state=tk.NORMAL)

    def _remove_bank_from_list(self):
        """从题库管理页面删除选中题库"""
        sel = self.bank_listbox.curselection()
        if not sel:
            return
        text = self.bank_listbox.get(sel[0])
        # 提取题库名
        name = text.split("（")[0].strip()
        if name.startswith("  "):
            name = name[2:]
        if not name or name not in self.question_banks:
            return
        if not messagebox.askyesno("确认删除", f"确定要从内存中删除题库「{name}」吗？\n（不会删除源文件）"):
            return
        del self.question_banks[name]
        self._update_bank_listbox()
        self._update_bank_combo()
        if name == self.active_bank_name:
            if self.question_banks:
                first = list(self.question_banks.keys())[0]
                self._activate_bank(first)
            else:
                self.questions = []
                self.active_bank_name = None
                self.used_questions.clear()
        self._log(f"🗑 已删除题库: {name}")

    # =============== 题库 ===============

    def _import_questions(self):
        file_path = filedialog.askopenfilename(
            title="选择题库文件",
            filetypes=[
                ("支持的格式", "*.txt *.csv *.json *.xlsx"),
                ("文本文件", "*.txt"),
                ("CSV 文件", "*.csv"),
                ("JSON 文件", "*.json"),
                ("Excel 文件", "*.xlsx"),
                ("所有文件", "*.*")
            ]
        )
        if not file_path:
            return
        try:
            ext = os.path.splitext(file_path)[1].lower()
            if ext == ".json":
                questions = self._parse_json(file_path)
            elif ext == ".csv":
                questions = self._parse_csv(file_path)
            elif ext == ".xlsx":
                questions = self._parse_xlsx(file_path)
            else:
                questions = self._parse_txt(file_path)

            if not questions:
                messagebox.showwarning("导入结果", "题库为空或格式不正确。\n帮助 → 题库格式说明")
                return

            bank_name = os.path.splitext(os.path.basename(file_path))[0]
            # 如果同名已存在，添加序号
            orig_name = bank_name
            idx = 2
            while bank_name in self.question_banks:
                bank_name = f"{orig_name}({idx})"
                idx += 1

            self.question_banks[bank_name] = questions
            self._update_bank_combo()
            self.bank_combo.set(bank_name)
            self._activate_bank(bank_name)
            self._update_bank_listbox()
            self._save_banks()

            self._log(f"📚 导入题库: {bank_name} — 共 {len(questions)} 题")
        except Exception as e:
            messagebox.showerror("导入失败", f"读取文件出错:\n{e}")

    # =============== 题库管理（多题库） ===============

    def _update_bank_combo(self):
        """更新题库下拉列表"""
        names = list(self.question_banks.keys())
        self.bank_combo["values"] = names
        if not names:
            self.bank_combo.set("")
            self.bank_del_btn.config(state=tk.DISABLED)
        else:
            self.bank_del_btn.config(state=tk.NORMAL)

    def _on_bank_select(self, event):
        """下拉选择题库"""
        name = self.bank_combo.get()
        if name and name in self.question_banks:
            self._activate_bank(name)

    def _activate_bank(self, name):
        """激活指定题库"""
        if name not in self.question_banks:
            return
        self.active_bank_name = name
        self.questions = self.question_banks[name]
        self.current_question_index = -1
        self.used_questions.clear()
        self.status_label.config(
            text=f"IP: {self.host_ip} | 端口: 8888 | 题库: {name} ({len(self.questions)} 题)"
        )
        self.buzz_banner.config(text=f"⏳ 题库已就绪：{name}（{len(self.questions)} 题），等待开始...", bg="#FF9800")
        self._show_welcome()

    def _remove_bank(self):
        """删除当前题库"""
        name = self.bank_combo.get()
        if not name or name not in self.question_banks:
            return
        if not messagebox.askyesno("确认删除", f"确定要从内存中删除题库「{name}」吗？\n（不会删除源文件）"):
            return
        del self.question_banks[name]
        self._update_bank_combo()
        if self.question_banks:
            first = list(self.question_banks.keys())[0]
            self.bank_combo.set(first)
            self._activate_bank(first)
        else:
            self.bank_combo.set("")
            self.questions = []
            self.current_question_index = -1
            self.active_bank_name = None
            self.used_questions.clear()
            self.buzz_banner.config(text="⚠️ 请先导入题库", bg="#FF9800")
            self.status_label.config(text=f"IP: {self.host_ip} | 端口: 8888 | 题库: 无")
            self._show_welcome()
        self._log(f"🗑 已删除题库: {name}")
        self._update_bank_listbox()
        self._save_banks()

    # =============== 题库持久化 ===============

    def _save_banks(self):
        """将题库数据保存到 JSON 文件"""
        try:
            data = {}
            for name, questions in self.question_banks.items():
                data[name] = questions
            with open(self.banks_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log(f"⚠️ 保存题库失败: {e}")

    def _load_banks(self):
        """从 JSON 文件加载题库数据"""
        if not os.path.exists(self.banks_file):
            return
        try:
            with open(self.banks_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.question_banks = {}
            for name, questions in data.items():
                if isinstance(questions, list) and len(questions) > 0:
                    self.question_banks[name] = questions
            self._update_bank_combo()
            if self.question_banks:
                first = list(self.question_banks.keys())[0]
                self.bank_combo.set(first)
                self._activate_bank(first)
                self._update_bank_listbox()
                self._log(f"📂 已加载 {len(self.question_banks)} 个题库（共 {sum(len(q) for q in self.question_banks.values())} 题）")
        except Exception as e:
            self._log(f"⚠️ 加载题库失败: {e}")

    def _parse_txt(self, file_path):
        questions = []
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            points = 10
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                question = parts[0]
                answer = parts[1] if len(parts) > 1 else ""
                if len(parts) > 2:
                    try:
                        points = int(parts[2])
                    except:
                        pass
            else:
                if "（" in line and "）" in line:
                    idx = line.index("（")
                    question = line[:idx].strip()
                    answer = line[idx+1:-1].strip()
                elif "(" in line and ")" in line:
                    idx = line.index("(")
                    question = line[:idx].strip()
                    answer = line[idx+1:-1].strip()
                else:
                    question = line
                    answer = ""
            questions.append({"question": question, "answer": answer, "points": points})
        return questions

    def _parse_csv(self, file_path):
        questions = []
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i == 0:
                    continue
                if not row or not row[0].strip():
                    continue
                question = row[0].strip()
                answer = row[1].strip() if len(row) > 1 else ""
                points = 10
                if len(row) > 2:
                    try:
                        points = int(row[2])
                    except:
                        pass
                questions.append({"question": question, "answer": answer, "points": points})
        return questions

    def _parse_json(self, file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "questions" in data:
            return data["questions"]
        return []

    def _parse_xlsx(self, file_path):
        """解析 XLSX 格式题库
        自动识别表头映射，支持任意列顺序：
        题目列 -> question
        答案列 -> answer
        分值列 -> points
        选项列 -> 附加到题目末尾
        题型列 -> 附加到题目末尾
        """
        try:
            import openpyxl
        except ImportError:
            messagebox.showerror("缺少依赖", "需要安装 openpyxl 才能导入 xlsx 文件\n运行: pip install openpyxl")
            return []

        wb = openpyxl.load_workbook(file_path)
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []

        # 识别表头映射
        header = [str(h).strip() if h else "" for h in rows[0]]
        col_map = {}
        for i, h in enumerate(header):
            hl = h.lower()
            if hl in ("题目", "问题", "question", "考题"):
                col_map["question"] = i
            elif hl in ("答案", "answer", "正确答案", "参考答案"):
                col_map["answer"] = i
            elif hl in ("分值", "分数", "points", "score", "分数值"):
                col_map["points"] = i
            elif hl in ("选项", "options", "choices", "选择"):
                col_map["options"] = i
            elif hl in ("题型", "type", "题型分类", "题目类型"):
                col_map["type"] = i

        # 如果没找到题目列，用固定映射：第6列（F列）是题目，第9列（I列）是答案，第8列（H列）是分值
        if "question" not in col_map:
            col_map["question"] = 5  # F列
        if "answer" not in col_map:
            col_map["answer"] = 8  # I列
        if "points" not in col_map:
            col_map["points"] = 7  # H列
        if "options" not in col_map:
            col_map["options"] = 6  # G列
        if "type" not in col_map:
            col_map["type"] = 4  # E列

        questions = []
        for row in rows[1:]:
            if not row or not row[col_map["question"]]:
                continue

            question = str(row[col_map["question"]]).strip()

            # 如果有题型，加在题目前面
            q_type = str(row[col_map["type"]]).strip() if col_map["type"] < len(row) and row[col_map["type"]] else ""

            # 如果有选项，追加到题目后面
            options = str(row[col_map["options"]]).strip() if col_map["options"] < len(row) and row[col_map["options"]] else ""
            if options and options.lower() not in ("none", "无", ""):
                # 换行显示选项
                formatted_opts = "\n" + options.replace("\n", "\n")
                question += formatted_opts

            answer = str(row[col_map["answer"]]).strip() if col_map["answer"] < len(row) and row[col_map["answer"]] else ""

            points = 10
            if col_map["points"] < len(row) and row[col_map["points"]]:
                try:
                    points = int(float(str(row[col_map["points"]])))
                except:
                    pass

            questions.append({
                "question": question,
                "answer": answer,
                "points": points,
                "type": q_type
            })

        return questions

    def _update_question_list(self):
        self.record_tree.delete(*self.record_tree.get_children())

    def _update_progress(self):
        total = len(self.questions)
        answered = len(self.used_questions)
        remaining = total - answered
        self.progress_label.config(text=f"共：{total}题 | 已答：{answered}题 | 未答：{remaining}题")
        if 0 <= self.current_question_index < len(self.questions):
            pts = self.questions[self.current_question_index]["points"]
            self.points_label.config(text=f"分值: {pts} 分")
        else:
            self.points_label.config(text="分值: --")

    def _get_question_type(self, q):
        """获取题型，直接从导入数据中读取"""
        return q.get("type", "")

    def _show_question(self, index):
        self.current_question_index = index
        self.answer_visible = False
        self.show_answer_btn.config(text="显示答案 👁")
        self.question_display.config(state=tk.NORMAL)
        self.question_display.delete("1.0", tk.END)
        if 0 <= index < len(self.questions):
            q = self.questions[index]
            q_type = q.get("type", "")
            if q_type:
                self.question_display.insert(tk.END, f"{q_type}\n\n")
            self.question_display.insert(tk.END, q["question"])
            self.answer_label.config(text='(点击"显示答案"查看)')
        else:
            self.question_display.insert(tk.END, "请导入题库或点击题目列表中的题目查看")
            self.answer_label.config(text="--")
        self.question_display.config(state=tk.DISABLED)
        # 不允许重复时，如果当前题已用完则禁用开始抢答
        if not self.allow_repeat and 0 <= index < len(self.questions) and index in self.used_questions:
            self.start_buzz_btn.config(state=tk.DISABLED)
        else:
            self.start_buzz_btn.config(state=tk.NORMAL)
        self._update_progress()
        self._update_nav_buttons()

    def _update_nav_buttons(self):
        """更新上一题/下一题按钮状态"""
        if self.current_question_index <= 0:
            self.prev_btn.config(state=tk.DISABLED)
        else:
            self.prev_btn.config(state=tk.NORMAL)
        # 下一题：不允许重复且所有题都用完时禁用，或到边界时禁用
        if self.current_question_index >= len(self.questions) - 1:
            self.next_round_btn.config(state=tk.DISABLED)
        elif not self.allow_repeat and len(self.used_questions) >= len(self.questions):
            self.next_round_btn.config(state=tk.DISABLED)
        elif not self.allow_repeat:
            # 检查是否还有未使用的题目
            remaining = [i for i in range(len(self.questions)) if i not in self.used_questions]
            if not remaining:
                self.next_round_btn.config(state=tk.DISABLED)
            else:
                self.next_round_btn.config(state=tk.NORMAL)
        else:
            self.next_round_btn.config(state=tk.NORMAL)

    def _show_welcome(self):
        """导入题库后显示过渡页面"""
        self.current_question_index = -1
        self.answer_visible = False
        self.show_answer_btn.config(text="显示答案 👁")
        self.answer_label.config(text="--")
        self.question_display.config(state=tk.NORMAL)
        self.question_display.delete("1.0", tk.END)
        self.question_display.insert(tk.END, f"📚 题库已加载：{len(self.questions)} 道题\n\n")
        self.question_display.insert(tk.END, "✅ 点击「▶ 下一题」开始浏览题目\n")
        self.question_display.insert(tk.END, "🚀 点击「开始抢答 🚀」发起抢答\n\n")
        self.question_display.insert(tk.END, "📌 选手连接后即可开始比赛")
        self.question_display.config(state=tk.DISABLED)
        self._update_progress()
        self._update_nav_buttons()
        self.start_buzz_btn.config(state=tk.NORMAL)

    def _toggle_answer(self):
        if self.current_question_index < 0 or self.current_question_index >= len(self.questions):
            return
        q = self.questions[self.current_question_index]
        if not q["answer"]:
            self.answer_label.config(text="（无参考答案）")
            return
        self.answer_visible = not self.answer_visible
        if self.answer_visible:
            self.answer_label.config(text=q["answer"], fg="#1565C0")
            self.show_answer_btn.config(text="隐藏答案 🙈")
        else:
            self.answer_label.config(text='(点击"显示答案"查看)')
            self.show_answer_btn.config(text="显示答案 👁")

    def _add_record(self, player_answer, result, correct_answer):
        """添加一条抢答记录"""
        self.record_tree.insert("", 0, values=(player_answer, result, correct_answer))

    def _next_question(self):
        """切换到下一题"""
        if not self.questions:
            self._log("⚠️ 请先导入题库")
            return

        next_idx = self.current_question_index + 1
        if next_idx >= len(self.questions):
            self._log("📋 已到最后一题")
            return

        # 如果不允许重复，自动跳过已使用的题目
        if not self.allow_repeat:
            while next_idx < len(self.questions) and next_idx in self.used_questions:
                next_idx += 1
            if next_idx >= len(self.questions):
                self._log("📋 所有题目都已使用过")
                return

        self._show_question(next_idx)
        self.start_buzz_btn.config(state=tk.NORMAL)
        self._log(f"📋 切换到第 {next_idx+1} 题，点击「开始抢答 🚀」发送给选手")

    def _prev_question(self):
        """切换到上一题"""
        if not self.questions:
            return
        prev_idx = self.current_question_index - 1
        # 不可重复模式下跳过已使用的题目
        if not self.allow_repeat:
            while prev_idx >= 0 and prev_idx in self.used_questions:
                prev_idx -= 1
        if prev_idx < 0:
            self._log("📋 已是第一题")
            return
        self._show_question(prev_idx)
        self.start_buzz_btn.config(state=tk.NORMAL)
        self._log(f"📋 切换到第 {prev_idx+1} 题，点击「开始抢答 🚀」发送给选手")

    def _start_buzz(self):
        """开始抢答：把当前题目发送给所有选手"""
        debug_log(">>> _start_buzz 被调用")
        if self.game_over:
            messagebox.showwarning("提示", "⚠️ 比赛已结束，无法开始抢答")
            self._log("⚠️ 比赛已结束，无法开始抢答")
            return
        if self.current_question_index < 0 or self.current_question_index >= len(self.questions):
            # 还没选过题目，自动切到第一题
            if len(self.questions) > 0:
                self._show_question(0)
                self._log(f"📋 自动切换到第 1 题")
            else:
                self._log("⚠️ 请先导入题库")
                return
            debug_log("<<< _start_buzz 退出: 无有效题目")
            return

        if not self.clients:
            self._log("⚠️ 没有选手连接，无法开始抢答")
            messagebox.showwarning("提示", "没有选手连接，无法开始抢答")
            debug_log("<<< _start_buzz 退出: 无客户端连接")
            return

        # 不允许重复时，检查当前题是否已使用过
        if not self.allow_repeat and self.current_question_index in self.used_questions:
            self._log("⚠️ 当前题目已被使用过，请切换到下一题")
            messagebox.showwarning("提示", "当前题目已被使用过，请切换到下一题")
            debug_log("<<< _start_buzz 退出: 题目已使用")
            return

        debug_log(f"_start_buzz 准备抢锁, clients={list(self.clients.keys())}")
        with self.lock:
            debug_log("_start_buzz 拿到锁")
            q = self.questions[self.current_question_index]
            self.round_num += 1
            self.round_active = True
            self.first_buzzer = None
            # 记录已使用题目
            if not self.allow_repeat:
                self.used_questions.add(self.current_question_index)
            debug_log(f"_start_buzz 开始第 {self.round_num} 轮")
            self.start_buzz_btn.config(state=tk.DISABLED)
            self.stop_round_btn.config(state=tk.NORMAL)
            self.prev_btn.config(state=tk.DISABLED)
            self.next_round_btn.config(state=tk.DISABLED)

            self._log(f"🟢 === 第 {self.round_num} 轮: 第 {self.current_question_index+1} 题（{q['points']} 分）===")
            self.buzz_banner.config(text=f"🟢 第 {self.round_num} 轮抢答进行中...", bg="#4CAF50")
            debug_log("_start_buzz 准备广播 round_start")
            self._broadcast({"type": "round_start", "round": self.round_num, "msg": f"🟢 第 {self.round_num} 轮抢答开始！按 空格键 或 回车键 抢答！"})
            debug_log("_start_buzz round_start 广播完毕")
            q_type = q.get("type", "")
            self._broadcast({"type": "question", "msg": q["question"], "q_type": q_type, "points": q["points"]})
            debug_log("_start_buzz question 广播完毕")
        debug_log("<<< _start_buzz 释放锁，正常退出")

    def _stop_round(self):
        with self.lock:
            self.round_active = False
            self.start_buzz_btn.config(state=tk.NORMAL) if self.current_question_index >= 0 else None
            self.stop_round_btn.config(state=tk.DISABLED)
            self._update_nav_buttons()
        self.buzz_banner.config(text="⏳ 抢答已结束，准备下一题", bg="#FF9800")
        self._log("🔴 本轮抢答已手动结束")
        self._broadcast({"type": "round_end", "msg": "🔴 本轮抢答已结束"})

    def _reset_scores(self):
        """重置所有选手计分"""
        if not messagebox.askyesno("确认重置", "⚠️ 确定要重置所有选手的分数吗？\n\n此操作不可撤销！"):
            return
        with self.lock:
            for name in self.clients:
                self.clients[name]["score"] = 0
                self._send_to_player_nolock(name, {"type": "score_update", "score": 0, "msg": "🔄 分数已重置"})
        self._update_player_list()
        self._log("🔄 所有选手分数已重置为 0")
        self._broadcast({"type": "system", "msg": "🔄 管理员已重置所有选手分数"})
        self.buzz_banner.config(text="🔄 分数已全部重置，比赛继续", bg="#795548")

    def _restart_game(self):
        """重赛：恢复到比赛刚开始的状态"""
        if not messagebox.askyesno("确认重赛", "⚠️ 确定要重赛吗？\n\n所有分数将清零，已答记录将清空，\n回到比赛初始状态。"):
            return
        # 停止计时器
        self.stop_timer()
        # 重置分数
        with self.lock:
            for name in self.clients:
                self.clients[name]["score"] = 0
                self._send_to_player_nolock(name, {"type": "score_update", "score": 0, "msg": "🔄 重赛，分数已重置"})
                # 重置延长次数
                self.extend_limits[name] = self.extend_max
                self._send_to_player_nolock(name, {"type": "extend_init", "max": self.extend_max, "seconds": self.extend_seconds})
        self._update_player_list()
        # 重置比赛状态
        self.game_over = False
        self.ranked_players = []
        self.used_questions.clear()
        self.round_num = 0
        self.round_active = False
        self.first_buzzer = None
        self.record_tree.delete(*self.record_tree.get_children())
        # 回到题库起始
        if self.active_bank_name and self.active_bank_name in self.question_banks:
            self._activate_bank(self.active_bank_name)
        else:
            self._show_welcome()
        self.start_buzz_btn.config(state=tk.DISABLED)
        self.stop_round_btn.config(state=tk.DISABLED)
        self._update_nav_buttons()
        self._log("🆕 比赛已重赛，所有数据已重置")
        self._broadcast({"type": "restart_game", "msg": "🆕 比赛已重赛，准备开始新一轮"})

    def _end_game(self):
        """结束比赛：展示最终积分榜，关闭后清空数据并返回主页"""
        if not messagebox.askyesno("确认结束", "🏁 确定要结束当前比赛吗？\n\n将展示最终积分榜，之后所有数据将清空并返回主页。"):
            return
        # 先停止本轮
        self.stop_timer()
        self.round_active = False
        self._broadcast({"type": "round_end", "msg": "🔴 比赛已结束"})
        # 展示最终积分榜（用当前分数，尚未清空），关闭时执行清理
        self._show_rankings(final=True, on_close=self._cleanup_after_end_game)

    def _cleanup_after_end_game(self):
        """结束比赛积分榜关闭后的清理工作"""
        self.game_started = False
        self.game_name = ""
        self.game_over = False
        self.first_buzzer = None
        # 清空分数并通知客户端
        with self.lock:
            for name in list(self.clients.keys()):
                self.clients[name]["score"] = 0
                self._send_to_player_nolock(name, {"type": "game_over", "rankings": [], "msg": "🏁 比赛已结束，感谢参与！"})
                self._send_to_player_nolock(name, {"type": "score_update", "score": 0})
        self.ranked_players = []
        self.used_questions.clear()
        self.round_num = 0
        self.record_tree.delete(*self.record_tree.get_children())
        self._log("🏁 比赛已结束，所有数据已清空")
        # 回到题库起始
        if self.active_bank_name and self.active_bank_name in self.question_banks:
            self._activate_bank(self.active_bank_name)
        else:
            self._show_welcome()
        self.start_buzz_btn.config(state=tk.DISABLED)
        self._update_nav_buttons()
        self._switch_to_home()

    def _check_winner(self):
        """检测是否有选手达到获胜积分并锁定排名"""
        if self.game_over:
            return
        if self.win_score <= 0:
            return

        rank_titles = {1: "🥇 第1名", 2: "🥈 第2名", 3: "🥉 第3名"}
        newly_ranked = []  # 本轮新排名的选手

        with self.lock:
            already_ranked_names = [r[0] for r in self.ranked_players]
            # 找还没排名且达到分数的选手
            sorted_players = sorted(
                [(n, d["score"]) for n, d in self.clients.items() if n not in already_ranked_names],
                key=lambda x: x[1], reverse=True
            )
            if not sorted_players:
                return
            top_name, top_score = sorted_players[0]
            if top_score < self.win_score:
                return  # 最高分都未达到

            # 达到分数，锁定排名
            next_rank = len(self.ranked_players) + 1
            self.ranked_players.append((top_name, top_score, next_rank))
            newly_ranked.append((top_name, top_score, next_rank))
            self._log(f"🏆 [{top_name}] 达到 {self.win_score} 分，锁定为第{next_rank}名！")
            self._send_to_player_nolock(top_name, {"type": "rank_locked", "rank": next_rank, "msg": f"🎉 恭喜获得第{next_rank}名！得分: {top_score}"})
            self._broadcast({"type": "system", "msg": f"🏆 [{top_name}] 获得第{next_rank}名！当前得分: {top_score}"})

        # 检查是否已满设定名次
        if len(self.ranked_players) >= self.win_rank_count or len(self.ranked_players) >= len(self.clients):
            self.game_over = True
            self.round_active = False
            self.first_buzzer = None

            # 显示最终排名
            lines = []
            for n, s, r in self.ranked_players:
                lines.append(f"{rank_titles[r]} {n} - {s}分")
            self.buzz_banner.config(text=" | ".join(lines), bg="#9C27B0")
            self._log("🏁 比赛全部结束！最终排名: " + " | ".join(lines))

            # 通知所有客户端
            rankings = [{"name": n, "score": s, "title": rank_titles[r]} for n, s, r in self.ranked_players]
            self._broadcast({"type": "game_over", "rankings": rankings})

            # 禁用主控按钮
            self.start_buzz_btn.config(state=tk.DISABLED)
            self.stop_round_btn.config(state=tk.DISABLED)
            self.next_btn.config(state=tk.DISABLED)
            self.prev_btn.config(state=tk.DISABLED)
            return

        # 仅有人获得排名，但游戏继续
        rank_titles = {1: "🥇 第1名", 2: "🥈 第2名", 3: "🥉 第3名"}
        lines = []
        for n, s, r in self.ranked_players:
            lines.append(f"{rank_titles[r]} {n} - {s}分")
        lines.append("⏳ 比赛继续...")
        self.buzz_banner.config(text=" | ".join(lines), bg="#9C27B0")
        self._broadcast({"type": "rank_update", "rankings": [{"name": n, "score": s, "title": rank_titles[r]} for n, s, r in self.ranked_players]})

        # 为新锁定排名的选手广播提示
        for n, s, r in newly_ranked:
            self._broadcast({"type": "system", "msg": f"🏆 [{n}] 获得第{r}名！当前得分: {s}"})

    def _show_rankings(self, final=False, on_close=None):
        """弹出全屏积分排名窗口
        final=True 时表示比赛已经结束，显示结束标题
        on_close 为关闭窗口后的回调函数
        """
        if not self.clients:
            messagebox.showinfo("提示", "暂无选手数据")
            # 即使没有选手，也要执行回调
            if on_close:
                on_close()
            return

        win = tk.Toplevel(self.root)
        title_text = "🏆 比赛结束 - 最终排名 🏆" if final else "🏆 积分排名榜 🏆"
        win.title(title_text)
        win.attributes("-fullscreen", True)
        win.attributes("-topmost", True)
        win.configure(bg="#1a1a2e")

        # 存储回调
        self._rank_close_callback = on_close

        # 关闭按钮
        close_btn = tk.Button(win, text="✕ 关闭", font=("微软雅黑", 14),
                              bg="#f44336", fg="white", bd=0,
                              command=lambda: self._close_rankings(win))
        close_btn.place(x=20, y=20, width=100, height=40)

        # 标题
        title_lbl = tk.Label(win, text=title_text,
                             font=("微软雅黑", 36, "bold"),
                             bg="#1a1a2e", fg="#FFD700")
        title_lbl.pack(pady=(40, 20))

        # 排名列表
        with self.lock:
            sorted_pl = sorted(self.clients.items(), key=lambda x: x[1]["score"], reverse=True)

        rank_icons = {0: "🥇", 1: "🥈", 2: "🥉"}
        rank_scores = [0, 0, 0]  # 仅用于视觉

        for i, (name, data) in enumerate(sorted_pl):
            icon = rank_icons.get(i, f"  {i+1}")
            # 检查是否已锁定排名
            locked = ""
            for rn, rs, rr in self.ranked_players:
                if rn == name:
                    locked = f" [第{rr}名 ✅]"
                    break

            row_frame = tk.Frame(win, bg="#16213e", highlightbackground="#FFD700",
                                 highlightthickness=1 if i < 3 else 0)
            row_frame.pack(fill=tk.X, padx=80, pady=5)

            # 选手名
            tk.Label(row_frame, text=f"{icon}  {name}",
                     font=("微软雅黑", 28, "bold"),
                     bg="#16213e", fg="white").pack(side=tk.LEFT, padx=30, pady=12)

            # 分数
            score_color = "#4CAF50" if data["score"] >= 0 else "#f44336"
            tk.Label(row_frame, text=f"{data['score']} 分{locked}",
                     font=("微软雅黑", 28, "bold"),
                     bg="#16213e", fg=score_color).pack(side=tk.RIGHT, padx=30, pady=12)

        # 底部
        if final or self.game_over:
            tk.Label(win, text="🏁 比赛已结束",
                     font=("微软雅黑", 20),
                     bg="#1a1a2e", fg="#9E9E9E").pack(pady=20)
        else:
            tk.Label(win, text="⏳ 比赛进行中...",
                     font=("微软雅黑", 20),
                     bg="#1a1a2e", fg="#4CAF50").pack(pady=20)

        # 备份窗口引用以便关闭
        self._rank_window = win

    def _close_rankings(self, win=None):
        w = win or getattr(self, '_rank_window', None)
        cb = getattr(self, '_rank_close_callback', None)
        if w:
            w.destroy()
            self._rank_window = None
            self._rank_close_callback = None
        # 执行回调
        if cb:
            cb()

    def _award_score(self, name):
        """抢答成功后答对给分"""
        pts = self.correct_points
        correct = ""
        if 0 <= self.current_question_index < len(self.questions):
            correct = self.questions[self.current_question_index]["answer"]
        with self.lock:
            if name in self.clients:
                # 已锁定排名的选手不再参与得分
                if any(r[0] == name for r in self.ranked_players):
                    self._log(f"⚠️ [{name}] 已获得排名，跳过加分")
                    return
                self.clients[name]["score"] += pts
                self._log(f"✅ [{name}] 答对 +{pts} 分 → {self.clients[name]['score']}")
                self._send_to_player_nolock(name, {"type": "score_update", "score": self.clients[name]["score"], "msg": f"✅ 答对了！+{pts} 分"})
        self._add_record(self._last_answer, "✅ 正确 ✅", correct)
        self._update_player_list()
        self._reset_judge_buttons()
        self.buzz_banner.config(text=f"💬 [{name}] 答案: {self._last_answer} | 正确答案: {correct}  ✅ [{name}] 答对 +{pts} 分！", bg="#4CAF50")
        # 检测是否有选手达到获胜积分
        self.root.after(200, self._check_winner)

    def _penalty_score(self, name):
        """抢答成功后答错扣分"""
        pts = self.wrong_points
        correct = ""
        if 0 <= self.current_question_index < len(self.questions):
            correct = self.questions[self.current_question_index]["answer"]
        with self.lock:
            if name in self.clients:
                # 已锁定排名的选手不再参与扣分
                if any(r[0] == name for r in self.ranked_players):
                    self._log(f"⚠️ [{name}] 已获得排名，跳过扣分")
                    return
                self.clients[name]["score"] -= pts  # 支持负数
                self._log(f"❌ [{name}] 答错 -{pts} 分 → {self.clients[name]['score']}")
                self._send_to_player_nolock(name, {"type": "score_update", "score": self.clients[name]["score"], "msg": f"❌ 答错了！-{pts} 分"})
        self._add_record(self._last_answer, "❌ 错误 ❌", correct)
        self._update_player_list()
        self._reset_judge_buttons()
        self.buzz_banner.config(text=f"💬 [{name}] 答案: {self._last_answer} | 正确答案: {correct}  ❌ [{name}] 答错 -{pts} 分", bg="#f44336")
        # 检测是否有选手达到获胜积分
        self.root.after(200, self._check_winner)

    def _reset_judge_buttons(self):
        """恢复按钮到默认状态"""
        self.stop_timer()
        self.start_buzz_btn.config(text="开始抢答 🚀", bg="#FF5722", fg="white", width=10, command=self._start_buzz)
        self.stop_round_btn.config(text="结束抢答 ■", bg="#f44336", fg="white", width=10, state=tk.DISABLED, command=self._stop_round)
        self.first_buzzer = None
        # 恢复上一题/下一题按钮
        self._update_nav_buttons()

    def _start_timer(self, name):
        """启动答题倒计时"""
        self.stop_timer()  # 取消之前的计时器
        self._timer_remaining = self.answer_timeout

        def tick():
            self._timer_remaining -= 1
            if self._timer_remaining <= 0:
                # 超时！自动判答错
                self._log(f"⏰ [{name}] 答题超时（{self.answer_timeout}秒）")
                self.buzz_banner.config(text=f"⏰ [{name}] 答题超时！-{self.wrong_points}分", bg="#f44336")
                self._broadcast({"type": "system", "msg": f"⏰ [{name}] 答题超时！"})
                # 扣分
                correct = ""
                if 0 <= self.current_question_index < len(self.questions):
                    correct = self.questions[self.current_question_index]["answer"]
                with self.lock:
                    if name in self.clients:
                        self.clients[name]["score"] -= self.wrong_points
                        self._send_to_player_nolock(name, {"type": "score_update", "score": self.clients[name]["score"], "msg": f"⏰ 答题超时！-{self.wrong_points}分"})
                        self._send_to_player_nolock(name, {"type": "timeout", "msg": f"⏰ 答题超时！"})
                self._add_record("超时", "❌ 超时 ❌", correct)
                self._update_player_list()
                self._reset_judge_buttons()
                self._check_winner()
                return
            # 更新横幅倒计时
            self.buzz_banner.config(text=f"🎉🎉🎉 [{name}] 抢答成功！等待 [{name}] 输入答案 ⏱ {self._timer_remaining}s 🎉🎉🎉")
            self._timer_id = self.root.after(1000, tick)

        self._timer_id = self.root.after(1000, tick)

    def stop_timer(self):
        """取消倒计时"""
        if self._timer_id:
            self.root.after_cancel(self._timer_id)
            self._timer_id = None
            self._timer_remaining = 0

    def _show_settings(self):
        """显示设置窗口"""
        win = tk.Toplevel(self.root)
        win.title("⚙ 设置")
        win.geometry("440x680")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        # 分数设置
        score_frame = tk.LabelFrame(win, text="得分设置", font=("微软雅黑", 10))
        score_frame.pack(fill=tk.X, padx=15, pady=10)

        row1 = tk.Frame(score_frame)
        row1.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(row1, text="答对加分:", font=("微软雅黑", 10)).pack(side=tk.LEFT)
        correct_var = tk.IntVar(value=self.correct_points)
        correct_spin = tk.Spinbox(row1, from_=0, to=999, textvariable=correct_var,
                                   font=("微软雅黑", 10), width=6)
        correct_spin.pack(side=tk.RIGHT)
        tk.Label(row1, text="分", font=("微软雅黑", 10)).pack(side=tk.RIGHT, padx=3)

        row2 = tk.Frame(score_frame)
        row2.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(row2, text="答错扣分:", font=("微软雅黑", 10)).pack(side=tk.LEFT)
        wrong_var = tk.IntVar(value=self.wrong_points)
        wrong_spin = tk.Spinbox(row2, from_=0, to=999, textvariable=wrong_var,
                                 font=("微软雅黑", 10), width=6)
        wrong_spin.pack(side=tk.RIGHT)
        tk.Label(row2, text="分", font=("微软雅黑", 10)).pack(side=tk.RIGHT, padx=3)

        # 超时设置
        timeout_frame = tk.LabelFrame(win, text="答题计时", font=("微软雅黑", 10))
        timeout_frame.pack(fill=tk.X, padx=15, pady=5)

        timeout_row = tk.Frame(timeout_frame)
        timeout_row.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(timeout_row, text="答题倒计时:", font=("微软雅黑", 10)).pack(side=tk.LEFT)
        timeout_var = tk.IntVar(value=self.answer_timeout)
        timeout_spin = tk.Spinbox(timeout_row, from_=5, to=120, textvariable=timeout_var,
                                   font=("微软雅黑", 10), width=6)
        timeout_spin.pack(side=tk.RIGHT)
        tk.Label(timeout_row, text="秒", font=("微软雅黑", 10)).pack(side=tk.RIGHT, padx=3)

        # 获胜积分
        win_frame = tk.LabelFrame(win, text="获胜条件", font=("微软雅黑", 10))
        win_frame.pack(fill=tk.X, padx=15, pady=5)

        win_row = tk.Frame(win_frame)
        win_row.pack(fill=tk.X, padx=10, pady=5)
        win_var = tk.IntVar(value=self.win_score)
        win_spin = tk.Spinbox(win_row, from_=0, to=9999, textvariable=win_var,
                               font=("微软雅黑", 10), width=8)
        win_spin.pack(side=tk.RIGHT)
        tk.Label(win_row, text="分（0=不启用）", font=("微软雅黑", 10)).pack(side=tk.RIGHT, padx=3)
        tk.Label(win_row, text="达到此积分即获胜:", font=("微软雅黑", 10)).pack(side=tk.LEFT)

        rank_row = tk.Frame(win_frame)
        rank_row.pack(fill=tk.X, padx=10, pady=(0, 5))
        rank_var = tk.IntVar(value=self.win_rank_count)
        rank_spin = tk.Spinbox(rank_row, from_=1, to=99, textvariable=rank_var,
                                font=("微软雅黑", 10), width=6)
        rank_spin.pack(side=tk.RIGHT)
        tk.Label(rank_row, text="名（全部选手名额用完后自动结束）", font=("微软雅黑", 10)).pack(side=tk.RIGHT, padx=3)
        tk.Label(rank_row, text="决出前:", font=("微软雅黑", 10)).pack(side=tk.LEFT)

        # 延长回答
        extend_frame = tk.LabelFrame(win, text="延长回答", font=("微软雅黑", 10))
        extend_frame.pack(fill=tk.X, padx=15, pady=5)

        ext_row1 = tk.Frame(extend_frame)
        ext_row1.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(ext_row1, text="每场比赛可延长次数:", font=("微软雅黑", 10)).pack(side=tk.LEFT)
        extend_max_var = tk.IntVar(value=self.extend_max)
        extend_spin = tk.Spinbox(ext_row1, from_=0, to=99, textvariable=extend_max_var,
                                  font=("微软雅黑", 10), width=6)
        extend_spin.pack(side=tk.RIGHT)
        tk.Label(ext_row1, text="次", font=("微软雅黑", 10)).pack(side=tk.RIGHT, padx=3)

        ext_row2 = tk.Frame(extend_frame)
        ext_row2.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(ext_row2, text="每次延长秒数:", font=("微软雅黑", 10)).pack(side=tk.LEFT)
        extend_sec_var = tk.IntVar(value=self.extend_seconds)
        extend_sec_spin = tk.Spinbox(ext_row2, from_=1, to=120, textvariable=extend_sec_var,
                                      font=("微软雅黑", 10), width=6)
        extend_sec_spin.pack(side=tk.RIGHT)
        tk.Label(ext_row2, text="秒", font=("微软雅黑", 10)).pack(side=tk.RIGHT, padx=3)

        # 自动判题
        judge_frame = tk.LabelFrame(win, text="判题模式", font=("微软雅黑", 10))
        judge_frame.pack(fill=tk.X, padx=15, pady=5)

        judge_row = tk.Frame(judge_frame)
        judge_row.pack(fill=tk.X, padx=10, pady=5)
        auto_var = tk.BooleanVar(value=self.auto_judge_var.get())
        tk.Checkbutton(judge_row, text="🤖 自动判题（服务器自动比对答案）",
                       font=("微软雅黑", 10), variable=auto_var).pack(side=tk.LEFT)

        # 题目复用
        reuse_frame = tk.LabelFrame(win, text="题目复用", font=("微软雅黑", 10))
        reuse_frame.pack(fill=tk.X, padx=15, pady=5)

        reuse_row = tk.Frame(reuse_frame)
        reuse_row.pack(fill=tk.X, padx=10, pady=5)
        reuse_var = tk.BooleanVar(value=self.allow_repeat)
        tk.Checkbutton(reuse_row, text="♻️ 题目可重复使用（勾选后已用题目可以再次抢答）",
                       font=("微软雅黑", 10), variable=reuse_var).pack(side=tk.LEFT)

        # 按钮
        btn_row = tk.Frame(win)
        btn_row.pack(fill=tk.X, padx=15, pady=5)

        def save():
            self.correct_points = correct_var.get()
            self.wrong_points = wrong_var.get()
            self.answer_timeout = timeout_var.get()
            self.win_score = win_var.get()
            self.win_rank_count = rank_var.get()
            self.extend_max = extend_max_var.get()
            self.extend_seconds = extend_sec_var.get()
            self.auto_judge_var.set(auto_var.get())
            self.allow_repeat = reuse_var.get()
            if not self.allow_repeat:
                self.used_questions.clear()
            self._log(f"⚙ 设置已更新: 答对+{self.correct_points}分, 答错-{self.wrong_points}分, 倒计时{self.answer_timeout}秒, 获胜积分{'已启用('+str(self.win_score)+'分/前'+str(self.win_rank_count)+'名)' if self.win_score>0 else '未启用'}, 延长回答{self.extend_max}次×{self.extend_seconds}秒, 自动判题={'开启' if self.auto_judge_var.get() else '关闭'}, 题目复用={'允许' if self.allow_repeat else '不允许'}")
            win.destroy()

        tk.Button(btn_row, text="保存", font=("微软雅黑", 10),
                  bg="#4CAF50", fg="white", width=10, command=save).pack(side=tk.RIGHT, padx=2)
        tk.Button(btn_row, text="取消", font=("微软雅黑", 10),
                  bg="#9E9E9E", fg="white", width=10, command=win.destroy).pack(side=tk.RIGHT, padx=2)

    def _send_message_to_all(self):
        msg = self.msg_entry.get().strip()
        if not msg or msg == "发送消息给所有选手...":
            messagebox.showwarning("提示", "请输入要发送的消息")
            return
        self._broadcast({"type": "info", "msg": f"📢 {msg}"})
        self._log(f"发送消息: {msg}")
        self.msg_entry.delete(0, tk.END)

    def _mark_correct(self):
        sel = self.player_tree.selection()
        if not sel:
            return
        name = self.player_tree.item(sel[0], "values")[0]
        pts = 10
        if 0 <= self.current_question_index < len(self.questions):
            pts = self.questions[self.current_question_index]["points"]
        with self.lock:
            if name in self.clients:
                self.clients[name]["score"] += pts
                self._log(f"✅ [{name}] 答对 +{pts} 分 → {self.clients[name]['score']}")
                self._send_to_player_nolock(name, {"type": "score_update", "score": self.clients[name]["score"], "msg": f"✅ 答对了！+{pts} 分"})
        self._update_player_list()

    def _mark_wrong(self):
        sel = self.player_tree.selection()
        if not sel:
            return
        name = self.player_tree.item(sel[0], "values")[0]
        pts = 5
        if 0 <= self.current_question_index < len(self.questions):
            pts = max(1, self.questions[self.current_question_index]["points"] // 2)
        with self.lock:
            if name in self.clients:
                self.clients[name]["score"] = max(0, self.clients[name]["score"] - pts)
                self._log(f"❌ [{name}] 答错 -{pts} 分 → {self.clients[name]['score']}")
                self._send_to_player_nolock(name, {"type": "score_update", "score": self.clients[name]["score"], "msg": f"❌ 答错了 -{pts} 分"})
        self._update_player_list()

    # =============== 网络 ===============

    def _toggle_log(self):
        """切换日志显示"""
        if self.log_frame.winfo_ismapped():
            self.log_frame.pack_forget()
            self.log_btn.config(text="📋 日志")
        else:
            self.log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2, before=self.log_btn)
            self.log_btn.config(text="📋 隐藏日志")

    def _toggle_record(self):
        """切换抢答记录显示"""
        if self.record_frame.winfo_ismapped():
            self.record_frame.pack_forget()
            self.record_btn.config(text="📋 抢答记录")
        else:
            self.record_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5), before=self.record_btn)
            self.record_btn.config(text="📋 隐藏记录")

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)

    def _start_server(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("0.0.0.0", 8888))
            self.server_socket.listen(20)
            self.server_socket.settimeout(1.0)
            self.running = True
            threading.Thread(target=self._accept_clients, daemon=True).start()
            self._log("服务器已启动，等待选手连接...")
        except Exception as e:
            self._log(f"❌ 服务器启动失败: {e}")
            messagebox.showerror("错误", f"服务器启动失败:\n{e}")

    def _accept_clients(self):
        while self.running:
            try:
                c, addr = self.server_socket.accept()
                threading.Thread(target=self._handle_client, args=(c, addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self._log("接受连接出错")
                    debug_log(f"_accept_clients 异常: {e}")

    def _handle_client(self, c, addr):
        debug_log(f"_handle_client 新连接: {addr}")
        # 比赛未开始时拒绝连接
        if not self.game_started:
            c.send(json.dumps({"type": "error", "msg": "⏳ 比赛尚未开始，请等待管理员开启比赛后再连接"}).encode())
            c.close()
            debug_log(f"_handle_client 比赛未开始，拒绝连接: {addr}")
            return
        try:
            data = c.recv(1024).decode("utf-8")
            msg = json.loads(data)
            name = msg.get("name", f"选手{addr[1]}")
            debug_log(f"_handle_client 选手名称: {name}")
            with self.lock:
                if name in self.clients:
                    c.send(json.dumps({"type": "error", "msg": "该名称已被使用"}).encode())
                    c.close()
                    debug_log(f"_handle_client 名称重复: {name}，已拒绝")
                    return
                self.clients[name] = {"socket": c, "address": addr, "score": 0, "banned": False, "connected": True}
                # 选手连接时初始化延长次数（整个比赛期间用尽即止）
                self.extend_limits[name] = self.extend_max
            self._update_player_list()
            self._log(f"✅ 选手 [{name}] 已连接 ({addr[0]})")
            self._send_to_player(name, {"type": "info", "msg": "连接成功！等待管理员开始抢答...", "game_name": self.game_name})
            self._broadcast({"type": "system", "msg": f"选手 [{name}] 加入了比赛"})

            # 设置 socket 超时，以便心跳和断开检测
            c.settimeout(self.heartbeat_interval)

            last_heartbeat = time.time()

            while self.running:
                try:
                    data = c.recv(1024)
                    if not data:
                        debug_log(f"_handle_client [{name}] 收到空数据，断开")
                        break
                    msg = json.loads(data.decode("utf-8"))
                    # 客户端发来的心跳，不做处理，只说明连接还活着
                    if msg.get("type") == "pong":
                        continue
                    self._process_client_msg(name, msg)
                except socket.timeout:
                    # 超时了，检查是否需要发送心跳
                    now = time.time()
                    if now - last_heartbeat >= self.heartbeat_interval:
                        try:
                            c.send(json.dumps({"type": "ping"}).encode())
                            last_heartbeat = now
                        except:
                            debug_log(f"_handle_client [{name}] 发送心跳失败")
                            break
                    continue
                except (json.JSONDecodeError, ConnectionResetError, ConnectionAbortedError, OSError) as e:
                    debug_log(f"_handle_client [{name}] 网络异常: {e}")
                    break
                except Exception as e:
                    debug_log(f"_handle_client [{name}] 未知异常: {e}")
                    break
        except Exception as e:
            debug_log(f"_handle_client [{name}] 初始化异常: {e}")
            pass
        finally:
            debug_log(f"_handle_client [{name}] 即将移除")
            self._remove_client(name)

    def _process_client_msg(self, name, msg):
        msg_type = msg.get("type")
        debug_log(f"_process_client_msg: [{name}] type={msg_type}")
        if msg_type == "buzz":
            debug_log(f"_process_client_msg: [{name}] 尝试抢答，准备抢锁")
            with self.lock:
                debug_log(f"_process_client_msg: [{name}] 拿到锁")
                if name not in self.clients:
                    debug_log(f"_process_client_msg: [{name}] 不在 clients 中，退出")
                    return
                p = self.clients[name]
                if p["banned"]:
                    debug_log(f"_process_client_msg: [{name}] 已被禁赛")
                    self._send_to_player_nolock(name, {"type": "error", "msg": "你已被禁赛"})
                    return
                if self.game_over:
                    debug_log(f"_process_client_msg: [{name}] 比赛已结束")
                    self._send_to_player_nolock(name, {"type": "error", "msg": "比赛已结束"})
                    return
                if not self.round_active:
                    debug_log(f"_process_client_msg: [{name}] 本轮未激活")
                    self._send_to_player_nolock(name, {"type": "error", "msg": "本轮尚未开始"})
                    return
                if self.first_buzzer is None:
                    debug_log(f"_process_client_msg: [{name}] 抢答成功！first_buzzer 设为 {name}")
                    self.first_buzzer = name
                    self._log(f"🔔 [{name}] 抢答成功！")
                    self.buzz_banner.config(text=f"🎉🎉🎉 [{name}] 抢答成功！等待 [{name}] 输入答案 ⏱ {self.answer_timeout}s 🎉🎉🎉", bg="#4CAF50")
                    # 抢答者收到成功，并进入答案输入模式；其他人收到已有人抢到
                    q_text = self.questions[self.current_question_index]["question"]
                    q_type = self.questions[self.current_question_index].get("type", "")
                    self._send_to_player_nolock(name, {"type": "buzz_result", "winner": True, "msg": "🎉 你抢答成功了！请在此输入你的答案：", "timeout": self.answer_timeout, "extend_remaining": self.extend_limits.get(name, 0), "extend_seconds": self.extend_seconds, "question": q_text, "q_type": q_type})
                    for other in list(self.clients.keys()):
                        if other != name:
                            self._send_to_player_nolock(other, {"type": "buzz_result", "winner": False, "msg": f"😅 [{name}] 抢先一步！"})
                    self.round_active = False
                    self.start_buzz_btn.config(state=tk.DISABLED)
                    self.stop_round_btn.config(state=tk.DISABLED)
                    # 显示参考答案供主持人对比
                    q = self.questions[self.current_question_index]
                    self.answer_label.config(text=q["answer"], fg="#1565C0")
                    self.answer_visible = True
                    self.show_answer_btn.config(text="隐藏答案 🙈")
                    self._log(f"📋 参考答案: {q['answer']}")
                    # 启动倒计时
                    self._start_timer(name)
                else:
                    self._send_to_player_nolock(name, {"type": "error", "msg": "已有选手抢答成功"})
        elif msg_type == "answer":
            # 选手提交了答案
            player_answer = msg.get("answer", "")
            self._last_answer = player_answer
            self.stop_timer()  # 取消倒计时
            debug_log(f"_process_client_msg: [{name}] 提交答案: {player_answer}")

            # 如果开启了自动判题，直接比对
            if self.auto_judge_var.get():
                correct = ""
                if 0 <= self.current_question_index < len(self.questions):
                    correct = self.questions[self.current_question_index]["answer"].strip().upper()
                is_correct = player_answer.strip().upper() == correct
                if is_correct:
                    self._log(f"🤖 自动判题: [{name}] 答案 {player_answer} ✅ 正确")
                    self._award_score(name)
                else:
                    self._log(f"🤖 自动判题: [{name}] 答案 {player_answer} ❌ 错误（正确答案: {correct}）")
                    self._penalty_score(name)
                self._broadcast({"type": "system", "msg": f"🤖 {name} 的答案 {'✅ 正确' if is_correct else '❌ 错误'}"})
                return

            self.buzz_banner.config(text=f"💬 [{name}] 的答案: {player_answer}", bg="#2196F3")
            self._log(f"💬 [{name}] 提交答案: {player_answer}")
            self._broadcast({"type": "system", "msg": f"💬 [{name}] 已提交答案，等待主持人判定..."})
            # 恢复按钮让主持人可以判定
            self.start_buzz_btn.config(state=tk.NORMAL, text="✅ 答对给分")
            self.start_buzz_btn.config(bg="#4CAF50", command=lambda: self._award_score(name))
            self.stop_round_btn.config(state=tk.NORMAL, text="❌ 答错扣分")
            self.stop_round_btn.config(bg="#f44336", command=lambda: self._penalty_score(name))
            self._send_to_player_nolock(name, {"type": "answer_received", "msg": "答案已提交，等待主持人判定"})

        elif msg_type == "extend_time":
            # 选手请求延长答题时间
            with self.lock:
                remaining = self.extend_limits.get(name, 0)
                if remaining <= 0:
                    self._send_to_player_nolock(name, {"type": "extend_result", "success": False, "msg": "延长次数已用完"})
                    return
                if self._timer_id is None or self._timer_remaining <= 0:
                    self._send_to_player_nolock(name, {"type": "extend_result", "success": False, "msg": "当前不在答题计时中"})
                    return
                # 扣减次数，延长计时
                self.extend_limits[name] = remaining - 1
                self._timer_remaining += self.extend_seconds
                self._log(f"⏱ [{name}] 使用延长，剩余{remaining-1}次，当前剩余{self._timer_remaining}秒")
                self.buzz_banner.config(text=f"🎉🎉🎉 [{name}] 抢答成功！等待 [{name}] 输入答案 ⏱ {self._timer_remaining}s 🎉🎉🎉")
                self._send_to_player_nolock(name, {"type": "extend_result", "success": True, "msg": f"⏱ 计时已延长{self.extend_seconds}秒，剩余{remaining-1}次", "remaining": remaining - 1, "time_remaining": self._timer_remaining})

    def _remove_client(self, name):
        debug_log(f"_remove_client: [{name}] 准备抢锁")
        with self.lock:
            debug_log(f"_remove_client: [{name}] 拿到锁")
            if name in self.clients:
                del self.clients[name]
                debug_log(f"_remove_client: [{name}] 已从 clients 移除")
            if name in self.extend_limits:
                del self.extend_limits[name]
        self._update_player_list()
        self._log(f"❌ 选手 [{name}] 已断开")
        self._broadcast({"type": "system", "msg": f"选手 [{name}] 离开了比赛"})

    def _send_to_player(self, name, msg):
        with self.lock:
            if name in self.clients:
                try:
                    self.clients[name]["socket"].send(json.dumps(msg).encode())
                except:
                    pass

    def _send_to_player_nolock(self, name, msg):
        """无锁版本，用于调用方已持有锁的场景"""
        if name in self.clients:
            try:
                self.clients[name]["socket"].send(json.dumps(msg).encode())
            except:
                pass

    def _broadcast(self, msg):
        msg_type = msg.get("type", "unknown")
        debug_log(f"_broadcast 开始: type={msg_type}, clients_count={len(self.clients)}")
        for n, i in self.clients.items():
            try:
                i["socket"].send(json.dumps(msg).encode())
                debug_log(f"_broadcast 已发送给 [{n}]")
            except Exception as e:
                debug_log(f"_broadcast 发送给 [{n}] 失败: {e}")
                # 不在这里移除客户端，让心跳机制处理断开
        debug_log(f"_broadcast 结束: type={msg_type}")

    def _update_player_list(self):
        def upd():
            for item in self.player_tree.get_children():
                self.player_tree.delete(item)
            with self.lock:
                for n, i in sorted(self.clients.items(), key=lambda x: x[1]["score"], reverse=True):
                    s = "🟢 正常" if not i["banned"] else "🔴 禁赛"
                    if not i["connected"]:
                        s = "⚫ 离线"
                    self.player_tree.insert("", tk.END, values=(n, i["score"], s))
        self.root.after(0, upd)

    def _change_score(self, delta):
        sel = self.player_tree.selection()
        if not sel:
            return
        name = self.player_tree.item(sel[0], "values")[0]
        with self.lock:
            if name in self.clients:
                self.clients[name]["score"] += delta
                self._log(f"💰 [{name}] {delta:+d} → {self.clients[name]['score']}")
                self._send_to_player_nolock(name, {"type": "score_update", "score": self.clients[name]["score"]})
        self._update_player_list()

    def _set_score(self):
        """手动设置选手分数"""
        sel = self.player_tree.selection()
        if not sel:
            return
        name = self.player_tree.item(sel[0], "values")[0]
        cur_score = 0
        with self.lock:
            if name in self.clients:
                cur_score = self.clients[name]["score"]
        dialog = tk.Toplevel(self.root)
        dialog.title(f"设置分数 - {name}")
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        tk.Label(dialog, text=f"选手: {name}", font=("微软雅黑", 12, "bold")).pack(pady=(15, 5))
        tk.Label(dialog, text=f"当前分数: {cur_score}", font=("微软雅黑", 10)).pack()
        var = tk.IntVar(value=cur_score)
        row = tk.Frame(dialog)
        row.pack(pady=10)
        tk.Label(row, text="设置分数:", font=("微软雅黑", 10)).pack(side=tk.LEFT)
        spin = tk.Spinbox(row, from_=-999, to=9999, textvariable=var,
                          font=("微软雅黑", 12, "bold"), width=8)
        spin.pack(side=tk.LEFT, padx=5)
        def do_set():
            with self.lock:
                if name in self.clients:
                    self.clients[name]["score"] = var.get()
                    self._log(f"🎯 [{name}] 分数设置为 {var.get()}")
                    self._send_to_player_nolock(name, {"type": "score_update", "score": var.get()})
            self._update_player_list()
            dialog.destroy()
        btn_row = tk.Frame(dialog)
        btn_row.pack(pady=5)
        tk.Button(btn_row, text="确定", font=("微软雅黑", 10),
                  bg="#4CAF50", fg="white", width=8, command=do_set).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_row, text="取消", font=("微软雅黑", 10),
                  bg="#9E9E9E", fg="white", width=8, command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _foul_penalty(self):
        """违规扣5分"""
        sel = self.player_tree.selection()
        if not sel:
            return
        name = self.player_tree.item(sel[0], "values")[0]
        if not messagebox.askyesno("违规扣分", f"确定要对 [{name}] 进行违规扣分（-5分）吗？"):
            return
        with self.lock:
            if name in self.clients:
                self.clients[name]["score"] -= 5
                self._log(f"🚫 [{name}] 违规扣5分 → {self.clients[name]['score']}")
                self._send_to_player_nolock(name, {"type": "score_update", "score": self.clients[name]["score"], "msg": "🚫 违规扣5分"})
        self._broadcast({"type": "system", "msg": f"🚫 [{name}] 违规，扣除5分"})
        self._update_player_list()

    def _toggle_ban(self):
        sel = self.player_tree.selection()
        if not sel:
            return
        name = self.player_tree.item(sel[0], "values")[0]
        with self.lock:
            if name in self.clients:
                self.clients[name]["banned"] = not self.clients[name]["banned"]
                st = "禁赛" if self.clients[name]["banned"] else "恢复"
                self._log(f"🚫 [{name}] 已被{st}")
                self._send_to_player_nolock(name, {"type": "ban_status", "banned": self.clients[name]["banned"]})
        self._update_player_list()

    def _disconnect_player(self):
        sel = self.player_tree.selection()
        if not sel:
            return
        name = self.player_tree.item(sel[0], "values")[0]
        with self.lock:
            if name in self.clients:
                try:
                    self.clients[name]["socket"].close()
                except:
                    pass
                del self.clients[name]
                self._log(f"🔌 已断开 [{name}]")
        self._update_player_list()

    def _show_popup(self, e):
        item = self.player_tree.identify_row(e.y)
        if item:
            self.player_tree.selection_set(item)
            self.popup_menu.post(e.x_root, e.y_root)

    def _export_scores(self):
        desktop = os.path.expanduser("~/Desktop")
        path = os.path.join(desktop, f"抢答成绩_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("=" * 50 + "\n")
            f.write(f"             抢 答 成 绩 单\n")
            f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
            if self.questions and self.question_file_path:
                f.write(f"题库: {os.path.basename(self.question_file_path)} ({len(self.questions)} 题)\n")
                f.write(f"已完成轮次: {self.round_num}\n\n")
            f.write("─" * 30 + "\n  选手排名\n" + "─" * 30 + "\n")
            with self.lock:
                for r, (n, i) in enumerate(sorted(self.clients.items(), key=lambda x: x[1]["score"], reverse=True), 1):
                    b = " 🚫" if i["banned"] else ""
                    f.write(f"  {r}. {n} — {i['score']} 分{b}\n")
            f.write("\n" + "=" * 50 + "\n")
        self._log(f"📄 成绩已导出: {path}")
        messagebox.showinfo("导出成功", f"成绩已保存到:\n{path}")

    def _show_format_help(self):
        messagebox.showinfo("题库格式说明", """📖 题库格式说明

支持 TXT / CSV / JSON / XLSX 四种格式

── TXT 格式（推荐）──
每行一题，支持：

  纯题目:
    中国的首都是哪里？

  题目|答案:
    中国的首都是哪里？|北京

  题目|答案|分值:
    中国的首都是哪里？|北京|20

  题目（答案）:
    中国的首都是哪里？（北京）

── CSV 格式（Excel编辑）──
  题目,答案,分值
  中国的首都是哪里？,北京,20

── JSON 格式 ──
  [{"question":"...","answer":"...","points":10}]

── XLSX 格式（直接导入 Excel）──
自动识别表头列名：
  题目 / 问题 / question
  答案 / answer
  分值 / points
  选项 / options（自动追加到题目后）
  题型 / type（自动追加到题目前）

📌 答案和分值可选，默认 10 分
📌 XLSX 需要安装 openpyxl：pip install openpyxl""")

    def _show_about(self):
        messagebox.showinfo("关于", """🚀 抢答软件 v2.0

功能：
- 📂 题库导入（TXT/CSV/JSON）
- 🎯 多人抢答
- 💯 自动计分
- 🚫 禁赛管理
- 📄 成绩导出

技术栈：Python + Tkinter + TCP""")

    def _on_close(self):
        if messagebox.askokcancel("退出", "确定要退出吗？所有选手将被断开。"):
            self._save_banks()
            self.running = False
            self._broadcast({"type": "shutdown", "msg": "服务器已关闭"})
            with self.lock:
                for i in self.clients.values():
                    try:
                        i["socket"].close()
                    except:
                        pass
            if self.server_socket:
                self.server_socket.close()
            self.root.destroy()


def main():
    root = tk.Tk()
    app = QuizServer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
