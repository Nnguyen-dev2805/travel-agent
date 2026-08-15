# pyrefly: ignore [missing-import]
import streamlit as st
import requests
import json
import uuid
import os
import re

# Configuration
API_BASE_URL = "http://localhost:8080/api/v1"
LOGIN_EMAIL = "user@travel.vn"
LOGIN_PASSWORD = "password123"
LOG_FILE_PATH = "data/debug.log"

st.set_page_config(page_title="Travel Agent - AI Debugger", page_icon="🧠", layout="wide")

# --- Initialize Session State ---
if "token" not in st.session_state:
    st.session_state.token = None
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "debug_info" not in st.session_state:
    st.session_state.debug_info = None

# --- Helper Functions ---
def login():
    try:
        # Try to register first, just in case
        requests.post(f"{API_BASE_URL}/auth/register", json={
            "email": LOGIN_EMAIL,
            "password": LOGIN_PASSWORD,
            "full_name": "Streamlit Debug User"
        })
        
        # Login
        res = requests.post(f"{API_BASE_URL}/auth/login", json={
            "email": LOGIN_EMAIL,
            "password": LOGIN_PASSWORD
        })
        if res.status_code == 200:
            st.session_state.token = res.json()["access_token"]
        else:
            st.error("Login failed! Ensure the backend is running.")
    except Exception as e:
        st.error(f"Connection error: {e}")

def send_message(user_message: str):
    headers = {"Content-Type": "application/json"}
    if st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
        
    payload = {
        "message": user_message,
        "session_id": st.session_state.session_id
    }
    
    try:
        res = requests.post(f"{API_BASE_URL}/chat", json=payload, headers=headers)
        if res.status_code == 200:
            data = res.json()
            reply = data.get("reply", "")
            debug = data.get("debug_info", None)
            return reply, debug
        else:
            return f"Error: {res.text}", None
    except Exception as e:
        return f"Error connecting to backend: {str(e)}", None

def parse_debug_log(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Regex to find blocks surrounded by '==== TITLE ====' and '================='
    pattern = r"={20}\s+(.*?)\s+={20}\n(.*?)\n={50,}"
    matches = re.findall(pattern, content, re.DOTALL)
    return matches

# --- UI Layout ---
if not st.session_state.token:
    with st.spinner("Logging in to backend..."):
        login()

# Top Header
st.title("🧠 AI Memory & RAG Debugger")
st.markdown("Giao diện giám sát quá trình suy nghĩ của AI theo thời gian thực.")

col1, col2 = st.columns([5, 5])

# --- Column 1: Chat Interface ---
with col1:
    st.subheader("Trò chuyện")
    
    # Render chat history
    chat_container = st.container(height=600)
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                
    # Input
    if prompt := st.chat_input("Nhập câu hỏi của bạn... (vd: Tôi bị dị ứng hải sản)"):
        # Add user msg to state
        st.session_state.messages.append({"role": "user", "content": prompt})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)
                
            with st.chat_message("assistant"):
                with st.spinner("AI đang phân tích..."):
                    reply, debug_info = send_message(prompt)
                    st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                    st.session_state.debug_info = debug_info

# --- Column 2: Debug Inspector ---
with col2:
    st.subheader("🕵️ AI Inspector")
    
    tab1, tab2 = st.tabs(["⚡ Live Traces (All)", "📦 API Response (Sync)"])
    
    with tab2:
        if st.session_state.debug_info:
            debug = st.session_state.debug_info
            
            router = debug.get("router_decision")
            if router:
                with st.expander("🚦 Router Decision", expanded=True):
                    st.json(router)
                    
            facts = debug.get("user_facts")
            if facts:
                with st.expander("🧠 Retrieved Memory (Facts & Episodes)", expanded=True):
                    st.text(facts)
                    
            rag_used = debug.get("rag_context_used")
            with st.expander("📚 RAG Status", expanded=True):
                if rag_used:
                    st.success("RAG Context was searched and injected.")
                else:
                    st.info("RAG was bypassed for this query.")
                    
        else:
            st.info("Chưa có dữ liệu Debug đồng bộ. Hãy gửi một tin nhắn bên trái.")
            
    with tab1:
        st.markdown("**Toàn bộ luồng Input/Output (bao gồm Background Tasks):**")
        if st.button("🔄 Tải lại luồng chạy ngầm", help="Nhấn để cập nhật các tiến trình ngầm như Fact Extraction"):
            pass # Rerun trigger
            
        traces = parse_debug_log(LOG_FILE_PATH)
        if not traces:
            st.info("Chưa có dữ liệu trong file log. Vui lòng chat để tạo log mới.")
        else:
            # Render blocks reversed (newest on top)
            for title, content in reversed(traces):
                with st.expander(f"📌 {title}", expanded=("OUTPUT" in title)):
                    if "OUTPUT" in title and "{" in content and "}" in content:
                        try:
                            # Try pretty printing JSON if it's JSON
                            st.json(json.loads(content))
                        except:
                            st.code(content, language="markdown")
                    else:
                        st.code(content, language="markdown")

    st.markdown("---")
    colA, colB = st.columns(2)
    with colA:
        if st.button("🗑️ Xóa lịch sử phiên chat"):
            st.session_state.messages = []
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.debug_info = None
            st.rerun()
    with colB:
        if st.button("🧹 Xóa trắng File Log"):
            with open(LOG_FILE_PATH, "w") as f:
                f.write("")
            st.success("Đã xóa log!")
            st.rerun()
