"""
抢答软件 - 客户端
选手在此连接服务器、抢答、查看信息
"""

import tkinter as tk
from tkinter import ttk, messagebox
import socket
import json
import threading
import time


class QuizClient:
    def __init__(self, root):
        self.root = root
        self.root.title("抢答软件 - 客户端 v2.0")
        self.root.geometry("600x550")
        self.root.resizable(True, True)
        self.root.minsize(500, 450)

        # 全屏状态
        self.fullscreen = False

        # 网络相关
        self.socket = None
        self.connected = False
        self.player_name = ""
        self.buzzed = False  # 本轮是否已抢答
        self.answering = False  # 是否在答案输入模式

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
        self.ip_var = tk.StringVar(value="127.0.0.1")
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

        # ====== 中间主区域：抢答按钮 / 答案输入（互斥显示） ======
        self.main_area = tk.Frame(self.root)
        self.main_area.pack(fill=tk.X, padx=10, pady=5)

        # --- 模式1：抢答按钮 ---
        self.buzz_frame = tk.Frame(self.main_area, height=100)
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
        self.buzz_frame.pack(fill=tk.X)

        # 抢答操作提示
        self.hint_label = tk.Label(
            self.root,
            text="💡 抢答操作：按 空格键(Space) 或 回车键(Enter)",
            font=("微软雅黑", 9),
            fg="#FF5722"
        )
        self.hint_label.pack(fill=tk.X, padx=10, pady=(0, 5))

        # --- 模式2：答案输入（默认隐藏） ---
        self.answer_frame = tk.Frame(self.root)
        answer_title = tk.Label(
            self.answer_frame, text="✏️ 你抢到了！请输入你的答案：",
            font=("微软雅黑", 12, "bold"), fg="#4CAF50"
        )
        answer_title.pack(anchor=tk.W, padx=5, pady=(5, 2))

        answer_row = tk.Frame(self.answer_frame)
        answer_row.pack(fill=tk.X, padx=5, pady=5)

        self.answer_var = tk.StringVar()
        self.answer_entry = tk.Entry(
            answer_row, textvariable=self.answer_var,
            font=("微软雅黑", 14), state=tk.DISABLED
        )
        self.answer_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=8)

        self.submit_answer_btn = tk.Button(
            answer_row, text="提交答案 📤",
            font=("微软雅黑", 11, "bold"),
            bg="#2196F3", fg="white", state=tk.DISABLED,
            command=self._submit_answer
        )
        self.submit_answer_btn.pack(side=tk.RIGHT)

        answer_hint = tk.Label(
            self.answer_frame,
            text="💡 输入答案后按 回车键(Enter) 或点击「提交答案」按钮",
            font=("微软雅黑", 9), fg="#666"
        )
        answer_hint.pack(anchor=tk.W, padx=5, pady=(0, 5))

        # ====== 底部：信息显示 ======
        info_frame = tk.LabelFrame(self.root, text="信息", font=("微软雅黑", 10))
        info_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.info_text = tk.Text(
            info_frame,
            font=("微软雅黑", 10),
            bg="#1e1e1e", fg="#d4d4d4",
            state=tk.DISABLED,
            wrap=tk.WORD
        )
        self.info_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 分数显示
        score_frame = tk.Frame(self.root)
        score_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        tk.Label(score_frame, text="当前分数:", font=("微软雅黑", 10)).pack(side=tk.LEFT)
        self.score_label = tk.Label(
            score_frame, text="0", font=("微软雅黑", 14, "bold"),
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

    def _log(self, msg):
        """添加日志到信息区"""
        if hasattr(self, 'info_text') and self.info_text:
            self.info_text.config(state=tk.NORMAL)
            self.info_text.insert(tk.END, f"> {msg}\n")
            self.info_text.see(tk.END)
            self.info_text.config(state=tk.DISABLED)

    def _show_answer_mode(self):
        """切换到答案输入模式"""
        self.answering = True
        self.buzz_frame.pack_forget()
        self.hint_label.pack_forget()
        self.answer_frame.pack(fill=tk.X, padx=10, pady=10)
        self.answer_var.set("")
        self.answer_entry.config(state=tk.NORMAL)
        self.answer_entry.focus()
        self.submit_answer_btn.config(state=tk.NORMAL, text="提交答案 📤")

    def _hide_answer_mode(self):
        """隐藏答案输入，恢复抢答模式"""
        self.answering = False
        self.answer_frame.pack_forget()
        self.buzz_frame.pack(fill=tk.X)
        self.hint_label.pack(fill=tk.X, padx=10, pady=(0, 5))

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
        self.connect_btn.config(state=tk.NORMAL, text="已连接 ✅")
        self.ip_entry.config(state=tk.DISABLED)
        self.name_entry.config(state=tk.DISABLED)
        self._log(f"✅ 已连接到服务器 [{self.ip_var.get()}]")
        self._log("🎯 请等待管理员开始抢答...")
        self.buzz_btn.config(state=tk.DISABLED, bg="#9E9E9E", text="⏳ 等待开始...")

    def _connect_failed(self, reason):
        """连接失败"""
        self.status_label.config(text="🔴 连接失败", fg="red")
        self.connect_btn.config(state=tk.NORMAL, text="连接服务器")
        self._log(f"❌ 连接失败: {reason}")

    def _receive_loop(self):
        """接收消息循环"""
        # 设置 socket 超时，避免 recv 永久阻塞
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
                # 超时正常，继续循环
                continue
            except (json.JSONDecodeError, ConnectionResetError, ConnectionAbortedError, OSError):
                break

        # 断开连接
        self.connected = False
        self.root.after(0, self._on_disconnect)

    def _handle_message(self, msg):
        """处理服务器消息"""
        msg_type = msg.get("type")

        if msg_type == "ping":
            # 心跳检测：回复 pong
            try:
                self.socket.send(json.dumps({"type": "pong"}).encode())
            except:
                pass
            return

        if msg_type == "info":
            self._log(f"📢 {msg.get('msg', '')}")

        elif msg_type == "system":
            self._log(f"ℹ️ {msg.get('msg', '')}")

        elif msg_type == "question":
            self._log(f"📝 {msg.get('msg', '')}")

        elif msg_type == "round_start":
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
            self.buzz_btn.config(
                state=tk.DISABLED,
                bg="#9E9E9E",
                text="⏳ 等待下一轮..."
            )
            self._log(f"🔴 {msg.get('msg', '')}")

        elif msg_type == "answer_received":
            self._log(f"📤 {msg.get('msg', '')}")

        elif msg_type == "buzz_result":
            winner = msg.get("winner", False)
            if winner:
                # 抢到了！切换到答案输入模式
                self.buzz_btn.config(
                    state=tk.DISABLED,
                    bg="#4CAF50",
                    text="🎉🎉 抢答成功！ ✏️ 请输入答案"
                )
                self.info_text.config(state=tk.NORMAL)
                self.info_text.insert(tk.END, "🎉🎉🎉 太棒了！你抢答成功了！请在下方输入你的答案 🎉🎉🎉\n")
                self.info_text.see(tk.END)
                self.info_text.config(state=tk.DISABLED)
                self._flash_btn()
                # 切换到答案输入
                self._show_answer_mode()
            else:
                # 没抢到
                self._hide_answer_mode()
                self.buzz_btn.config(
                    state=tk.DISABLED,
                    bg="#f44336",
                    text="😅 慢了！"
                )

            self._log(f"{msg.get('msg', '')}")

        elif msg_type == "score_update":
            score = msg.get("score", 0)
            self.score_label.config(text=str(score))
            self._log(f"💰 当前分数: {score}")

        elif msg_type == "ban_status":
            banned = msg.get("banned", False)
            if banned:
                self._log("🚫 你已被管理员禁赛")
                self.buzz_btn.config(state=tk.DISABLED, bg="#333333", text="🚫 已禁赛")
                self.status_label.config(text="🔴 已禁赛", fg="red")
            else:
                self._log("🟢 你已被管理员恢复参赛资格")
                self.status_label.config(text="🟢 已连接", fg="green")

        elif msg_type == "error":
            self._log(f"⚠️ {msg.get('msg', '')}")

        elif msg_type == "shutdown":
            self._log("🛑 服务器已关闭")
            self._on_disconnect()

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

        self.buzzed = True
        try:
            self.socket.send(json.dumps({"type": "buzz"}).encode())
            self._log("🔔 已发送抢答信号...")
            self.buzz_btn.config(state=tk.DISABLED, bg="#9E9E9E", text="⏳ 等待结果...")
        except:
            self._log("❌ 发送抢答信号失败")
            self._on_disconnect()

    def _submit_answer(self):
        """提交答案"""
        if not self.answering:
            return
        answer = self.answer_var.get().strip()
        if not answer:
            return
        try:
            self.socket.send(json.dumps({"type": "answer", "answer": answer}).encode())
            self._log(f"📤 答案已提交: {answer}")
            self.answer_entry.config(state=tk.DISABLED)
            self.submit_answer_btn.config(state=tk.DISABLED, text="已提交 ✅")
            self.answering = False
        except:
            self._log("❌ 提交答案失败")
            self._on_disconnect()

    def _on_key_return(self, event):
        """回车键处理：先判断是否在答案模式，再判断是否抢答"""
        if self.answering:
            # 答案模式：提交答案
            self._submit_answer()
            return "break"
        # 抢答模式
        if self.buzz_btn["state"] == tk.NORMAL:
            self._buzz()
            return "break"

    def _on_buzz_key(self, event):
        """空格触发抢答"""
        if self.answering:
            return  # 答案模式下空格不抢答
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
            if messagebox.askokcancel("退出", "确定要断开连接并退出吗？"):
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
