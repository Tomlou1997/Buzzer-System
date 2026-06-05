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

        self.questions = []
        self.current_question_index = -1
        self.question_file_path = ""

        self.host_ip = self._get_local_ip()
        self.heartbeat_interval = 5  # 心跳间隔（秒）
        self._build_ui()
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

        top_frame = tk.Frame(self.root, height=100)
        top_frame.pack(fill=tk.X, padx=8, pady=4)

        mid_frame = tk.Frame(self.root)
        mid_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        bottom_frame = tk.Frame(self.root, height=150)
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

        self.next_round_btn = tk.Button(
            ctrl_frame, text="下一题 ▶", font=("微软雅黑", 10),
            bg="#4CAF50", fg="white", width=10, command=self._start_round
        )
        self.next_round_btn.pack(side=tk.LEFT, padx=2)

        self.stop_round_btn = tk.Button(
            ctrl_frame, text="结束本轮 ■", font=("微软雅黑", 10),
            bg="#f44336", fg="white", width=10, state=tk.DISABLED, command=self._stop_round
        )
        self.stop_round_btn.pack(side=tk.LEFT, padx=2)

        self.import_btn = tk.Button(
            ctrl_frame, text="📂 导入题库", font=("微软雅黑", 9),
            bg="#FF9800", fg="white", width=10, command=self._import_questions
        )
        self.import_btn.pack(side=tk.LEFT, padx=2)

        # === 中部左：题库 ===
        question_frame = tk.LabelFrame(mid_frame, text="📖 题库", font=("微软雅黑", 10))
        question_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))

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

        list_frame = tk.Frame(question_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        tk.Label(list_frame, text="题目列表:", font=("微软雅黑", 9)).pack(anchor=tk.W)
        list_scroll = tk.Frame(list_frame)
        list_scroll.pack(fill=tk.BOTH, expand=True)
        self.question_listbox = tk.Listbox(
            list_scroll, font=("微软雅黑", 9), height=6,
            selectmode=tk.SINGLE, activestyle="none"
        )
        self.question_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.question_listbox.bind("<<ListboxSelect>>", self._on_question_select)
        q_vsb = tk.Scrollbar(list_scroll, orient="vertical", command=self.question_listbox.yview)
        self.question_listbox.configure(yscrollcommand=q_vsb.set)
        q_vsb.pack(side=tk.RIGHT, fill=tk.Y)

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

        # === 底部：日志 ===
        log_frame = tk.LabelFrame(bottom_frame, text="系统日志", font=("微软雅黑", 10))
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_area = scrolledtext.ScrolledText(
            log_frame, height=5, font=("微软雅黑", 9),
            bg="#1e1e1e", fg="#d4d4d4", state=tk.DISABLED
        )
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._log(f"🚀 主控端 v2.0 启动，服务器 IP: {self.host_ip}")

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

            self.questions = questions
            self.current_question_index = -1
            self.question_file_path = file_path
            self._update_question_list()
            self._show_question(-1)
            self._update_progress()
            self.status_label.config(
                text=f"IP: {self.host_ip} | 端口: 8888 | 题库: {os.path.basename(file_path)} ({len(questions)} 题)"
            )
            self._log(f"📚 成功导入题库: {os.path.basename(file_path)} — 共 {len(questions)} 题")
            if questions:
                self.question_listbox.selection_set(0)
        except Exception as e:
            messagebox.showerror("导入失败", f"读取文件出错:\n{e}")

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
                "points": points
            })

        return questions

    def _update_question_list(self):
        self.question_listbox.delete(0, tk.END)
        for i, q in enumerate(self.questions):
            text = q["question"][:30] + ("..." if len(q["question"]) > 30 else "")
            self.question_listbox.insert(tk.END, f"{i+1}. {text}")

    def _update_progress(self):
        total = len(self.questions)
        current = self.current_question_index + 1 if self.current_question_index >= 0 else 0
        self.progress_label.config(text=f"进度: {current} / {total}")
        if 0 <= self.current_question_index < len(self.questions):
            pts = self.questions[self.current_question_index]["points"]
            self.points_label.config(text=f"分值: {pts} 分")
        else:
            self.points_label.config(text="分值: --")

    def _show_question(self, index):
        self.current_question_index = index
        self.answer_visible = False
        self.show_answer_btn.config(text="显示答案 👁")
        self.question_display.config(state=tk.NORMAL)
        self.question_display.delete("1.0", tk.END)
        if 0 <= index < len(self.questions):
            q = self.questions[index]
            self.question_display.insert(tk.END, f"第 {index+1} 题（{q['points']} 分）\n\n")
            self.question_display.insert(tk.END, q["question"])
            self.answer_label.config(text='(点击"显示答案"查看)')
        else:
            self.question_display.insert(tk.END, "请导入题库或点击题目列表中的题目查看")
            self.answer_label.config(text="--")
        self.question_display.config(state=tk.DISABLED)
        self._update_progress()

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

    def _on_question_select(self, event):
        selection = self.question_listbox.curselection()
        if selection:
            self._show_question(selection[0])

    def _start_round(self):
        # 先检查选手，不加锁，避免弹窗卡住
        if not self.clients:
            self._log("⚠️ 目前没有选手连接，题目已准备好，选手连上后即可开始")
            # 如果选中了题目，还是显示到日志里
            if 0 <= self.current_question_index < len(self.questions):
                q = self.questions[self.current_question_index]
                self._log(f"📋 准备就绪: 第 {self.current_question_index+1} 题（{q['points']} 分）")
            return

        with self.lock:

            if self.current_question_index < 0 or self.current_question_index >= len(self.questions):
                msg = self.msg_entry.get().strip()
                if not msg or msg == "发送消息给所有选手...":
                    self._log("⚠️ 请在左侧题库中选择一道题，或在消息框中输入题目")
                    return
                self.round_num += 1
                self.round_active = True
                self.first_buzzer = None
                self.next_round_btn.config(state=tk.DISABLED)
                self.stop_round_btn.config(state=tk.NORMAL)
                self._log(f"🟢 === 第 {self.round_num} 轮抢答开始（手动）===")
                self._broadcast({"type": "round_start", "round": self.round_num, "msg": f"🟢 第 {self.round_num} 轮抢答开始！按 空格键 或 回车键 抢答！"})
                self._broadcast({"type": "question", "msg": f"📝 题目: {msg}"})
                return

            q = self.questions[self.current_question_index]
            self.round_num += 1
            self.round_active = True
            self.first_buzzer = None
            self.next_round_btn.config(state=tk.DISABLED)
            self.stop_round_btn.config(state=tk.NORMAL)

            if self.question_listbox.size() > 0:
                self.question_listbox.itemconfig(self.current_question_index, bg="#E8F5E9")

            self._log(f"🟢 === 第 {self.round_num} 轮: 第 {self.current_question_index+1} 题（{q['points']} 分）===")
            self._broadcast({"type": "round_start", "round": self.round_num, "msg": f"🟢 第 {self.round_num} 轮抢答开始！按 空格键 或 回车键 抢答！"})
            self._broadcast({"type": "question", "msg": f"📝 第 {self.current_question_index+1} 题（{q['points']} 分）: {q['question']}"})

    def _stop_round(self):
        with self.lock:
            self.round_active = False
            self.next_round_btn.config(state=tk.NORMAL)
            self.stop_round_btn.config(state=tk.DISABLED)
        self._log("🔴 本轮抢答已手动结束")
        self._broadcast({"type": "round_end", "msg": "🔴 本轮抢答已结束"})

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
                self._send_to_player(name, {"type": "score_update", "score": self.clients[name]["score"], "msg": f"✅ 答对了！+{pts} 分"})
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
                self._send_to_player(name, {"type": "score_update", "score": self.clients[name]["score"], "msg": f"❌ 答错了 -{pts} 分"})
        self._update_player_list()

    # =============== 网络 ===============

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
            except:
                if self.running:
                    self._log("接受连接出错")

    def _handle_client(self, c, addr):
        try:
            data = c.recv(1024).decode("utf-8")
            msg = json.loads(data)
            name = msg.get("name", f"选手{addr[1]}")
            with self.lock:
                if name in self.clients:
                    c.send(json.dumps({"type": "error", "msg": "该名称已被使用"}).encode())
                    c.close()
                    return
                self.clients[name] = {"socket": c, "address": addr, "score": 0, "banned": False, "connected": True}
            self._update_player_list()
            self._log(f"✅ 选手 [{name}] 已连接 ({addr[0]})")
            self._send_to_player(name, {"type": "info", "msg": "连接成功！等待管理员开始抢答..."})
            self._broadcast({"type": "system", "msg": f"选手 [{name}] 加入了比赛"})

            # 设置 socket 超时，以便心跳和断开检测
            c.settimeout(self.heartbeat_interval)

            last_heartbeat = time.time()

            while self.running:
                try:
                    data = c.recv(1024)
                    if not data:
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
                            break
                    continue
                except (json.JSONDecodeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    break
                except:
                    break
        except:
            pass
        finally:
            self._remove_client(name)

    def _process_client_msg(self, name, msg):
        if msg.get("type") == "buzz":
            with self.lock:
                if name not in self.clients:
                    return
                p = self.clients[name]
                if p["banned"]:
                    self._send_to_player(name, {"type": "error", "msg": "你已被禁赛"})
                    return
                if not self.round_active:
                    self._send_to_player(name, {"type": "error", "msg": "本轮尚未开始"})
                    return
                if self.first_buzzer is None:
                    self.first_buzzer = name
                    self._log(f"🔔 [{name}] 抢答成功！")
                    self._broadcast({"type": "buzz_result", "winner": name, "msg": f"🎉 {name} 抢答成功！"})
                    self.round_active = False
                    self.next_round_btn.config(state=tk.NORMAL)
                    self.stop_round_btn.config(state=tk.DISABLED)
                else:
                    self._send_to_player(name, {"type": "error", "msg": "已有选手抢答成功"})

    def _remove_client(self, name):
        with self.lock:
            if name in self.clients:
                del self.clients[name]
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

    def _broadcast(self, msg):
        with self.lock:
            disc = []
            for n, i in self.clients.items():
                try:
                    i["socket"].send(json.dumps(msg).encode())
                except:
                    disc.append(n)
            for n in disc:
                if n in self.clients:
                    del self.clients[n]

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
                self._send_to_player(name, {"type": "score_update", "score": self.clients[name]["score"]})
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
                self._send_to_player(name, {"type": "ban_status", "banned": self.clients[name]["banned"]})
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
