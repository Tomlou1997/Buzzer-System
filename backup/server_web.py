"""
🎯 抢答系统 - 网页版服务端
基于 FastAPI + WebSocket
"""
import asyncio
import json
import os
import time
import threading
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import openpyxl

app = FastAPI(title="抢答系统")

# ============================================================
# HTML 页面路由
# ============================================================
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

@app.get("/")
async def admin_page():
    path = os.path.join(TEMPLATES_DIR, "server.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>管理端页面未找到</h1><p>请确保 templates/server.html 存在</p>")

@app.get("/client")
async def client_page():
    path = os.path.join(TEMPLATES_DIR, "client.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>客户端页面未找到</h1><p>请确保 templates/client.html 存在</p>")

# ============================================================
# 数据存储
# ============================================================
class GameState:
    def __init__(self):
        self.clear()

    def clear(self):
        self.game_started = False          # 是否进入比赛模式
        self.game_over = False             # 比赛是否结束
        self.round_active = False          # 本轮抢答是否进行中
        self.game_name = ""                # 比赛名称
        self.questions = []                # 当前题库 [{question, answer, type, points}]
        self.question_banks = {}           # 所有题库 {name: [questions]}
        self.active_bank_name = ""         # 当前使用的题库名
        self.current_question_index = -1   # 当前题号
        self.first_buzzer = ""             # 本轮第一个抢到的选手名
        self.buzz_order = []               # 抢答顺序
        self.ranked_players = []           # 已锁定排名的选手 [(name, score, rank)]
        self.used_questions = set()        # 已用题目索引
        self.allow_repeat = False          # 是否允许重复答题
        self.round_num = 0                 # 当前轮次
        self.correct_points = 10           # 答对加分
        self.wrong_points = 5              # 答错/超时扣分
        self.answer_timeout = 15           # 答题倒计时秒数
        self.win_score = 20                # 获胜分
        self.win_rank_count = 3            # 前几名
        self.extend_max = 1                # 每场比赛可求助啦啦队次数
        self.extend_seconds = 15           # 每次增加秒数
        self.extend_limits = {}            # {name: remaining}
        self._timer_task = None            # 倒计时异步任务
        self._timer_remaining = 0
        self._timer_name = ""
        self.banned_players = set()        # 禁赛选手
        self.show_answer = False           # 是否显示参考答案

    def get_ranked_player_names(self):
        return [r[0] for r in self.ranked_players]


state = GameState()

# WebSocket 连接管理
class ConnectionManager:
    def __init__(self):
        self.admin: Optional[WebSocket] = None
        self.players: dict[str, WebSocket] = {}  # {name: ws}

    async def connect_admin(self, ws: WebSocket):
        await ws.accept()
        self.admin = ws

    def disconnect_admin(self):
        self.admin = None

    async def connect_player(self, ws: WebSocket, name: str):
        await ws.accept()
        self.players[name] = ws

    def disconnect_player(self, name: str):
        self.players.pop(name, None)

    async def send_admin(self, msg: dict):
        if self.admin:
            try:
                await self.admin.send_json(msg)
            except:
                pass

    async def send_player(self, name: str, msg: dict):
        ws = self.players.get(name)
        if ws:
            try:
                await ws.send_json(msg)
            except:
                pass

    async def broadcast(self, msg: dict):
        for name in list(self.players.keys()):
            await self.send_player(name, msg)

    def get_player_list(self):
        return [{"name": n, "score": state.clients.get(n, {}).get("score", 0),
                 "banned": n in state.banned_players,
                 "ranked": n in state.get_ranked_player_names()}
                for n in self.players.keys()]


manager = ConnectionManager()
state.clients = {}  # {name: {"score": int, "connected": bool}}


