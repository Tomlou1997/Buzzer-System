"""
抢答软件 - 客户端 v2.0
选手在此连接服务器、抢答、查看信息
"""

import tkinter as tk
from tkinter import ttk, messagebox
import socket
import json
import threading
import time


class QuizClient:
    OPTIONS = ["A", "B", "C", "D", "E", "F"]

    def __init__(self, root):
        self.root = root
        self.root.title("抢答软件 - 客户端 v2.0")
        self.root.geometry("650x720")
        self.root.resizable(True, True)
        self.root.minsize(550, 620)

        # 全屏状态
        self.fullscreen = False

        # 网络相关
        self.socket = None
        self.connected = False
        self.player_name = ""
        self.buzzed = False  # 本轮是否已抢答
        self.answering = False  # 是否在答案选择模式
        self.game_over = False  # 比赛是否已结束
        self._client_timer_id = None
        self._client_timer_label = None
        self._client_timer_hint = None
        self._client_timer_remaining = 0
        self.extend_remaining = 0   # 本轮可求助啦啦队次数
        self.extend_seconds = 15    # 每次求助增加秒数
        self.extend_btn = None     # 求助啦啦队按钮

        # 答案选择状态
        self.selected_options = {}  # {"A": tk.BooleanVar, ...}

        # 设置界面
        self._build_ui()

        # 绑定键盘事件
        self.root.bind_all("<Key-space>", self._on_buzz_key)  # 空格
        self.root.bind_all("<Key-Return>", self._on_key_return)  # 回车
        self.root.bind("<Escape>", self._toggle_fullscreen)
        self.root.bind("<F11>", self._toggle_fullscreen)

        self._log("程序已启动，请输入名称和服务器IP后连接")

    def _build_ui(self):
        """构建界面"""
        # ====== 顶部：连接区 ======
        conn_frame = tk.LabelFrame(self.root, text="连接设置", font=("微软雅黑", 10))
        conn_frame.pack(fill=tk.X, padx=10, pady=5)

        # IP
        ip_frame = tk.Frame(conn_frame)
        ip_frame.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(ip_frame, text="服务器IP:", font=("微软雅黑", 9), width=8).pack(side=tk.LEFT)
        self.ip_var = tk.StringVar(value="10.8.51.7")
        self.ip_entry = tk.Entry(ip_frame, textvariable=self.ip_var, font=("微软雅黑", 9), width=15)
        self.ip_entry.pack(side=tk.LEFT, padx=5)
        tk.Label(ip_frame, text="端口: 8888", font=("微软雅黑", 9), fg="gray").pack(side=tk.LEFT, padx=5)

        # 选手名
        name_frame = tk.Frame(conn_frame)
        name_frame.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(name_frame, text="选手名:", font=("微软雅黑", 9), width=8).pack(side=tk.LEFT)
        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(name_frame, textvariable=self.name_var, font=("微软雅黑", 9), width=15)
        self.name_entry.pack(side=tk.LEFT, padx=5)
        self.name_entry.focus()

        # 连接按钮
        btn_frame = tk.Frame(conn_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        self.connect_btn = tk.Button(
            btn_frame, text="连接服务器",
            font=("微软雅黑", 9), bg="#4CAF50", fg="white",
            width=12, command=self._connect
        )
        self.connect_btn.pack(side=tk.LEFT, padx=2)

        self.status_label = tk.Label(
            btn_frame, text="🔴 未连接",
            font=("微软雅黑", 9), fg="red"
        )
        self.status_label.pack(side=tk.LEFT, padx=10)

        # 全屏按钮
        self.fs_btn = tk.Button(
            btn_frame, text="⛶ 全屏",
            font=("微软雅黑", 9),
            command=self._toggle_fullscreen
        )
        self.fs_btn.pack(side=tk.RIGHT, padx=2)

        # 日志按钮
        self.log_btn = tk.Button(
            btn_frame, text="📋 日志",
            font=("微软雅黑", 9),
            command=self._toggle_log
        )
        self.log_btn.pack(side=tk.RIGHT, padx=2)

        # ====== 主区域：抢答按钮（默认显示） ======
        self.buzz_frame = tk.Frame(self.root)
        self.buzz_frame.pack(fill=tk.X, padx=10, pady=10)

        self.buzz_btn = tk.Button(
            self.buzz_frame,
            text="🔒 未连接服务器\n请先填写信息并连接",
            font=("微软雅黑", 14, "bold"),
            bg="#9E9E9E", fg="white",
            height=3,
            state=tk.DISABLED,
            command=self._buzz
        )
        self.buzz_btn.pack(fill=tk.BOTH, expand=True)

        # 抢答操作提示
        self.hint_label = tk.Label(
            self.root,
            text="💡 抢答操作：按 空格键(Space) 或 回车键(Enter)",
            font=("微软雅黑", 9),
            fg="#FF5722"
        )
        self.hint_label.pack(fill=tk.X, padx=10, pady=(0, 5))

        # ====== 题目展示区 ======
        self.question_frame = tk.LabelFrame(self.root, text="📝 题目", font=("微软雅黑", 11, "bold"), fg="#FF9800")
        self.question_text = tk.Text(
            self.question_frame,
            font=("微软雅黑", 12),
            bg="#FFF8E1",
            fg="#333",
            wrap=tk.WORD,
            height=5,
            state=tk.DISABLED
        )
        self.question_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        # 默认不显示，抢答成功后才显示

        # ====== 答案选择区（默认隐藏，抢到答后显示） ======
        self.answer_frame = tk.LabelFrame(self.root, text="✏️ 请选择答案", font=("微软雅黑", 11, "bold"), fg="#4CAF50")

        # 选项按钮（两行三列）
        opt_grid = tk.Frame(self.answer_frame)
        opt_grid.pack(pady=10)

        opt_labels = [
            ("A", "#FF5722"), ("B", "#2196F3"), ("C", "#4CAF50"),
            ("D", "#9C27B0"), ("E", "#FF9800"), ("F", "#607D8B")
        ]

        self.option_vars = {}
        self.option_btns = {}

        for i, (label, color) in enumerate(opt_labels):
            var = tk.BooleanVar()
            self.option_vars[label] = var
            btn = tk.Checkbutton(
                opt_grid, text=f"  {label}  ",
                font=("微软雅黑", 14, "bold"),
                variable=var,
                fg=color,
                width=4,
                indicatoron=False,
                selectcolor="#E8F5E9"
            )
            btn.grid(row=i // 3, column=i % 3, padx=8, pady=5)
            self.option_btns[label] = btn

        # 提交按钮行
        submit_row = tk.Frame(self.answer_frame)
        submit_row.pack(fill=tk.X, pady=(5, 10))

        tk.Label(submit_row, text="可多选，点击选项后提交", font=("微软雅黑", 9), fg="#666").pack(side=tk.LEFT, padx=10)

        self.submit_answer_btn = tk.Button(
            submit_row, text="提交答案 📤",
            font=("微软雅黑", 11, "bold"),
            bg="#2196F3", fg="white", state=tk.DISABLED,
            command=self._submit_answer
        )
        self.submit_answer_btn.pack(side=tk.RIGHT, padx=10)

        # ====== 底部：信息显示（默认隐藏，点击日志按钮弹出） ======
        self.info_frame = tk.LabelFrame(self.root, text="📋 日志", font=("微软雅黑", 10))
        # 初始不 pack，通过日志按钮控制

        self.info_text = tk.Text(
            self.info_frame,
            font=("微软雅黑", 10),
            bg="#1e1e1e", fg="#d4d4d4",
            state=tk.DISABLED,
            wrap=tk.WORD,
            height=6
        )
        self.info_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 分数显示（默认隐藏，连接成功后显示）
        self.score_frame = tk.Frame(self.root)

        tk.Label(self.score_frame, text="当前分数:", font=("微软雅黑", 10)).pack(side=tk.LEFT)
        self.score_label = tk.Label(
            self.score_frame, text="0", font=("微软雅黑", 14, "bold"),
            fg="#4CAF50"
        )
        self.score_label.pack(side=tk.LEFT, padx=5)

        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _toggle_fullscreen(self, event=None):
        """切换全屏模式"""
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)
        if self.fullscreen:
            self.fs_btn.config(text="⛶ 退出全屏")
        else:
            self.fs_btn.config(text="⛶ 全屏")

    def _toggle_log(self):
        """切换日志显示"""
        if self.info_frame.winfo_ismapped():
            self.info_frame.pack_forget()
            self.log_btn.config(text="📋 日志")
        else:
            # 在分数区域之前插入
            self.info_frame.pack(fill=tk.X, padx=10, pady=5, before=self.score_frame)
            self.log_btn.config(text="📋 隐藏日志")

    def _log(self, msg):
        """添加日志到信息区"""
        if hasattr(self, 'info_text') and self.info_text:
            self.info_text.config(state=tk.NORMAL)
            self.info_text.insert(tk.END, f"> {msg}\n")
            self.info_text.see(tk.END)
            self.info_text.config(state=tk.DISABLED)

    def _show_answer_mode(self, question_text=""):
        """切换到答案选择模式，显示题目"""
        self.answering = True
        self.buzz_frame.pack_forget()
        self.hint_label.pack_forget()
        # 显示题目（放在分数区之前）
        if question_text:
            self.question_frame.pack(fill=tk.X, padx=10, pady=(5, 0), before=self.score_frame)
            self.question_text.config(state=tk.NORMAL)
            self.question_text.delete(1.0, tk.END)
            self.question_text.insert(tk.END, question_text)
            self.question_text.config(state=tk.DISABLED)
        # 重置所有选项为可用和未选中
        for var in self.option_vars.values():
            var.set(False)
        for btn in self.option_btns.values():
            btn.config(state=tk.NORMAL)
        self.submit_answer_btn.config(state=tk.NORMAL, text="提交答案 📤", bg="#2196F3")
        self.answer_frame.pack(fill=tk.X, padx=10, pady=10, before=self.score_frame)
        # 有剩余求助次数才显示求助按钮
        if self.extend_btn:
            try:
                self.extend_btn.destroy()
            except:
                pass
            self.extend_btn = None
        if self.extend_remaining > 0:
            self.extend_btn = tk.Button(
                self.answer_frame, text=f"📣 求助啦啦队（余{self.extend_remaining}次）",
                font=("微软雅黑", 10, "bold"),
                bg="#FF9800", fg="white", bd=0,
                command=self._extend_time
            )
            self.extend_btn.pack(anchor=tk.W, padx=5, pady=(5, 0))

    def _update_extend_btn(self):
        """更新求助啦啦队按钮状态"""
        if self.extend_btn:
            if self.extend_remaining > 0:
                self.extend_btn.config(state=tk.NORMAL, text=f"📣 求助啦啦队（余{self.extend_remaining}次）",
                                       bg="#FF9800")
            else:
                # 次数用完，隐藏按钮
                try:
                    self.extend_btn.destroy()
                except:
                    pass
                self.extend_btn = None

    def _extend_time(self):
        """发送求助啦啦队请求"""
        if not self.connected or self.extend_remaining <= 0:
            return
        try:
            self.socket.send(json.dumps({"type": "extend_time"}).encode())
            self._log("📤 请求啦啦队支援...")
        except:
            self._log("❌ 发送求助请求失败")

    def _hide_answer_mode(self):
        """隐藏答案选择，恢复抢答模式"""
        self.answering = False
        self._stop_client_timer()
        # 移除求助啦啦队按钮
        if self.extend_btn:
            try:
                self.extend_btn.destroy()
            except:
                pass
            self.extend_btn = None
        self.answer_frame.pack_forget()
        self.question_frame.pack_forget()
        self.buzz_frame.pack(fill=tk.X, padx=10, pady=10)
        self.hint_label.pack(fill=tk.X, padx=10, pady=(0, 5))

    def _start_client_timer(self, seconds):
        """客户端倒计时"""
        self._stop_client_timer()
        self._client_timer_remaining = seconds
        hint = tk.Label(
            self.answer_frame, text="💡 超时未提交答案视为答错",
            font=("微软雅黑", 9), fg="#666"
        )
        hint.pack(anchor=tk.W, padx=5)
        self._client_timer_hint = hint
        self._client_timer_label = tk.Label(
            self.answer_frame, text=f"⏱ 剩余 {seconds} 秒",
            font=("微软雅黑", 14, "bold"), fg="#FF5722"
        )
        self._client_timer_label.pack(anchor=tk.W, padx=5, pady=(0, 5))

        def tick():
            self._client_timer_remaining -= 1
            if self._client_timer_label and self._client_timer_label.winfo_exists():
                if self._client_timer_remaining <= 0:
                    self._client_timer_label.config(text="⏰ 时间到！", fg="#f44336")
                else:
                    self._client_timer_label.config(text=f"⏱ 剩余 {self._client_timer_remaining} 秒")
                    self._client_timer_id = self.root.after(1000, tick)

        self._client_timer_id = self.root.after(1000, tick)

    def _stop_client_timer(self):
        """取消客户端倒计时"""
        if hasattr(self, '_client_timer_id') and self._client_timer_id:
            try:
                self.root.after_cancel(self._client_timer_id)
            except:
                pass
            self._client_timer_id = None
        if hasattr(self, '_client_timer_label') and self._client_timer_label:
            try:
                self._client_timer_label.destroy()
            except:
                pass
            self._client_timer_label = None
        # 销毁提示标签
        if hasattr(self, '_client_timer_hint') and self._client_timer_hint:
            try:
                self._client_timer_hint.destroy()
            except:
                pass
            self._client_timer_hint = None

    def _connect(self):
        """连接服务器"""
        ip = self.ip_var.get().strip()
        name = self.name_var.get().strip()

        if not ip:
            messagebox.showwarning("提示", "请输入服务器IP地址")
            return
        if not name:
            messagebox.showwarning("提示", "请输入选手名")
            return

        self.player_name = name

        # 禁用连接按钮
        self.connect_btn.config(state=tk.DISABLED, text="连接中...")

        # 在后台线程连接
        threading.Thread(target=self._do_connect, args=(ip,), daemon=True).start()

    def _do_connect(self, ip):
        """后台连接服务器"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((ip, 8888))

            # 发送选手名
            sock.send(json.dumps({"name": self.player_name}).encode())

            # 等待响应
            data = sock.recv(1024).decode("utf-8")
            response = json.loads(data)

            if response.get("type") == "error":
                self.root.after(0, lambda: self._connect_failed(response.get("msg", "连接被拒绝")))
                sock.close()
                return

            self.socket = sock
            self.connected = True

            # 提前读取连接成功消息中的比赛名称
            game_name = response.get("game_name", "")
            if game_name:
                self.root.title(f"抢答软件 - 客户端 | {game_name}")

            self.root.after(0, self._connect_success)

            # 开始接收消息
            self._receive_loop()

        except socket.timeout:
            self.root.after(0, lambda: self._connect_failed("连接超时"))
        except ConnectionRefusedError:
            self.root.after(0, lambda: self._connect_failed("连接被拒绝，请检查服务器是否已启动"))
        except Exception as e:
            self.root.after(0, lambda: self._connect_failed(str(e)))

    def _connect_success(self):
        """连接成功后的界面更新"""
        self._hide_answer_mode()
        self.status_label.config(text="🟢 已连接", fg="green")
        self.connect_btn.config(state=tk.DISABLED, text="已连接 ✅")
        self.ip_entry.config(state=tk.DISABLED)
        self.name_entry.config(state=tk.DISABLED)
        # 连接成功后显示分数区
        self.score_frame.pack(fill=tk.X, padx=10, pady=(0, 10), before=self.root.pack_slaves()[-1])
        self._log(f"✅ 已连接到服务器 [{self.ip_var.get()}]")
        self._log("🎯 请等待管理员开始抢答...")
        self.buzz_btn.config(state=tk.DISABLED, bg="#9E9E9E", text="⏳ 等待开始...")

    def _connect_failed(self, reason):
        """连接失败"""
        self.status_label.config(text="🔴 连接失败", fg="red")
        self.connect_btn.config(state=tk.NORMAL, text="连接服务器")
        self._log(f"❌ 连接失败: {reason}")
        if self.root.winfo_exists():
            title = "连接失败"
            if "比赛尚未开始" in reason:
                title = "比赛尚未开始"
            messagebox.showwarning(title, reason)

    def _receive_loop(self):
        """接收消息循环"""
        try:
            self.socket.settimeout(8)
        except:
            pass

        while self.connected:
            try:
                data = self.socket.recv(4096)
                if not data:
                    break
                msg = json.loads(data.decode("utf-8"))
                self.root.after(0, self._handle_message, msg)
            except socket.timeout:
                continue
            except (json.JSONDecodeError, ConnectionResetError, ConnectionAbortedError, OSError) as e:
                self._log(f"❌ 接收消息异常: {type(e).__name__}: {e}")
                break

        self.connected = False
        self.root.after(0, self._on_disconnect)

    def _handle_message(self, msg):
        """处理服务器消息"""
        msg_type = msg.get("type")

        if msg_type == "ping":
            try:
                self.socket.send(json.dumps({"type": "pong"}).encode())
            except:
                pass
            return

        if msg_type == "info":
            self._log(f"📢 {msg.get('msg', '')}")
            game_name = msg.get("game_name", "")
            if game_name:
                self.root.title(f"抢答软件 - 客户端 | {game_name}")

        elif msg_type == "system":
            self._log(f"ℹ️ {msg.get('msg', '')}")

        elif msg_type == "question":
            q_type = msg.get("q_type", "")
            q_text = msg.get("msg", "")
            self.current_question_text = q_text
            if q_type:
                self.question_frame.config(text=f"📝 题目 — {q_type}")
            else:
                self.question_frame.config(text="📝 题目")
            self._log(f"📝 {q_text}")

        elif msg_type == "round_start":
            if self.game_over:
                return
            self.buzzed = False
            self._hide_answer_mode()
            self.buzz_btn.config(
                state=tk.NORMAL,
                bg="#FF5722",
                text="🚀 抢 答 🚀\n→ 按 空格键 或 回车键 ←"
            )
            self._log(f"🟢 {msg.get('msg', '')}")

        elif msg_type == "round_end":
            self._hide_answer_mode()
            if not self.game_over:
                self.buzz_btn.config(
                    state=tk.DISABLED,
                    bg="#9E9E9E",
                    text="⏳ 等待下一轮..."
                )
            self._log(f"🔴 {msg.get('msg', '')}")

        elif msg_type == "answer_received":
            self._log(f"📤 {msg.get('msg', '')}")

        elif msg_type == "buzz_result":
            if self.game_over:
                return
            winner = msg.get("winner", False)
            if winner:
                # 抢到了！切换到答案选择模式
                timeout = msg.get("timeout", 15)
                self.extend_remaining = msg.get("extend_remaining", 0)
                self.extend_seconds = msg.get("extend_seconds", 15)
                self._start_client_timer(timeout)
                self.buzz_btn.config(
                    state=tk.DISABLED,
                    bg="#4CAF50",
                    text=f"🎉🎉 抢答成功！⏱ {timeout}s"
                )
                self._log(f"🎉🎉🎉 太棒了！你抢答成功了！请选择答案 A-F（可多选） ⏱ {timeout}秒 🎉🎉🎉")
                self._flash_btn()
                question = msg.get("question", "")
                q_type = msg.get("q_type", "")
                if q_type:
                    self.question_frame.config(text=f"📝 题目 — {q_type}")
                self._show_answer_mode(question)
            else:
                # 没抢到
                self._hide_answer_mode()
                self._stop_client_timer()
                self.buzz_btn.config(
                    state=tk.DISABLED,
                    bg="#f44336",
                    text="😅 手慢无，下次加油"
                )

            self._log(f"{msg.get('msg', '')}")

        elif msg_type == "score_update":
            score = msg.get("score", 0)
            self.score_label.config(text=str(score))
            result_msg = msg.get("msg", "")
            self._log(f"💰 当前分数: {score}")
            # 排名已锁定的选手不更新抢答按钮
            if self.game_over:
                return
            # 在抢答按钮上显示判题结果
            self._hide_answer_mode()
            if "答对了" in result_msg or "答错" in result_msg:
                is_correct = "答对了" in result_msg
                self.buzz_btn.config(
                    state=tk.DISABLED,
                    bg="#4CAF50" if is_correct else "#f44336",
                    text=result_msg
                )

        elif msg_type == "timeout":
            # 答题超时
            self._stop_client_timer()
            self._hide_answer_mode()
            if not self.game_over:
                self.buzz_btn.config(
                    state=tk.DISABLED,
                    bg="#f44336",
                    text="⏰ 答题超时！"
                )
            self._log(f"⏰ {msg.get('msg', '')}")

        elif msg_type == "ban_status":
            banned = msg.get("banned", False)
            if banned:
                self._log("🚫 你已被管理员禁赛")
                self.buzz_btn.config(state=tk.DISABLED, bg="#333333", text="🚫 已禁赛")
                self.status_label.config(text="🔴 已禁赛", fg="red")
            else:
                self._log("🟢 你已被管理员恢复参赛资格")
                self.status_label.config(text="🟢 已连接", fg="green")

        elif msg_type == "extend_result":
            success = msg.get("success", False)
            if success:
                self.extend_remaining = msg.get("remaining", 0)
                remaining_time = msg.get("time_remaining", 0)
                self._start_client_timer(remaining_time)
                self._update_extend_btn()
                self._log(f"✅ {msg.get('msg', '')}")
            else:
                self._log(f"❌ {msg.get('msg', '')}")

        elif msg_type == "error":
            msg_text = msg.get('msg', '')
            self._log(f"⚠️ {msg_text}")

        elif msg_type == "shutdown":
            self._log("🛑 服务器已关闭")
            self._on_disconnect()

        elif msg_type == "rank_locked":
            rank = msg.get("rank", 0)
            rank_titles = {1: "🥇 第1名", 2: "🥈 第2名", 3: "🥉 第3名"}
            title = rank_titles.get(rank, f"第{rank}名")
            self._log(f"🎉 {msg.get('msg', '')}")
            self.game_over = True
            self.buzz_btn.config(state=tk.DISABLED, bg="#9C27B0", text=f"🏆 已锁定排名\n{title}")
            self._hide_answer_mode()
            self._stop_client_timer()
            messagebox.showinfo("🎉 排名锁定", f"恭喜！你获得 {title}！\n比赛仍在继续，请等待其他选手")

        elif msg_type == "rank_update":
            rankings = msg.get("rankings", [])
            lines = [f"{r['title']} {r['name']} - {r['score']}分" for r in rankings]
            self._log("🏆 最新排名: " + " | ".join(lines))

        elif msg_type == "restart_game":
            """重赛：重置客户端所有UI状态"""
            self.game_over = False
            self._hide_answer_mode()
            self._stop_client_timer()
            self.score_label.config(text="0")
            self.buzz_btn.config(
                state=tk.DISABLED,
                bg="#9E9E9E",
                text="⏳ 等待开始..."
            )
            self._log(f"🆕 {msg.get('msg', '')}")

        elif msg_type == "game_over":
            rankings = msg.get("rankings", [])
            self._hide_answer_mode()
            self._stop_client_timer()
            lines = []
            for r in rankings:
                lines.append(f"{r['title']} {r['name']} - {r['score']}分")
            rank_str = "\n".join(lines)
            self._log(f"🏁 比赛全部结束！\n{rank_str}")
            self.buzz_btn.config(
                state=tk.DISABLED,
                bg="#9C27B0",
                text=f"🏁 比赛结束\n{rank_str}"
            )
            for r in rankings:
                if r['name'] == self.player_name:
                    messagebox.showinfo("🏁 比赛结束", f"恭喜！你获得 {r['title']}！\n得分: {r['score']}分")
                    break
            else:
                messagebox.showinfo("🏁 比赛结束", "所有排名已产生，比赛结束")

        elif msg_type == "server_closed":
            # 比赛结束，服务端主动断开
            self._hide_answer_mode()
            self._stop_client_timer()
            self.game_over = True
            self.buzz_btn.config(
                state=tk.DISABLED,
                bg="#9C27B0",
                text="🏁 比赛已结束\n连接已断开"
            )
            messagebox.showinfo("比赛结束", f"🏁 比赛已结束，连接已断开\n感谢参与！")
            self.running = False
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass

    def _flash_btn(self):
        """抢答成功闪烁效果"""
        def flash():
            for _ in range(3):
                self.buzz_btn.config(bg="#FFD700")
                time.sleep(0.15)
                self.buzz_btn.config(bg="#FF5722")
                time.sleep(0.15)

        threading.Thread(target=flash, daemon=True).start()

    def _buzz(self):
        """发送抢答信号"""
        if not self.connected:
            return
        if self.buzzed:
            return
        if self.game_over:
            return

        self.buzzed = True
        try:
            self.socket.send(json.dumps({"type": "buzz"}).encode())
            self._log("🔔 已发送抢答信号...")
            self.buzz_btn.config(state=tk.DISABLED, bg="#9E9E9E", text="⏳ 等待结果...")
        except Exception as e:
            self._log(f"❌ 发送抢答信号失败: {e}")
            self._on_disconnect()

    def _submit_answer(self):
        """提交选择的答案"""
        if not self.answering:
            return
        selected = [k for k, v in self.option_vars.items() if v.get()]
        if not selected:
            return
        answer_str = "".join(selected)
        try:
            self.socket.send(json.dumps({"type": "answer", "answer": answer_str}).encode())
            self._log(f"📤 答案已提交: {answer_str}")
            # 停止倒计时
            self._stop_client_timer()
            # 禁用所有选项按钮
            for btn in self.option_btns.values():
                btn.config(state=tk.DISABLED)
            self.submit_answer_btn.config(state=tk.DISABLED, text="已提交 ✅")
            self.answering = False
        except Exception as e:
            self._log(f"❌ 提交答案失败: {e}")
            self._on_disconnect()

    def _on_key_return(self, event):
        """回车键处理"""
        if self.answering:
            self._submit_answer()
            return "break"
        if self.buzz_btn["state"] == tk.NORMAL:
            self._buzz()
            return "break"

    def _on_buzz_key(self, event):
        """空格触发抢答"""
        if self.answering:
            return
        if self.buzz_btn["state"] == tk.NORMAL:
            self._buzz()
            return "break"

    def _on_disconnect(self):
        """断开连接"""
        self.connected = False
        self._hide_answer_mode()
        self.status_label.config(text="🔴 已断开", fg="red")
        self.buzz_btn.config(state=tk.DISABLED, bg="#9E9E9E", text="❌ 已断开")
        self.connect_btn.config(state=tk.NORMAL, text="重新连接")
        self.ip_entry.config(state=tk.NORMAL)
        self.name_entry.config(state=tk.NORMAL)
        self._log("🔌 已与服务器断开连接")

    def _on_close(self):
        """关闭窗口"""
        if self.connected:
            if messagebox.askokcancel("退出", "退出视为放弃比赛资格，确认要退出吗？"):
                self.connected = False
                if self.socket:
                    try:
                        self.socket.close()
                    except:
                        pass
                self.root.destroy()
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    app = QuizClient(root)
    root.mainloop()


if __name__ == "__main__":
    main()
