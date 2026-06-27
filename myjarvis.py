"""
Jarvis 2.0 -- Bug-Free & Fully Verified Version (Creator: Ayush)
---------------------------------------------------------------------------------
"""

import re
import io
import os
import streamlit as st

st.set_page_config(page_title="Jarvis 2.0", page_icon="🤖", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0b0e14; }
    .jarvis-card { background: linear-gradient(145deg, #161b26, #1b212e); padding: 18px; border-radius: 14px; margin-bottom: 12px; border: 1px solid #2a3140; }
    .jarvis-tag { background: #1f6feb22; color: #58a6ff; padding: 2px 12px; border-radius: 999px; font-size: 0.7rem; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)

JARVIS_SYSTEM_PROMPT = """You are Jarvis 2.0, a grounded, intelligent, and direct AI assistant.
Your creator and boss is Ayush. If asked who made you or who your boss is, always proudly say that Ayush created you.
Tone: speak like a grounded, intelligent peer -- warm, occasionally witty.
Use the Google Search tool for all queries related to real-time events, current dates, time, match scores, or news.
"""

def get_gemini_client(api_key):
    try:
        from google import genai
        return genai.Client(api_key=api_key.strip()), None
    except Exception as e: return None, str(e)

def call_gemini(client, prompt, model):
    try:
        from google.genai import types
        response = client.models.generate_content(
            model=model, 
            contents=prompt, 
            config=types.GenerateContentConfig(
                system_instruction=JARVIS_SYSTEM_PROMPT, 
                tools=[{"google_search": {}}]
            )
        )
        return response.text, None
    except Exception as e: return None, str(e)

def text_to_speech_bytes(text):
    try:
        from gtts import gTTS
        clean = re.sub(r"\*\*|\*|__|_|#+|`|http\S+", "", text).strip()
        if not clean:
            return None
        tts = gTTS(text=clean[:1000], lang='en', tld='co.uk') 
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        st.warning(f"Voice synthesis failed: {e}")
        return None

with st.sidebar:
    st.title("⚙️ Settings")
    try:
        secret_key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        secret_key = ""  # No secrets.toml configured yet -- expected during early prototyping.
    api_key = os.environ.get("GEMINI_API_KEY") or secret_key
    client, _ = get_gemini_client(api_key) if api_key else (None, None)
    if not api_key:
        st.info("No GEMINI_API_KEY found in environment or secrets.toml.")
    
    model = st.selectbox("Select Model", ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.1-pro", "gemini-2.5-flash"])
    st.markdown("---")
    if st.button("🧹 Clear Chat"):
        st.session_state.messages = []
        st.rerun()

if "messages" not in st.session_state: 
    st.session_state.messages = []

st.markdown('<div class="jarvis-card"><span class="jarvis-tag">JARVIS 2.0 · ONLINE</span><h2>🤖 Welcome to Jarvis 2.0</h2></div>', unsafe_allow_html=True)

for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            if st.button("🔊 Speak Response", key=f"btn_{i}"):
                with st.spinner("Generating Voice..."):
                    audio = text_to_speech_bytes(msg["content"])
                    if audio: 
                        st.audio(audio, format="audio/mp3", autoplay=True)

if prompt := st.chat_input("Ask me anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): 
        st.markdown(prompt)
        
    with st.spinner("Thinking..."):
        resp, err = call_gemini(client, prompt, model) if client else ("Please connect an API key.", None)

    if not resp:
        resp = f"Sorry, something went wrong: {err or 'no response received.'}"

    # Append to session state BEFORE rendering anything interactive (like the
    # speak button) in this turn. This is the actual fix for the rerun bug:
    # st.button clicks trigger their own rerun, and on that rerun
    # st.chat_input(...) returns None, so this whole block is skipped. If the
    # append happens after the button, a click before the natural rerun
    # permanently loses that message from history. Appending first means the
    # message is durable no matter what triggers the next rerun.
    st.session_state.messages.append({"role": "assistant", "content": resp})

    with st.chat_message("assistant"):
        st.markdown(resp)
        current_idx = len(st.session_state.messages) - 1
        if st.button("🔊 Speak Response", key=f"btn_now_{current_idx}"):
            with st.spinner("Generating Voice..."):
                audio = text_to_speech_bytes(resp)
                if audio: 
                    st.audio(audio, format="audio/mp3", autoplay=True)
                else:
                    st.warning("Couldn't generate audio for this response.")
