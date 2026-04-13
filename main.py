import streamlit as st
import discord
from discord.ext import commands, tasks
from jira import JIRA
import threading
import asyncio
from datetime import datetime
import time

# --- 1. 持久化日誌 ---
if 'global_logs' not in st.session_state:
    st.session_state.global_logs = [f"[{datetime.now().strftime('%H:%M:%S')}] 系統啟動..."]

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
        "TIME": int(S.get("CHECK_INTERVAL", 1))
    }
except Exception as e:
    st.error(f"❌ Secrets 載入失敗: {e}")
    st.stop()

# --- 3. Discord 機器人類別 ---
class JiraMonitorBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.last_seen_key = None
        self.jira = None

    async def setup_hook(self):
        # 延遲初始化 Jira，避免阻塞啟動
        try:
            add_log("📡 正在嘗試連線 Jira...")
            self.jira = JIRA(server=CONF["J_SERVER"], basic_auth=(CONF["J_EMAIL"], CONF["J_TOKEN"]))
            add_log("✅ Jira 連線成功")
        except Exception as e:
            add_log(f"❌ Jira 連線失敗: {e}")
        
        self.check_jira_task.start()
        add_log("✅ 掃描任務已掛載 (Tasks Started)")

    async def on_ready(self):
        add_log(f"✅ Discord 機器人已上線: {self.user}")

    @tasks.loop(minutes=CONF["TIME"])
    async def check_jira_task(self):
        if not self.jira:
            return
            
        try:
            jql = f'project = "{CONF["PROJ"]}" AND assignee = "{CONF["UID"]}" ORDER BY created DESC'
            issues = self.jira.search_issues(jql, maxResults=1)

            if issues:
                curr = issues[0]
                if self.last_seen_key is None:
                    self.last_seen_key = curr.key
                    add_log(f"📍 初始監測點: {curr.key}")
                    return

                if curr.key != self.last_seen_key:
                    self.last_seen_key = curr.key
                    channel = self.get_channel(CONF["CH_ID"])
                    if channel:
                        await channel.send(f"🚨 **新任務通知**: {curr.key}\n{curr.fields.summary}")
                        add_log(f"📩 Discord 通知已送出: {curr.key}")
            else:
                add_log("🔍 掃描中: 尚無新議題")
        except Exception as e:
            add_log(f"❌ 掃描循環異常: {e}")

# --- 4. Streamlit 介面與啟動邏輯 ---
st.title("Jira 🔍 Discord 控制台")

if "bot_started" not in st.session_state:
    st.session_state.bot_started = False

def start_bot():
    # 強制建立新的事件迴圈
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    bot = JiraMonitorBot()
    try:
        # 使用 run 之前先確認 Token 是否正確
        bot.run(CONF["D_TOKEN"])
    except Exception as e:
        add_log(f"❌ 機器人運行崩潰: {str(e)}")

if not st.session_state.bot_started:
    thread = threading.Thread(target=start_bot, daemon=True)
    thread.start()
    st.session_state.bot_started = True
    add_log("🚀 啟動執行緒中...")

# --- UI 顯示 ---
if st.button("🔄 手動刷新日誌與狀態"):
    st.rerun()

st.subheader("📝 運行日誌")
# 組合並顯示日誌
full_log = "\n".join(st.session_state.global_logs[::-1])
st.text_area("Live Log", value=full_log, height=400)

# 狀態儀表板
st.divider()
st.write(f"**檢查對象專案:** {CONF['PROJ']}")
st.write(f"**檢查對象 ID:** {CONF['UID']}")
