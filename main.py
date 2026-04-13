import streamlit as st
from jira import JIRA
import discord
from discord.ext import commands, tasks
import asyncio
import threading
from datetime import datetime
import time

# --- 1. 基礎設定 ---
st.set_page_config(page_title="Jira 監控中心", layout="wide")
st.title("📋 Jira 監控 & Discord 機器人")

try:
    S = st.secrets
    conf = {
        "J_SERVER": S["JIRA_SERVER"],
        "J_EMAIL": S["JIRA_EMAIL"],
        "J_TOKEN": S["JIRA_API_TOKEN"],
        "D_TOKEN": S["DISCORD_TOKEN"],
        "CH_ID": int(S["CHANNEL_ID"]),
        "PROJ": S["TARGET_PROJECT"],
        "UID": S["ASSIGNEE_ID"]
    }
except Exception as e:
    st.error(f"❌ Secrets 載入失敗: {e}")
    st.stop()

# Jira 初始化
jira = JIRA(server=conf["J_SERVER"], basic_auth=(conf["J_EMAIL"], conf["J_TOKEN"]))

# --- 2. 議題列表 (確保資料源正確) ---
st.subheader(f"🔍 當前追蹤議題 (專案: {conf['PROJ']})")
jql = f'project = "{conf["PROJ"]}" AND assignee = "{conf["UID"]}" ORDER BY created DESC'
issues = jira.search_issues(jql, maxResults=5)

if issues:
    st.table([{"Key": i.key, "Summary": i.fields.summary, "Status": i.fields.status.name} for i in issues])
    initial_key = issues[0].key
else:
    st.warning("目前無符合條件的議題。")
    initial_key = None

st.divider()

# --- 3. 機器人核心邏輯 ---
if 'bot_status' not in st.session_state:
    st.session_state.bot_status = "未啟動"
if 'logs' not in st.session_state:
    st.session_state.logs = []

def add_log(msg):
    now = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{now}] {msg}")

class JiraBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.last_key = initial_key

    async def on_ready(self):
        add_log(f"✅ 機器人成功登入: {self.user.name}")
        st.session_state.bot_status = "🟢 運行中"
        
        # 嘗試發送啟動測試訊息
        channel = self.get_channel(conf["CH_ID"])
        if channel:
            await channel.send("🚀 **Jira 監控機器人已在 Streamlit 上線！**")
            add_log("📬 已在 Discord 頻道發送上線通知")
        else:
            add_log("❌ 找不到頻道，請確認 Bot 已加入該伺服器且 ID 正確")

    async def setup_hook(self):
        self.check_loop.start()

    @tasks.loop(minutes=1)
    async def check_loop(self):
        try:
            # 每分鐘抓取最新一筆
            current_issues = jira.search_issues(jql, maxResults=1)
            if current_issues:
                new_key = current_issues[0].key
                if self.last_key and new_key != self.last_key:
                    self.last_key = new_key
                    channel = self.get_channel(conf["CH_ID"])
                    if channel:
                        await channel.send(f"🔔 **新任務指派**: {new_key}\n{current_issues[0].fields.summary}")
                        add_log(f"🔥 發現新任務並通知: {new_key}")
                else:
                    add_log("💤 掃描中: 暫無變動")
        except Exception as e:
            add_log(f"❌ 掃描出錯: {e}")

# --- 4. 啟動器 ---
st.subheader(f"🤖 機器人控制台 (狀態: {st.session_state.bot_status})")

if st.button("🚀 啟動監控機器人"):
    if st.session_state.bot_status == "未啟動":
        def start_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            bot = JiraBot()
            try:
                bot.run(conf["D_TOKEN"])
            except Exception as e:
                add_log(f"❌ 啟動崩潰: {e}")

        t = threading.Thread(target=start_thread, daemon=True)
        t.start()
        st.session_state.bot_status = "⏳ 啟動中..."
        add_log("⏳ 執行緒已開啟，嘗試登入 Discord...")
        time.sleep(2)
        st.rerun()
    else:
        st.info("機器人正在運作或啟動中。")

# 顯示日誌
st.text_area("Live Logs", value="\n".join(st.session_state.logs[::-1]), height=250)

if st.button("🔄 刷新日誌"):
    st.rerun()
