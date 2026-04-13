import streamlit as st
from jira import JIRA
import discord
import asyncio
from datetime import datetime

# --- 1. 設定與初始化 ---
st.set_page_config(page_title="Jira Discord 同步器", layout="wide")
st.title("🚀 Jira 列表直發 Discord")

try:
    S = st.secrets
    conf = {
        "D_TOKEN": S["DISCORD_TOKEN"],
        "CH_ID": int(S["CHANNEL_ID"]),
        "J_SERVER": S["JIRA_SERVER"],
        "J_EMAIL": S["JIRA_EMAIL"],
        "J_TOKEN": S["JIRA_API_TOKEN"],
        "PROJ": S["TARGET_PROJECT"],
        "UID": S["ASSIGNEE_ID"]
    }
except Exception as e:
    st.error(f"❌ Secrets 載入失敗: {e}")
    st.stop()

# --- 2. 核心功能函式 (不使用執行緒) ---

async def send_jira_list_to_discord():
    """負責連線 Jira、抓取列表並透過 Discord 送出的非同步函式"""
    try:
        # A. 抓取 Jira 資料
        with st.spinner("正在從 Jira 抓取資料..."):
            jira = JIRA(server=conf["J_SERVER"], basic_auth=(conf["J_EMAIL"], conf["J_TOKEN"]))
            jql = f'project = "{conf["PROJ"]}" AND assignee = "{conf["UID"]}" ORDER BY created DESC'
            issues = jira.search_issues(jql, maxResults=5)
        
        if not issues:
            st.warning("⚠️ Jira 上沒有符合條件的議題。")
            return

        # B. 格式化訊息
        msg = f"📋 **Jira 任務列表 (專案: {conf['PROJ']})**\n"
        msg += "------------------------------------------\n"
        for i in issues:
            msg += f"🔹 **[{i.key}]** {i.fields.summary} (`{i.fields.status.name}`)\n"
        msg += "------------------------------------------\n"
        msg += f"⏰ 更新時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        # C. 透過 Discord 送出 (短連接，送完即關閉)
        with st.spinner("正在連線 Discord 並發送..."):
            intents = discord.Intents.default()
            client = discord.Client(intents=intents)
            
            await client.login(conf["D_TOKEN"])
            channel = await client.fetch_channel(conf["CH_ID"])
            await channel.send(msg)
            await client.close()
            
        st.success("✅ 列表已成功同步至 Discord 頻道！")
        
    except Exception as e:
        st.error(f"❌ 執行過程中出錯: {e}")

# --- 3. UI 介面 ---

st.info(f"當前監控：{conf['PROJ']} / 負責人：{conf['UID']}")

if st.button("📤 立即抓取列表並發送到 Discord"):
    # 在 Streamlit 中直接執行非同步函式 (同步阻塞式等待結果)
    asyncio.run(send_jira_list_to_discord())

st.divider()
st.caption("此版本不使用背景執行緒，每次點擊按鈕才會執行一次同步。")