# ============================================================
# 页面路由
# ============================================================
@app.get("/")
async def get_admin_page():
    html_path = os.path.join(os.path.dirname(__file__), "templates", "server.html")
    with open(html_path, encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/client")
async def get_client_page():
    html_path = os.path.join(os.path.dirname(__file__), "templates", "client.html")
    with open(html_path, encoding="utf-8") as f:
        return HTMLResponse(f.read())


# ============================================================
# WebSocket - 管理端
# ============================================================
@app.websocket("/ws/admin")
async def admin_websocket(ws: WebSocket):
    await manager.connect_admin(ws)
    try:
        while True:
            data = await ws.receive_json()
            action = data.get("action")

            if action == "import_bank":
                # 导入题库（文件名方式）
                await handle_import_bank(ws, data)
            elif action == "activate_bank":
                await handle_activate_bank(ws, data)
            elif action == "delete_bank":
                await handle_delete_bank(ws, data)
            elif action == "start_game":
                await handle_start_game(ws, data)
            elif action == "switch_question":
                await handle_switch_question(ws, data)
            elif action == "start_round":
                await handle_start_round()
            elif action == "stop_round":
                await handle_stop_round()
            elif action == "judge_correct":
                await handle_judge(data.get("name", ""), True)
            elif action == "judge_wrong":
                await handle_judge(data.get("name", ""), False)
            elif action == "ban_player":
                await handle_ban_player(ws, data)
            elif action == "set_score":
                await handle_set_score(ws, data)
            elif action == "reset_scores":
                await handle_reset_scores()
            elif action == "restart_game":
                await handle_restart_game()
            elif action == "end_game":
                await handle_end_game()
            elif action == "update_settings":
                await handle_update_settings(ws, data)
            elif action == "get_state":
                await send_full_state(ws)
            elif action == "upload_bank":
                pass  # 通过 /upload_bank REST 接口处理

    except WebSocketDisconnect:
        manager.disconnect_admin()

# ============================================================
# WebSocket - 客户端
# ============================================================
@app.websocket("/ws/client")
async def client_websocket(ws: WebSocket):
    await ws.accept()
    name = ""
    try:
        # 先收连接消息
        data = await ws.receive_json()
        if data.get("action") == "connect":
            name = data.get("name", "")
            if not name:
                await ws.send_json({"type": "error", "msg": "请输入选手名称"})
                ws.close()
                return
            if name in manager.players:
                await ws.send_json({"type": "error", "msg": "该名称已被使用"})
                ws.close()
                return
            if not state.game_started:
                await ws.send_json({"type": "error", "msg": "比赛尚未开始"})
                ws.close()
                return

            # 加入
            if name not in state.clients:
                state.clients[name] = {"score": 0}
            manager.players[name] = ws
            state.extend_limits[name] = state.extend_max

            await ws.send_json({"type": "connected", "name": name,
                                "score": state.clients[name]["score"],
                                "game_name": state.game_name})
            await manager.send_admin({"type": "player_joined", "name": name,
                                      "players": manager.get_player_list()})
            await manager.broadcast({"type": "system", "msg": f"选手 [{name}] 加入了比赛"})

            # 如果有当前题目，发送
            if state.current_question_index >= 0 and state.current_question_index < len(state.questions):
                q = state.questions[state.current_question_index]
                await ws.send_json({"type": "question", "q_type": q.get("type", ""),
                                    "msg": q["question"]})

            # 消息循环
            while True:
                data = await ws.receive_json()
                msg_type = data.get("action")
                if msg_type == "buzz":
                    await handle_player_buzz(name)
                elif msg_type == "answer":
                    await handle_player_answer(name, data.get("answer", ""))
                elif msg_type == "extend_time":
                    await handle_player_extend(name)
                elif msg_type == "ping":
                    await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        if name:
            manager.disconnect_player(name)
            await manager.send_admin({"type": "player_left", "name": name,
                                      "players": manager.get_player_list()})
            await manager.broadcast({"type": "system", "msg": f"选手 [{name}] 离开了比赛"})
            try:
                await ws.close()
            except:
                pass


# ============================================================
# REST API - 题库上传
# ============================================================
@app.post("/upload_bank")
async def upload_bank(file: UploadFile = File(...)):
    try:
        wb = openpyxl.load_workbook(file.file)
        ws = wb.active
        questions = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0] is None:
                continue
            q = {
                "question": str(row[0] or "").strip(),
                "answer": str(row[1] or "").strip(),
                "points": int(row[2]) if row[2] else 10,
                "type": str(row[4] or "").strip() if len(row) > 4 else ""
            }
            q["type"] = q.get("type", "") or "题目"
            if q["question"]:
                questions.append(q)

        if not questions:
            return {"success": False, "msg": "未读取到有效题目，请确认第2行开始有数据"}

        # 用文件名作为题库名（去重）
        bank_name = os.path.splitext(file.filename or "未命名题库")[0]
        original_name = bank_name
        suffix = 1
        while bank_name in state.question_banks:
            bank_name = f"{original_name}({suffix})"
            suffix += 1

        state.question_banks[bank_name] = questions
        return {"success": True, "msg": f"✅ 成功导入 {len(questions)} 道题",
                "banks": list(state.question_banks.keys()),
                "bank_counts": {n: len(q) for n, q in state.question_banks.items()}}
    except Exception as e:
        return {"success": False, "msg": f"导入失败: {str(e)}"}


