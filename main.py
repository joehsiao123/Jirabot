import streamlit as st
import discord
from discord.ext import commands, tasks
from jira import JIRA
import threading
import asyncio
from datetime import datetime

# --- 1. 設定與初始化 ---
st.set_page_config(page_title="Jira-Discord 監控中心", page_icon="🤖")

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
        "TARGET_PROJ_B": S.get("TARGET_PROJECT_B", "PROJB") # 預留轉發專案
    }
except Exception as e:
    st.error(f"❌ Secrets 載入失敗，請檢查設定: {e}")
    st.stop()

# --- 2. 互動按鈕元件 ---
class JiraActionView(discord.ui.View):
    def __init__(self, issue_key, summary, jira_instance):
        super().__init__(timeout=None) # 按鈕永久有效直到程式重啟
        self.issue_key = issue_key
        self.summary = summary
        self.jira = jira_instance

    @discord.ui.button(label="Report to Project B", style=discord.ButtonStyle.primary, emoji="🚀")
    async def report_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # 執行轉發邏輯
            new_issue = self.jira.create_issue(
                project=CONF["TARGET_PROJ_B"],
                summary=f"[Fwd] {self.summary}",
                description=f"由 Discord 轉發自 {self.issue_key}",
                issuetype={'name': 'Task'}
            )
            # 建立 Issue Link
            self.jira.create_issue_link(type="Relates", inwardIssue=new_issue.key, outwardIssue=self.issue_key)
            
            await interaction.response.send_message(f"✅ 已成功轉發至 {new_issue.key}！", ephemeral=True)
            self.stop()
        except Exception as e:
            await interaction.response.send_message(f"❌ 轉發失敗: {e}", ephemeral=True)

    @discord.ui.button(label="忽略", style=discord.ButtonStyle.secondary)
    async def ignore(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("已忽略該議題。", ephemeral=True)
        self.stop()

# --- 3. Discord 機器人主程式 ---
class JiraMonitorBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.last_seen_key = None
        self.logs = []
        self.jira = JIRA(server=CONF["J_SERVER"], basic_auth=(CONF["J_EMAIL"], CONF["J_TOKEN"]))

    def add_log(self, msg):
        now = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{now}] {msg}")
        if len(self.logs) > 20: self.logs.pop(0)

    async def setup_hook(self):
        self.add_log("🤖 監控任務已啟動...")
        self.check_jira_task.start()

    @tasks.loop(minutes=CONF["TIME"])
    async def check_jira_task(self):
        try:
            # JQL: 搜尋指定專案且指派給指定 ID 的最新 Issue
            jql = f'project = "{CONF["PROJ"]}" AND assignee = "{CONF["UID"]}" ORDER BY created DESC'
            issues = self.jira.search_issues(jql, maxResults=1)

            if issues:
                current_issue = issues[0]
                
                # 初始執行時，只記錄最新 ID
                if self.last_seen_key is None:
                    self.last_seen_key = current_issue.key
                    self.add_log(f"📍 初始標記完成: {current_issue.key}")
                    return

                # 發現新 Issue
                if current_issue.key != self.last_seen_key:
                    self.last_seen_key = current_issue.key
                    channel = self.get_channel(CONF["CH_ID"])
                    
                    if channel:
                        embed = discord.Embed(
                            title="🔔 偵測到新指派任務",
                            description=f"**[{current_issue.key}]** {current_issue.fields.summary}",
                            color=discord.Color.blue(),
                            url=f"{CONF['J_SERVER']}/browse/{current_issue.key}"
                        )
                        embed.set_footer(text="點擊下方按鈕決定是否轉發")
                        
                        view = JiraActionView(current_issue.key, current_issue.fields.summary, self.jira)
                        await channel.send(embed=embed, view=view)
                        self.add_log(f"🚀 已通知新議題: {current_issue.key}")
            else:
                self.add_log("🔍 掃描中：目前無新任務")
        except Exception as e:
            self.add_log(f"❌ 錯誤: {e}")

# --- 4. Streamlit 介面與啟動器 ---
st.title("Jira 🔍 Discord 監控面板")

if "bot" not in st.session_state:
    st.session_state.bot = JiraMonitorBot()
    
    def run_bot():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        st.session_state.bot.run(CONF["D_TOKEN"])
    
    # 啟動背景執行緒
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    st.toast("機器人啟動中...", icon="🤖")

# UI 顯示區
col1, col2 = st.columns(2)
with col1:
    st.metric("監控專案", CONF["PROJ"])
    st.metric("檢查頻率", f"{CONF['TIME']} 分鐘")
with col2:
    st.metric("當前狀態", "🟢 運行中" if any(t.is_alive() for t in threading.enumerate()) else "🔴 停止")
    st.metric("最後抓取", st.session_state.bot.last_seen_key or "等待中")

st.divider()
st.subheader("📝 運行日誌")
# 建立一個動態更新的容器
log_box = st.container(height=300)
with log_box:
    for l in reversed(st.session_state.bot.logs):
        st.write(l)

if st.button("🔄 手動刷新畫面"):
    st.rerun()
