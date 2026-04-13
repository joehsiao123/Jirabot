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
st.title("📋 Jira 列表同步 & Discord 機器人")

try:
    S = st.secrets
    conf = {
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

# --- 2. 機器人核心邏輯 ---
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
        self.jira = JIRA(server=conf["J_SERVER"], basic_auth=(conf["J_EMAIL"], conf["J_TOKEN"]))
        self.last_key = None

    async def on_ready(self):
        add_log(f"✅ 機器人成功登入: {self.user.name}")
        channel = self.get_channel(conf["CH_ID"])
        
        if channel:
            try:
                # 1. 抓取當前清單
                jql = f'project = "{conf["PROJ"]}" AND assignee = "{conf["UID"]}" ORDER BY created DESC'
                issues = self.jira.search_issues(jql, maxResults=5)
                
                if issues:
                    self.last_key = issues[0].key # 標記目前最新的一筆
                    
                    # 2. 格式化訊息
                    msg = f"📋 **當前 Jira 待辦清單 (專案: {conf['PROJ']})**\n"
                    msg += "------------------------------------------\n"
                    for i in issues:
                        msg += f"🔹 **[{i.key}]** {i.fields.summary} (`{i.fields.status.name}`)\n"
                    msg += "------------------------------------------\n"
                    msg += "✨ *機器人已進入即時監控模式...*"
                    
                    await channel.send(msg)
                    add_log("📬 已將初始列表同步至 Discord")
                else:
                    await channel.send(f"✅ 機器人已上線，但目前在專案 `{conf['PROJ']}` 中找不到指派給你的任務。")
                    add_log("⚠️ 找不到任務，已發送空列表通知")
            except Exception as e:
                add_log(f"❌ 初始發送失敗: {e}")
        else:
            add_log("❌ 找不到 Discord 頻道，請確認 ID 與權限")

    async def setup_hook(self):
        self.check_loop.start()

    @tasks.loop(minutes=conf["TIME"])
    async def check_loop(self):
        # 這裡維持每分鐘檢查是否有「新」Issue 的邏輯
        try:
            jql = f'project = "{conf["PROJ"]}" AND assignee = "{conf["UID"]}" ORDER BY created DESC'
            current_issues = self.jira.search_issues(jql, maxResults=1)
            if current_issues:
                new_key = current_issues[0].key
                if self.last_key and new_key != self.last_key:
                    self.last_key = new_key
                    channel = self.get_channel(conf["CH_ID"])
                    if channel:
                        await channel.send(f"🔔 **偵測到新任務！**\n**[{new_key}]** {current_issues[0].fields.summary}")
                        add_log(f"🔥 發現新變動: {new_key}")
        except Exception as e:
            add_log(f"❌ 輪詢出錯: {e}")

# --- 3. Streamlit 介面 ---
if 'bot_started' not in st.session_state:
    st.session_state.bot_started = False

if st.button("🚀 啟動機器人並同步列表"):
    if not st.session_state.bot_started:
        def start_bot():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            bot = JiraBot()
            bot.run(conf["D_TOKEN"])
        
        thread = threading.Thread(target=start_bot, daemon=True)
        thread.start()
        st.session_state.bot_started = True
        add_log("⏳ 正在啟動執行緒...")
        time.sleep(1)
        st.rerun()

st.subheader("📝 運行日誌")
st.text_area("Logs", value="\n".join(st.session_state.logs[::-1]), height=300)

if st.button("🔄 刷新頁面"):
    st.rerun()