# ============================================================
# 处理函数
# ============================================================
async def handle_import_bank(ws, data):
    # 通过文件名方式导入（备用）
    await ws.send_json({"type": "error", "msg": "请使用上传功能导入题库"})

async def handle_activate_bank(ws, data):
    name = data.get("name", "")
    if name in state.question_banks:
        state.active_bank_name = name
        state.questions = state.question_banks[name]
        state.current_question_index = -1
        state.used_questions.clear()
        await send_full_state(ws)
        await ws.send_json({"type": "toast", "msg": f"✅ 已加载题库：{name}（{len(state.questions)}题）"})
        await ws.send_json({"type": "show_welcome"})

async def handle_delete_bank(ws, data):
    name = data.get("name", "")
    if name in state.question_banks:
        del state.question_banks[name]
        if state.active_bank_name == name:
            state.active_bank_name = ""
            state.questions = []
        await send_full_state(ws)

async def handle_start_game(ws, data):
    if not state.questions:
        await ws.send_json({"type": "error", "msg": "请先导入题库"})
        return
    if state.game_started:
        # 继续比赛
        await ws.send_json({"type": "game_resumed"})
        return
    name = data.get("name", "知识竞赛")
    state.game_name = name
    state.game_started = True
    state.game_over = False
    state.current_question_index = 0
    state.used_questions.clear()
    state.ranked_players.clear()
    state.round_num = 0
    await send_full_state(ws)
    await ws.send_json({"type": "show_question", "index": 0,
                        **get_question_data(0)})
    await manager.broadcast({"type": "info", "msg": f"比赛开始：{name}", "game_name": name})

async def handle_switch_question(ws, data):
    index = data.get("index", 0)
    if 0 <= index < len(state.questions):
        state.current_question_index = index
        await ws.send_json({"type": "show_question", "index": index,
                            **get_question_data(index)})
        # 通知客户端显示题目
        q = state.questions[index]
        await manager.broadcast({"type": "question", "q_type": q.get("type", ""),
                                 "msg": q["question"]})

async def handle_start_round():
    if state.game_over:
        await manager.send_admin({"type": "toast", "msg": "比赛已结束"})
        return
    if state.round_active:
        return
    state.round_num += 1
    state.round_active = True
    state.first_buzzer = ""
    state.buzz_order.clear()
    await manager.broadcast({"type": "round_start", "round": state.round_num})
    await manager.broadcast({"type": "question",
                             "q_type": state.questions[state.current_question_index].get("type", ""),
                             "msg": state.questions[state.current_question_index]["question"]})
    await manager.send_admin({"type": "round_started", "round": state.round_num})

async def handle_stop_round():
    if not state.round_active:
        return
    state.round_active = False
    await manager.broadcast({"type": "round_end", "msg": "🔴 本轮抢答已结束"})
    await manager.send_admin({"type": "round_ended"})
    # 取消倒计时
    if state._timer_task:
        state._timer_task.cancel()
        state._timer_task = None

