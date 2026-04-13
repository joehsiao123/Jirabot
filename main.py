import streamlit as st
import discord
from discord.ext import commands, tasks
from jira import JIRA
import threading
import asyncio
from datetime import datetime
import sys

# --- 1. 全域日誌儲存 (解決 session_state 消失問題) ---
if 'global_logs' not in st.session_state:
    st.session_state.global_logs = [f"[{datetime.now().strftime('%H:%M:%S')}] 系統初始化中..."]

def add_log(msg):
    now = datetime.now().strftime("%H:%M:%S")
    st.session_state.global_logs.append(f"[{now}] {msg}")
    if len(st.session_state.global_logs) > 30:
        st.session_state.global_logs.pop(0)

# --- 2. 載入設定 ---
try:
    S = st.secrets
    CONF = {
        "D_TOKEN": S["DISCORD_TOKEN"],
        "CH_ID": int(S["CHANNEL_ID"]),
        "J_SERVER": S["JIRA_SERVER"],
        "J_EMAIL": S["JIRA_EMAIL"],
        "J_TOKEN": S["JIRA_API_TOKEN"],
        "PROJ": S["TARGET_PROJECT"],
        "UID": S["ASSIGNEE_ID"],
        "TIME": int(S.get("CHECK_INTERVAL", 1)),
        "TARGET_PROJ_B": S.get("TARGET_PROJECT_B", "PROJB")
    }
except Exception as e:
    st.error(f"❌ Secrets 載入失敗: {e}")
    st.stop()

# --- 3. Discord 機器人邏輯 ---
class JiraMonitorBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.last_seen_key = None
        # 使用 Jira 初始化測試
        try:
            self.jira = JIRA(server=CONF["J_SERVER"], basic_auth=(CONF["J_EMAIL"], CONF["J_TOKEN"]))
        except Exception as e:
            add_log(f"❌ Jira 連線預檢失敗: {e}")

    async def setup_hook(self):
        add_log("🤖 Discord Bot 已連線，準備啟動掃描任務...")
        self.check_jira_task.start()

    @tasks.loop(minutes=CONF["TIME"])
    async def check_jira_task(self):
        try:
            jql = f'project = "{CONF["PROJ"]}" AND assignee = "{CONF["UID"]}" ORDER BY created DESC'
            issues = self.jira.search_issues(jql, maxResults=1)

            if issues:
                curr = issues[0]
                if self.last_seen_key is None:
                    self.last_seen_key = curr.key
                    add_log(f"📍 初始標記完成，目前最新議題: {curr.key}")
                    return

                if curr.key != self.last_seen_key:
                    self.last_seen_key = curr.key
                    channel = self.get_channel(CONF["CH_ID"])
                    if channel:
                        embed = discord.Embed(title="🚨 新 Jira 任務指派！", color=0x3498db)
                        embed.description = f"**[{curr.key}]** {curr.fields.summary}"
                        await channel.send(embed=embed) # 簡化發送測試
                        add_log(f"📩 已發送 Discord 通知: {curr.key}")
            else:
                add_log("🔍 掃描中：目前無符合條件的任務")
        except Exception as e:
            add_log(f"❌ 掃描過程出錯: {e}")

# --- 4. 啟動與介面 ---
st.title("Jira 🔍 Discord 控制台")

# 確保 Bot 唯一次啟動
if "bot_started" not in st.session_state:
    st.session_state.bot_started = False

if not st.session_state.bot_started:
    def run_bot():
        asyncio.set_event_loop(asyncio.new_event_loop())
        bot = JiraMonitorBot()
        try:
            bot.run(CONF["D_TOKEN"])
        except Exception as e:
            add_log(f"❌ 機器人崩潰: {e}")

    thread = threading.Thread(target=run_bot, daemon=True)
    thread.start()
    st.session_state.bot_started = True
    add_log("🚀 背景執行緒已建立")

# --- UI 顯示區 ---
st.subheader("📝 運行日誌")
# 點擊按鈕強制刷新頁面，從 session_state 讀取最新日誌
if st.button("🔄 刷新日誌"):
    st.rerun()

log_text = "\n".join(st.session_state.global_logs[::-1])
st.text_area("Log Output", value=log_text, height=400)

st.divider()
st.write(f"當前檢查頻率: {CONF['TIME']} 分鐘一次")
