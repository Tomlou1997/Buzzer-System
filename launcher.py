"""
抢答软件 - 启动器
提供图形界面选择启动主控端或客户端
"""

import tkinter as tk
from tkinter import messagebox
import subprocess
import sys
import os


def start_server():
    """启动主控端"""
    try:
        subprocess.Popen(
            [sys.executable, "server.py"],
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        root.destroy()
    except Exception as e:
        messagebox.showerror("错误", f"启动主控端失败:\n{e}")


def start_client():
    """启动客户端"""
    try:
        subprocess.Popen(
            [sys.executable, "client.py"],
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        root.destroy()
    except Exception as e:
        messagebox.showerror("错误", f"启动客户端失败:\n{e}")


root = tk.Tk()
root.title("抢答软件 - 启动器")
root.geometry("400x280")
root.resizable(False, False)

# 标题
tk.Label(
    root,
    text="🚀 抢答软件",
    font=("微软雅黑", 20, "bold"),
    fg="#FF5722"
).pack(pady=(30, 10))

tk.Label(
    root,
    text="请选择启动模式",
    font=("微软雅黑", 11),
    fg="gray"
).pack(pady=(0, 20))

# 主控端按钮
btn_frame = tk.Frame(root)
btn_frame.pack(expand=True)

server_btn = tk.Button(
    btn_frame,
    text="🎮 主控端（管理员）",
    font=("微软雅黑", 12),
    bg="#4CAF50", fg="white",
    width=20, height=2,
    command=start_server
)
server_btn.pack(pady=5)

client_btn = tk.Button(
    btn_frame,
    text="🎯 客户端（选手）",
    font=("微软雅黑", 12),
    bg="#2196F3", fg="white",
    width=20, height=2,
    command=start_client
)
client_btn.pack(pady=5)

exit_btn = tk.Button(
    btn_frame,
    text="退出",
    font=("微软雅黑", 10),
    width=10,
    command=root.destroy
)
exit_btn.pack(pady=(10, 0))

root.mainloop()