async def handle_player_buzz(name: str):
    if state.game_over:
        await manager.send_player(name, {"type": "error", "msg": "比赛已结束"})
        return
    if not state.round_active:
        await manager.send_player(name, {"type": "error", "msg": "本轮尚未开始"})
        return
    if name in state.banned_players:
        await manager.send_player(name, {"type": "error", "msg": "你已被禁赛"})
        return
    if state.first_buzzer:
        await manager.send_player(name, {"type": "buzz_result", "winner": False,
                                          "msg": f"😅 [{state.first_buzzer}] 抢先一步！"})
        return

    state.first_buzzer = name
    state.buzz_order.append(name)
    await manager.send_player(name, {"type": "buzz_result", "winner": True,
                                      "msg": "🎉 你抢答成功了！",
                                      "timeout": state.answer_timeout,
                                      "extend_remaining": state.extend_limits.get(name, 0),
                                      "extend_seconds": state.extend_seconds,
                                      "question": state.questions[state.current_question_index]["question"],
                                      "q_type": state.questions[state.current_question_index].get("type", "")})
    await manager.broadcast({"type": "system", "msg": f"🔔 [{name}] 抢答成功！"})
    await manager.send_admin({"type": "player_buzzed", "name": name})

    # 启动倒计时
    await start_timer(name)

async def start_timer(name: str):
    state._timer_remaining = state.answer_timeout
    state._timer_name = name

    async def tick():
        while state._timer_remaining > 0:
            await asyncio.sleep(1)
            state._timer_remaining -= 1
            # 更新管理端倒计时
            await manager.send_admin({"type": "timer_tick", "remaining": state._timer_remaining,
                                       "name": name})
        # 超时
        await handle_timer_timeout(name)

    state._timer_task = asyncio.create_task(tick())
    await manager.send_admin({"type": "timer_start", "remaining": state.answer_timeout, "name": name})

async def handle_timer_timeout(name: str):
    state.round_active = False
    correct = state.questions[state.current_question_index]["answer"] if state.current_question_index >= 0 else ""
    # 扣分
    if name in state.clients:
        state.clients[name]["score"] -= state.wrong_points
        await manager.send_player(name, {"type": "score_update",
                                          "score": state.clients[name]["score"],
                                          "msg": f"⏰ 答题超时！-{state.wrong_points}分"})
        await manager.send_player(name, {"type": "timeout", "msg": "⏰ 答题超时！"})
    await manager.broadcast({"type": "system", "msg": f"⏰ [{name}] 答题超时！"})
    await manager.send_admin({"type": "judge_result", "result": "timeout",
                              "name": name, "correct": correct,
                              "players": manager.get_player_list()})
    await send_rankings()
    await manager.send_admin({"type": "round_ended"})

async def handle_player_answer(name: str, answer: str):
    if name != state.first_buzzer:
        return
    if state._timer_task:
        state._timer_task.cancel()
        state._timer_task = None
    state.round_active = False

    correct = state.questions[state.current_question_index]["answer"] if state.current_question_index >= 0 else ""
    is_correct = answer.strip().upper() == correct.strip().upper()

    if is_correct:
        pts = state.correct_points
        if name in state.clients:
            if name not in state.get_ranked_player_names():
                state.clients[name]["score"] += pts
        await manager.send_player(name, {"type": "score_update",
                                          "score": state.clients[name]["score"],
                                          "msg": f"✅ 答对了！+{pts}分"})
        await manager.broadcast({"type": "system", "msg": f"✅ [{name}] 答对了！+{pts}分"})
        await manager.send_admin({"type": "judge_result", "result": "correct",
                                  "name": name, "answer": answer, "correct": correct,
                                  "players": manager.get_player_list()})
    else:
        pts = state.wrong_points
        if name in state.clients:
            if name not in state.get_ranked_player_names():
                state.clients[name]["score"] -= pts
        await manager.send_player(name, {"type": "score_update",
                                          "score": state.clients[name]["score"],
                                          "msg": f"❌ 答错了！-{pts}分"})
        await manager.broadcast({"type": "system", "msg": f"❌ [{name}] 答错了！正确答案: {correct}"})
        await manager.send_admin({"type": "judge_result", "result": "wrong",
                                  "name": name, "answer": answer, "correct": correct,
                                  "players": manager.get_player_list()})

    await send_rankings()
    await manager.send_admin({"type": "round_ended"})

