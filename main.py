import streamlit as st
import discord
from discord.ext import commands, tasks
from jira import JIRA
import threading
import asyncio
from datetime import datetime

# --- 1. 初始化與設定 ---
# 在 Streamlit Cloud 上，這些資訊會從 Secrets 讀取
try:
    DISCORD_TOKEN = st.secrets["DISCORD_TOKEN"]
    CHANNEL_ID = int(st.secrets["CHANNEL_ID"])
    JIRA_SERVER = st.secrets["JIRA_SERVER"]
    JIRA_EMAIL = st.secrets["JIRA_EMAIL"]
    JIRA_API_TOKEN = st.secrets["JIRA_API_TOKEN"]
    
    # 篩選條件
    TARGET_PROJECT = st.secrets["TARGET_PROJECT"] # 例如: 'PROJ'
    ASSIGNEE_ID = st.secrets["ASSIGNEE_ID"] # Jira 使用者的 Account ID 或 Email
    INTERVAL = int(st.secrets.get("CHECK_INTERVAL", 1))
except Exception as e:
    st.error("❌ 找不到 Secrets 設定，請確認 .streamlit/secrets.toml 或 Streamlit 後台設定。")
    st.stop()

# 初始化 Jira 連線
jira = JIRA(server=JIRA_SERVER, basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN))

# --- 2. Discord 機器人邏輯 ---
class JiraBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.last_seen_key = None
        self.logs = []

    def add_log(self, msg):
        now = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{now}] {msg}")
        if len(self.logs) > 10: self.logs.pop(0)

    async def setup_hook(self):
        self.check_jira.start()

    @tasks.loop(minutes=INTERVAL)
    async def check_jira(self):
        channel = self.get_channel(CHANNEL_ID)
        if not channel: return

        # JQL: 指定專案 + 指定負責人 + 按建立時間排序
        jql = f'project = "{TARGET_PROJECT}" AND assignee = "{ASSIGNEE_ID}" ORDER BY created DESC'
        
        try:
            issues = jira.search_issues(jql, maxResults=1)
            if issues:
                new_issue = issues[0]
                
                if self.last_seen_key is None:
                    self.last_seen_key = new_issue.key
                    self.add_log(f"系統啟動，監控中。目前最新: {new_issue.key}")
                    return

                if new_issue.key != self.last_seen_key:
                    self.last_seen_key = new_issue.key
                    
                    # 發送通知到 Discord
                    embed = discord.Embed(title="🔔 發現指派給你的新議題", color=discord.Color.green())
                    embed.add_field(name="Issue", value=f"[{new_issue.key}]({JIRA_SERVER}/browse/{new_issue.key})", inline=False)
                    embed.add_field(name="標題", value=new_issue.fields.summary, inline=False)
                    
                    view = JiraActionView(new_issue.key, new_issue.fields.summary)
                    await channel.send(embed=embed, view=view)
                    self.add_log(f"🚀 已通知新議題: {new_issue.key}")
            else:
                self.add_log("檢查完畢：目前無符合條件的議題")
        except Exception as e:
            self.add_log(f"❌ Jira 檢查出錯: {e}")

# Discord 互動按鈕
class JiraActionView(discord.ui.View):
    def __init__(self, key, summary):
        super().__init__(timeout=None)
        self.key = key
        self.summary = summary

    @discord.ui.button(label="Report to Project B", style=discord.ButtonStyle.primary)
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 這裡執行轉發到另一個專案的動作 (範例：ProjectB)
        # 實際實作可參考之前的 jira.create_issue 邏輯
        await interaction.response.send_message(f"已記錄轉發請求: {self.key}", ephemeral=True)

# --- 3. Streamlit 介面 ---
st.title("Jira 🔍 Discord 通知中心")

if "bot" not in st.session_state:
    st.session_state.bot = JiraBot()
    
    def run_bot():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        st.session_state.bot.run(DISCORD_TOKEN)
    
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    st.success("🤖 Discord 機器人已在背景啟動")

st.metric("監控專案", TARGET_PROJECT)
st.metric("負責人 ID", ASSIGNEE_ID)

st.subheader("📝 即時運行日誌")
for log in reversed(st.session_state.bot.logs):
    st.text(log)

if st.button("手動重新整理網頁"):
    st.rerun()
