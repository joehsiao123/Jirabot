import streamlit as st
from jira import JIRA
import discord
from discord.ext import commands, tasks
import asyncio
import threading
from datetime import datetime

# --- 1. 頁面初始化 ---
st.set_page_config(page_title="Jira 任務清單與機器人", layout="wide")
st.title("📋 Jira 議題清單 & 機器人控制台")

# 讀取 Secrets
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

# 初始化 Jira 連線
@st.cache_resource
def get_jira():
    return JIRA(server=conf["J_SERVER"], basic_auth=(conf["J_EMAIL"], conf["J_TOKEN"]))

jira = get_jira()

# --- 2. 展示符合條件的 Issue List ---
st.header(f"🔍 目前符合條件的 Issue (專案: {conf['PROJ']})")

try:
    # JQL: 指定專案、指定負責人、按建立時間排序
    jql = f'project = "{conf["PROJ"]}" AND assignee = "{conf["UID"]}" ORDER BY created DESC'
    issues = jira.search_issues(jql, maxResults=5)

    if issues:
        # 使用表格顯示
        issue_data = []
        for issue in issues:
            issue_data.append({
                "Key": issue.key,
                "Summary": issue.fields.summary,
                "Status": issue.fields.status.name,
                "Created": issue.fields.created[:10],
                "Link": f"{conf['J_SERVER']}/browse/{issue.key}"
            })
        st.table(issue_data)
        st.success(f"✅ 成功找到 {len(issues)} 筆相符的議題")
    else:
        st.warning("⚠️ 目前 Jira 上沒有符合條件 (Assignee + Project) 的 Issue。")
        st.info(f"當前搜尋條件: `{jql}`")

except Exception as e:
    st.error(f"❌ Jira 資料抓取失敗: {e}")

st.divider()

# --- 3. Discord 機器人邏輯 ---
st.header("🤖 機器人監控狀態")

if 'bot_logs' not in st.session_state:
    st.session_state.bot_logs = []

def add_log(msg):
    now = datetime.now().strftime("%H:%M:%S")
    st.session_state.bot_logs.append(f"[{now}] {msg}")

class JiraBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.last_key = issues[0].key if issues else None

    async def setup_hook(self):
        self.check_loop.start()

    @tasks.loop(minutes=1)
    async def check_loop(self):
        try:
            # 再次檢查最新一筆
            check_issues = jira.search_issues(jql, maxResults=1)
            if check_issues:
                new_key = check_issues[0].key
                if self.last_key and new_key != self.last_key:
                    self.last_key = new_key
                    channel = self.get_channel(conf["CH_ID"])
                    if channel:
                        await channel.send(f"🚨 **偵測到新指派議題**: {new_key}\n標題: {check_issues[0].fields.summary}")
                        add_log(f"📩 已發送 Discord 通知: {new_key}")
                else:
                    add_log("🔍 每分鐘檢查中：尚無新議題")
        except Exception as e:
            add_log(f"❌ 檢查出錯: {e}")

# 啟動按鈕
if "bot_running" not in st.session_state:
    st.session_state.bot_running = False

if st.button("🚀 啟動 Discord 機器人即時監控"):
    if not st.session_state.bot_running:
        def run_bot():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            bot = JiraBot()
            bot.run(conf["D_TOKEN"])
        
        thread = threading.Thread(target=run_bot, daemon=True)
        thread.start()
        st.session_state.bot_running = True
        st.success("機器人已在背景啟動！每分鐘將自動比對一次。")
    else:
        st.info("機器人已經在運行中。")

# 日誌顯示
if st.session_state.bot_running:
    st.subheader("📝 機器人運行日誌")
    if st.button("刷新日誌"):
        st.rerun()
    st.text_area("Logs", value="\n".join(st.session_state.bot_logs[::-1]), height=200)