async def handle_player_extend(name: str):
    remaining = state.extend_limits.get(name, 0)
    if remaining <= 0:
        await manager.send_player(name, {"type": "extend_result", "success": False,
                                          "msg": "啦啦队次数已用完"})
        return
    if not state._timer_task or state._timer_remaining <= 0:
        await manager.send_player(name, {"type": "extend_result", "success": False,
                                          "msg": "当前不在答题计时中"})
        return
    state.extend_limits[name] = remaining - 1
    state._timer_remaining += state.extend_seconds
    await manager.send_player(name, {"type": "extend_result", "success": True,
                                      "msg": f"🎉 啦啦队增加了{state.extend_seconds}秒，剩余{remaining-1}次",
                                      "remaining": remaining - 1,
                                      "time_remaining": state._timer_remaining})
    await manager.send_admin({"type": "player_extended", "name": name,
                              "remaining": state._timer_remaining,
                              "seconds": state.extend_seconds})

async def handle_judge(name: str, is_correct: bool):
    # 手动判题
    correct = state.questions[state.current_question_index]["answer"] if state.current_question_index >= 0 else ""
    if is_correct:
        pts = state.correct_points
        if name in state.clients:
            if name not in state.get_ranked_player_names():
                state.clients[name]["score"] += pts
        await manager.send_player(name, {"type": "score_update",
                                          "score": state.clients[name]["score"],
                                          "msg": f"✅ 答对了！+{pts}分"})
        await manager.broadcast({"type": "system", "msg": f"✅ [{name}] 答对了！+{pts}分"})
    else:
        pts = state.wrong_points
        if name in state.clients:
            if name not in state.get_ranked_player_names():
                state.clients[name]["score"] -= pts
        await manager.send_player(name, {"type": "score_update",
                                          "score": state.clients[name]["score"],
                                          "msg": f"❌ 答错了！-{pts}分"})
        await manager.broadcast({"type": "system", "msg": f"❌ [{name}] 答错了！正确答案: {correct}"})
    await manager.send_admin({"type": "judge_result", "result": "correct" if is_correct else "wrong",
                              "name": name, "correct": correct,
                              "players": manager.get_player_list()})
    await send_rankings()

async def handle_ban_player(ws, data):
    name = data.get("name", "")
    ban = data.get("ban", True)
    if ban:
        state.banned_players.add(name)
        await manager.send_player(name, {"type": "ban_status", "banned": True})
    else:
        state.banned_players.discard(name)
        await manager.send_player(name, {"type": "ban_status", "banned": False})
    await send_full_state(ws)

async def handle_set_score(ws, data):
    name = data.get("name", "")
    score = data.get("score", 0)
    if name in state.clients:
        state.clients[name]["score"] = score
        await manager.send_player(name, {"type": "score_update", "score": score,
                                          "msg": f"管理员已将分数设为 {score}分"})
        await send_full_state(ws)

async def handle_reset_scores():
    for name in state.clients:
        state.clients[name]["score"] = 0
        await manager.send_player(name, {"type": "score_update", "score": 0,
                                          "msg": "🔄 分数已重置"})
    state.ranked_players.clear()
    await manager.send_admin({"type": "scores_reset", "players": manager.get_player_list()})

async def handle_restart_game():
    state.game_over = False
    state.round_active = False
    state.first_buzzer = ""
    state.ranked_players.clear()
    state.banned_players.clear()
    state.used_questions.clear()
    state.round_num = 0
    state.extend_limits.clear()
    for name in state.clients:
        state.clients[name]["score"] = 0
        await manager.send_player(name, {"type": "restart_game", "msg": "🔄 重赛，分数已重置"})
        state.extend_limits[name] = state.extend_max
    await manager.send_admin({"type": "game_restarted", "players": manager.get_player_list()})

