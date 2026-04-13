import streamlit as st
from jira import JIRA
import discord
import asyncio
from datetime import datetime

st.set_page_config(page_title="Jira 診斷器", layout="wide")
st.title("🔍 Jira + Discord 終極連線診斷")

# --- 1. 檢查 Secrets 讀取 ---
st.header("1. 環境變數檢查")
try:
    creds = {
        "JIRA_SERVER": st.secrets["JIRA_SERVER"],
        "JIRA_EMAIL": st.secrets["JIRA_EMAIL"],
        "JIRA_API_TOKEN": st.secrets["JIRA_API_TOKEN"],
        "DISCORD_TOKEN": st.secrets["DISCORD_TOKEN"],
        "CHANNEL_ID": st.secrets["CHANNEL_ID"],
        "TARGET_PROJECT": st.secrets["TARGET_PROJECT"],
        "ASSIGNEE_ID": st.secrets["ASSIGNEE_ID"]
    }
    st.success("✅ Secrets 讀取成功")
except Exception as e:
    st.error(f"❌ Secrets 讀取失敗: {e}")
    st.info("請檢查 Streamlit Cloud 控制台的 Settings -> Secrets 是否已填寫。")
    st.stop()

# --- 2. 手動診斷按鈕 ---
st.header("2. 執行連線測試")
if st.button("🚀 立即開始診斷"):
    
    # --- A. 測試 Jira ---
    st.subheader("📡 Jira 連線測試")
    try:
        with st.status("正在連線至 Jira...", expanded=True) as status:
            jira = JIRA(server=creds["JIRA_SERVER"], basic_auth=(creds["JIRA_EMAIL"], creds["JIRA_API_TOKEN"]))
            myself = jira.myself()
            st.write(f"✅ 連線成功！登入身分: **{myself['displayName']}**")
            
            # 測試專案權限
            project = jira.project(creds["TARGET_PROJECT"])
            st.write(f"✅ 找到專案: **{project.name}**")
            
            # 測試 JQL (不加 Assignee 試試看)
            st.write("🔍 正在嘗試不限制負責人搜尋最新議題...")
            issues_any = jira.search_issues(f'project = "{creds["TARGET_PROJECT"]}" ORDER BY created DESC', maxResults=1)
            if issues_any:
                latest = issues_any[0]
                real_assignee = latest.fields.assignee.accountId if latest.fields.assignee else "未指派"
                st.write(f"📌 專案最新議題: `{latest.key}`")
                st.code(f"該議題的正確 Assignee ID 是: {real_assignee}", language="text")
                
                if str(real_assignee) == str(creds["ASSIGNEE_ID"]):
                    st.success("🎯 你的 ASSIGNEE_ID 匹配成功！")
                else:
                    st.warning("⚠️ 你的 ASSIGNEE_ID 與最新議題的負責人不符，請確認是否填錯。")
            else:
                st.error("❌ 專案內似乎沒有任何議題。")
            status.update(label="Jira 診斷完成", state="complete")
    except Exception as e:
        st.error(f"❌ Jira 階段出錯: {e}")

    # --- B. 測試 Discord ---
    st.subheader("💬 Discord 發送測試")
    async def send_test_msg():
        try:
            intents = discord.Intents.default()
            client = discord.Client(intents=intents)
            
            # 我們不使用 client.run() 因為它會阻塞，這裡只測試發送訊息
            await client.login(creds["DISCORD_TOKEN"])
            channel = await client.fetch_channel(int(creds["CHANNEL_ID"]))
            await channel.send(f"✅ **Jira 診斷測試成功**\n測試時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            await client.close()
            return True
        except Exception as e:
            return str(e)

    with st.status("正在嘗試發送 Discord 訊息...") as status:
        result = asyncio.run(send_test_msg())
        if result is True:
            st.success("✅ Discord 測試訊息已送出！請檢查你的頻道。")
            status.update(label="Discord 測試成功", state="complete")
        else:
            st.error(f"❌ Discord 階段出錯: {result}")
            status.update(label="Discord 測試失敗", state="error")

st.divider()
st.info("💡 如果點擊按鈕後出現錯誤訊息，請根據錯誤提示修改你的 Secrets。如果連按鈕都沒出現，請確認 GitHub 上的檔案名稱是否為 app.py。")
