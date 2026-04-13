import streamlit as st
import discord
from discord.ext import commands, tasks
from jira import JIRA
import threading
import asyncio
from datetime import datetime
import traceback

# --- 頁面配置 ---
st.set_page_config(page_title="Jira Bot Debugger", layout="wide")
st.title("🛠️ Jira 機器人診斷監控面板")

# --- 1. 安全讀取 Secrets ---
try:
    CONFIG = {
        "DISCORD_TOKEN": st.secrets["DISCORD_TOKEN"],
        "CHANNEL_ID": int(st.secrets["CHANNEL_ID"]),
        "JIRA_SERVER": st.secrets["JIRA_SERVER"],
        "JIRA_EMAIL": st.secrets["JIRA_EMAIL"],
        "JIRA_API_TOKEN": st.secrets["JIRA_API_TOKEN"],
        "TARGET_PROJECT": st.secrets["TARGET_PROJECT"],
        "ASSIGNEE_ID": st.secrets["ASSIGNEE_ID"],
        "INTERVAL": int(st.secrets.get("CHECK_INTERVAL", 1))
    }
    st.sidebar.success("✅ Secrets 載入成功")
except Exception as e:
    st.error(f"❌ Secrets 設定錯誤: {e}")
    st.stop()

# --- 2. Discord 機器人類別 ---
class DebugJiraBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.last_seen_key = None
        self.logs = []
        self.is_running = False
        
        # 建立 Jira 連線
        try:
            self.jira = JIRA(
                server=CONFIG["JIRA_SERVER"], 
                basic_auth=(CONFIG["JIRA_EMAIL"], CONFIG["JIRA_API_TOKEN"])
            )
        except Exception as e:
            self.add_log(f"CRITICAL: Jira 連線失敗 - {e}")

    def add_log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {msg}"
        self.logs.append(full_msg)
        print(full_msg) # 同時印在後台終端機

    async def setup_hook(self):
        self.add_log("🤖 Discord Bot 正在初始化 Hook...")
        self.check_jira.start()

    @tasks.loop(minutes=CONFIG["INTERVAL"])
    async def check_jira(self):
        self.add_log("🔍 開始一輪 Jira 掃描...")
        try:
            # 診斷 1: 測試 Jira 身分
            myself = self.jira.myself()
            self.add_log(f"👤 已登入 Jira: {myself['displayName']} ({myself['emailAddress']})")

            # 診斷 2: 檢查專案是否存在
            project = self.jira.project(CONFIG["TARGET_PROJECT"])
            self.add_log(f"📁 找到專案: {project.name}")

            # 診斷 3: 執行 JQL 搜尋
            jql = f'project = "{CONFIG["TARGET_PROJECT"]}" AND assignee = "{CONFIG["ASSIGNEE_ID"]}" ORDER BY created DESC'
            self.add_log(f"🔎 執行 JQL: {jql}")
            
            issues = self.jira.search_issues(jql, maxResults=1)
            
            if not issues:
                self.add_log("⚠️ 結果為空！請確認 Assignee ID 是否正確。")
                # 額外嘗試：搜尋該專案的所有 Issue 
                all_issues = self.jira.search_issues(f'project = "{CONFIG["TARGET_PROJECT"]}"', maxResults=1)
                if all_issues:
                    correct_assignee = all_issues[0].fields.assignee
                    self.add_log(f"💡 建議：專案中最新 Issue 的負責人 ID 為: {correct_assignee.accountId if correct_assignee else '未指派'}")
                return

            current_issue = issues[0]
            self.add_log(f"✅ 成功抓取最新 Issue: {current_issue.key}")

            # 檢查是否為新議題
            if self.last_seen_key is None:
                self.last_seen_key = current_issue.key
                self.add_log(f"📍 初始標記完成，將從下一張新 Issue 開始通知。")
                return

            if current_issue.key != self.last_seen_key:
                old_key = self.last_seen_key
                self.last_seen_key = current_issue.key
                self.add_log(f"🔥 偵測到新變動! {old_key} -> {current_issue.key}")
                
                # 發送 Discord 通知
                channel = self.get_channel(CONFIG["CHANNEL_ID"])
                if channel:
                    embed = discord.Embed(title="New Jira Assigned!", color=0x00ff00)
                    embed.add_field(name="Summary", value=current_issue.fields.summary)
                    embed.description = f"[點我查看議題]({CONFIG['JIRA_SERVER']}/browse/{current_issue.key})"
                    await channel.send(embed=embed)
                    self.add_log("📩 Discord 訊息已送出")
                else:
                    self.add_log(f"❌ 找不到頻道 ID: {CONFIG['CHANNEL_ID']}，請確認 Bot 是否在該伺服器。")

        except Exception as e:
            self.add_log(f"❌ 發生錯誤: {str(e)}")
            self.add_log(traceback.format_exc()) # 印出詳細錯誤堆疊

# --- 3. Streamlit 運行邏輯 ---
if "bot" not in st.session_state:
    st.session_state.bot = DebugJiraBot()

def start_bot_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        st.session_state.bot.run(CONFIG["DISCORD_TOKEN"])
    except Exception as e:
        print(f"Bot 執行出錯: {e}")

if not any(t.name == "DiscordBotThread" for t in threading.enumerate()):
    bot_thread = threading.Thread(target=start_bot_thread, name="DiscordBotThread", daemon=True)
    bot_thread.start()
    st.sidebar.success("🚀 機器人執行緒已啟動")

# --- 4. 儀表板 UI ---
st.header("📋 運行日誌")
if st.button("🔄 刷新頁面資訊"):
    st.rerun()

# 顯示日誌內容
log_container = st.container()
with log_container:
    if st.session_state.bot.logs:
        for l in reversed(st.session_state.bot.logs):
            if "❌" in l or "CRITICAL" in l:
                st.error(l)
            elif "⚠️" in l or "💡" in l:
                st.warning(l)
            elif "✅" in l or "📩" in l:
                st.success(l)
            else:
                st.text(l)
    else:
        st.info("等待日誌產生中... (每分鐘檢查一次)")

# 顯示當前變數狀態（Debug 用）
with st.expander("查看當前連線變數"):
    st.write(f"**Jira Server:** {CONFIG['JIRA_SERVER']}")
    st.write(f"**Target Project:** {CONFIG['TARGET_PROJECT']}")
    st.write(f"**Assignee ID:** {CONFIG['ASSIGNEE_ID']}")
    st.write(f"**Last Seen Key:** {st.session_state.bot.last_seen_key}")