async def handle_end_game():
    state.game_started = False
    state.game_over = True
    state.round_active = False
    # 发送排名给客户端
    rankings = get_rankings()
    # 通知所有客户端
    for name in list(manager.players.keys()):
        await manager.send_player(name, {"type": "game_over", "rankings": rankings})
    await asyncio.sleep(1)
    # 断开所有客户端
    for name in list(manager.players.keys()):
        try:
            await manager.players[name].close()
        except:
            pass
    manager.players.clear()
    state.clients.clear()
    state.ranked_players.clear()
    state.banned_players.clear()
    state.extend_limits.clear()
    await manager.send_admin({"type": "game_ended"})

async def handle_update_settings(ws, data):
    state.correct_points = data.get("correct_points", state.correct_points)
    state.wrong_points = data.get("wrong_points", state.wrong_points)
    state.answer_timeout = data.get("answer_timeout", state.answer_timeout)
    state.win_score = data.get("win_score", state.win_score)
    state.win_rank_count = data.get("win_rank_count", state.win_rank_count)
    state.extend_max = data.get("extend_max", state.extend_max)
    state.extend_seconds = data.get("extend_seconds", state.extend_seconds)
    state.allow_repeat = data.get("allow_repeat", state.allow_repeat)
    state.show_answer = data.get("show_answer", state.show_answer)
    await ws.send_json({"type": "toast", "msg": "⚙ 设置已保存"})


# ============================================================
# 辅助函数
# ============================================================
def get_question_data(index):
    if 0 <= index < len(state.questions):
        q = state.questions[index]
        return {
            "question": q["question"],
            "answer": q["answer"],
            "points": q["points"],
            "type": q.get("type", ""),
            "total": len(state.questions),
            "answered": len(state.used_questions),
        }
    return {"question": "", "answer": "", "points": 0, "type": "", "total": 0, "answered": 0}

def get_rankings():
    """获取排名列表"""
    players = []
    for n, d in state.clients.items():
        rank = next((r[2] for r in state.ranked_players if r[0] == n), None)
        players.append({"name": n, "score": d["score"], "rank": rank})

    # 已锁定排名的按名次排最前，其余按分数降序
    ranked = [p for p in players if p["rank"] is not None]
    unranked = [p for p in players if p["rank"] is None]
    ranked.sort(key=lambda x: x["rank"])
    unranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked + unranked

async def send_rankings():
    rankings = get_rankings()
    await manager.send_admin({"type": "rankings", "rankings": rankings,
                               "players": manager.get_player_list()})

async def send_full_state(ws):
    """发送完整状态给管理端"""
    await ws.send_json({
        "type": "full_state",
        "game_started": state.game_started,
        "game_over": state.game_over,
        "game_name": state.game_name,
        "active_bank": state.active_bank_name,
        "banks": list(state.question_banks.keys()),
        "bank_counts": {n: len(q) for n, q in state.question_banks.items()},
        "current_index": state.current_question_index,
        "questions_count": len(state.questions),
        "players": manager.get_player_list(),
        "rankings": get_rankings(),
        "show_answer": state.show_answer,
        "settings": {
            "correct_points": state.correct_points,
            "wrong_points": state.wrong_points,
            "answer_timeout": state.answer_timeout,
            "win_score": state.win_score,
            "win_rank_count": state.win_rank_count,
            "extend_max": state.extend_max,
            "extend_seconds": state.extend_seconds,
            "allow_repeat": state.allow_repeat,
        }
    })


# ============================================================
# 启动
# ============================================================
if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("  [抢答系统] - 网页版")
    print("  =====================")
    print(f"  [管理端] http://10.8.51.7:8888")
    print(f"  [选手端] http://10.8.51.7:8888/client")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8888)
