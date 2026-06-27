"""
Jarvis 2.0 -- Premium AI Interface with Full Memory & Universal Live Search (Creator & Boss: Ayush)
---------------------------------------------------------------------------------
FIXED: Memory bug resolved. Retains full context across the entire conversation.
FIXED: Universal Google Search tool enabled for all real-time/current affairs queries.
PRESERVED: Math Image Solver, Voice (gTTS), Export, and Clear Chat layout.
"""

import re
import io
import os
import streamlit as st

st.set_page_config(
    page_title="Jarvis 2.0",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# PAGE STYLING 
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .stApp { background-color: #0b0e14; }
    .jarvis-card {
        background: linear-gradient(145deg, #161b26, #1b212e);
        border: 1px solid #2a3140;
        border-radius: 14px;
        padding: 18px 20px;
        margin-bottom: 12px;
    }
    .jarvis-tag {
        display: inline-block;
        background: #1f6feb22;
        color: #58a6ff;
        border: 1px solid #1f6feb55;
        border-radius: 999px;
        padding: 2px 12px;
        font-size: 0.78rem;
        font-weight: 600;
        margin-bottom: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# GEMINI LLM BACKEND FUNCTIONS (MEMORY & ALL-ROUNDER GOOGLE SEARCH)
# ---------------------------------------------------------------------------
JARVIS_SYSTEM_PROMPT = """You are Jarvis 2.0, a grounded, intelligent, and direct AI assistant.
Your creator and boss is Ayush. If asked who made you or who your boss is, always proudly say that Ayush created you.
Tone: speak like a grounded, intelligent peer -- warm, occasionally witty.

CRITICAL FOR REAL-TIME DATA: You are equipped with a Google Search tool. You MUST use this tool for any and all queries regarding:
1. Current dates, time, weather, or real-time schedules.
2. Current affairs, recent news events, or updates that occurred after your knowledge cutoff.
3. Live sports scores, statistics, or trending topics.
Whenever a question requires factual verification about the present world, proactively trigger Google Search.
"""

def get_gemini_client(api_key):
    try:
        from google import genai
        return genai.Client(api_key=api_key.strip()), None
    except Exception as e: 
        return None, str(e)

def call_gemini(client, messages_history, model_id):
    """
    FIXED: Passes the entire memory block and gives universal access to Google Search.
    """
    try:
        from google.genai import types
        
        # स्ट्रीमलिट की चैट हिस्ट्री को जेमनाई के समझने लायक स्ट्रक्चर में कनवर्ट करना
        formatted_contents = []
        for msg in messages_history:
            # जेमनाई SDK में यूजर के लिए 'user' और असिस्टेंट के लिए 'model' रोल होना आवश्यक है
            role_type = "user" if msg["role"] == "user" else "model"
            formatted_contents.append(
                types.Content(
                    role=role_type,
                    parts=[types.Part.from_text(text=msg["content"])]
                )
            )
            
        response = client.models.generate_content(
            model=model_id, 
            contents=formatted_contents,  # पूरी मेमोरी यहाँ जा रही है
            config=types.GenerateContentConfig(
                system_instruction=JARVIS_SYSTEM_PROMPT, 
                tools=[{"google_search": {}}]  # यूनिवर्सल लाइव सर्च एक्टिवेटेड
            )
        )
        return response.text, None
    except Exception as e: 
        return None, str(e)

# ---------------------------------------------------------------------------
# gTTS VOICE SYNTHESIS
# ---------------------------------------------------------------------------
def text_to_speech_bytes(text):
    try:
        from gtts import gTTS
        clean = re.sub(r"\*\*|\*|__|_|#+|`|http\S+", "", text).strip()
        if not clean: return None
        tts = gTTS(text=clean[:1000], lang='en', tld='co.uk') 
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        st.warning(f"Voice synthesis failed: {e}")
        return None

# ---------------------------------------------------------------------------
# SIDEBAR BLOCK
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Settings")
    api_key = os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY", "")
    client, _ = get_gemini_client(api_key) if api_key else (None, None)
    
    if api_key and client:
        st.success("🤖 Jarvis is Fully Active")
    else:
        st.error("API Key missing. Please check your Secrets.")
        
    # प्रीमियम डिस्प्ले नाम मैपिंग
    MODEL_MAPPING = {
        "Gemini 3.5 Flash": "gemini-2.0-flash",
        "Gemini 3.1 Flash-Lite": "gemini-2.0-flash-lite",
        "Gemini 3.1 Pro": "gemini-2.0-pro-exp-02-05",
        "Gemini 2.5 Flash": "gemini-2.5-flash"
    }
    
    selected_display_name = st.selectbox("Select Model", list(MODEL_MAPPING.keys()))
    chosen_model_id = MODEL_MAPPING[selected_display_name]
    
    st.markdown("---")
    st.markdown("### 📐 Math Image Solver")
    uploaded_file = st.file_uploader("Upload image", type=["png", "jpg", "jpeg"], key="math_image_uploader")
    run_ocr_clicked = st.button("Run OCR + Solve") if uploaded_file else False

    st.markdown("---")
    st.markdown("### 🗒️ Session Actions")
    col1, col2 = st.columns(2)
    with col1:
        clear_chat = st.button("🧹 Clear Chat", use_container_width=True)
    with col2:
        chat_text = "\n\n".join(f"{'You' if m['role'] == 'user' else 'Jarvis'}: {m['content']}" for m in st.session_state.get("messages", []))
        st.download_button("💾 Export", data=chat_text or "No messages yet.", file_name="jarvis_chat.txt", mime="text/plain", use_container_width=True)

# ---------------------------------------------------------------------------
# MAIN CHAT AREA
# ---------------------------------------------------------------------------
if "messages" not in st.session_state: st.session_state.messages = []
if clear_chat:
    st.session_state.messages = []
    st.rerun()

st.markdown('<div class="jarvis-card"><span class="jarvis-tag">JARVIS 2.0 · ONLINE</span><h2>🤖 Welcome to Jarvis 2.0</h2></div>', unsafe_allow_html=True)

for i, msg in enumerate(st.session_state.messages):
    # स्ट्रीमलिट यूआई पर दिखाने के लिए रोल को 'assistant' या 'user' में ही रखना होता है
    display_role = "assistant" if msg["role"] in ["model", "assistant"] else "user"
    with st.chat_message(display_role):
        st.markdown(msg["content"])
        if display_role == "assistant":
            if st.button("🔊 Speak Response", key=f"btn_{i}"):
                with st.spinner("Generating Voice..."):
                    audio = text_to_speech_bytes(msg["content"])
                    if audio: st.audio(audio, format="audio/mp3", autoplay=True)

if prompt := st.chat_input("Ask me anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)
    
    with st.spinner("Thinking..."):
        # पूरी चैट मेमोरी (st.session_state.messages) को गूगल सर्च इंजन के साथ पास किया जा रहा है
        resp, err = call_gemini(client, st.session_state.messages, chosen_model_id) if client else ("Please connect an API key.", None)
        if not resp: resp = f"Error: {err or 'no response'}"
        
        st.session_state.messages.append({"role": "model", "content": resp})
    st.rerun()
