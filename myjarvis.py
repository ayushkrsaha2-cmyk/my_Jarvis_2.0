"""
Jarvis 2.0 -- Ultimate Version (With Fixed Audio Player & Grand Welcome)
---------------------------------------------------------------------------------
Run with:
    streamlit run myjarvis.py
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
# GEMINI LLM BACKEND FUNCTIONS
# ---------------------------------------------------------------------------
JARVIS_SYSTEM_PROMPT = """You are Jarvis, a warm, sharp, and direct AI assistant.
Your name is Jarvis 2.0.
Tone: speak like a grounded, intelligent peer -- warm, occasionally witty.
Formatting: use clear structure -- short paragraphs, bullet points for lists.
Use the Google Search tool for all queries related to real-time events, current dates, time, match scores, or news.
"""

def get_gemini_client(api_key):
    if not api_key or not api_key.strip():
        return None, "No API key provided."
    try:
        from google import genai
        client = genai.Client(api_key=api_key.strip())
        return client, None
    except ImportError:
        return None, "The `google-genai` package isn't installed. Run: pip install google-genai"
    except Exception as e:
        return None, f"Couldn't create Gemini client: {e}"

def call_gemini(client, prompt, model="gemini-2.5-flash"):
    try:
        from google.genai import types
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=JARVIS_SYSTEM_PROMPT,
                temperature=0.7,
                tools=[{"google_search": {}}],
            ),
        )
        return response.text, None
    except Exception as e:
        return None, f"Gemini API call failed: {e}"

# ---------------------------------------------------------------------------
# gTTS VOICE SYNTHESIS
# ---------------------------------------------------------------------------
def text_to_speech_bytes(text, lang="en"):
    try:
        from gtts import gTTS
        cleaned = re.sub(r"\*\*|\*|__|_|#+\s?|`|http\S+", "", text).strip()
        if not cleaned: return None
        tts = gTTS(text=cleaned[:1500], lang=lang)
        buffer = io.BytesIO()
        tts.write_to_fp(buffer)
        buffer.seek(0)
        return buffer.read()
    except Exception:
        return None

# ---------------------------------------------------------------------------
# LOCAL FALLBACK RESEARCH ENGINE
# ---------------------------------------------------------------------------
def research_wikipedia(query):
    try:
        import wikipedia
        return wikipedia.summary(query, sentences=3, auto_suggest=True, redirect=True).strip()
    except Exception:
        return None

def research_duckduckgo(query, max_results=5):
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            snippets = [r.get("body") or r.get("snippet") or "" for r in results if r]
            return " ".join(snippets)[:900], []
    except Exception:
        return None, []

def local_research_answer(query):
    wiki = research_wikipedia(query)
    if wiki: return f"📚 **Local fallback (Wikipedia summary):**\n\n{wiki}"
    ddg, _ = research_duckduckgo(query)
    if ddg: return f"🔎 **Local fallback (Live search):**\n\n{ddg}"
    return "I couldn't find anything via local search. Please connect a Gemini API key."

# ---------------------------------------------------------------------------
# ROUTING
# ---------------------------------------------------------------------------
def route_message(text, gemini_client, model="gemini-2.5-flash"):
    if not text.strip(): return "I didn't catch that."
    if gemini_client:
        ans, err = call_gemini(gemini_client, text, model=model)
        if ans: return ans
    return local_research_answer(text)

# ---------------------------------------------------------------------------
# ONE SINGLE BULLETPROOF SIDEBAR BLOCK
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Settings")
    
    GLOBAL_API_KEY = ""
    if "GEMINI_API_KEY" in st.secrets:
        GLOBAL_API_KEY = st.secrets["GEMINI_API_KEY"]
    else:
        GLOBAL_API_KEY = os.environ.get("GEMINI_API_KEY", "")
        
    gemini_client = None
    
    if GLOBAL_API_KEY:
        gemini_client, client_error = get_gemini_client(GLOBAL_API_KEY)
        if gemini_client:
            st.success("🤖 Jarvis is Fully Active")
        else:
            st.error(f"Global Key Error: {client_error}")
    else:
        api_key_input = st.text_input(
            "Google Gemini API Key",
            type="password",
            key="gemini_api_key_input",
            placeholder="Paste your API key here..."
        )
        if api_key_input:
            gemini_client, client_error = get_gemini_client(api_key_input)
            if gemini_client:
                st.success("Gemini Connected!")
            else:
                st.error(f"Error: {client_error}")
        else:
            st.info("Running on Local Fallback Mode.")

    st.markdown("---")
    
    if "gemini_model" not in st.session_state:
        st.session_state.gemini_model = "gemini-2.5-flash"
        
    selected_model = st.selectbox(
        "Select Model",
        options=["gemini-2.5-flash", "gemini-2.5-pro"],
        key="gemini_model"
    )

    st.markdown("---")
    
    # वॉइस स्विच
    voice_toggle = st.toggle("Enable Voice System (Speaker)", key="voice_toggle", value=True)

    st.markdown("---")
    
    st.markdown("### 📐 Math Image Solver")
    uploaded_file = st.file_uploader("Upload image", type=["png", "jpg", "jpeg"], key="math_image_uploader")
    run_ocr_clicked = st.button("Run OCR + Solve") if uploaded_file else False

    st.markdown("---")
    st.markdown("### 🗒️ Session Actions")
    
    col1, col2 = st.columns(2)
    with col1:
        clear_chat = st.button("🧹 Clear Chat", use_container_width=True, key="clear_chat_button")
    
    with col2:
        chat_text = "\n\n".join(
            f"{'You' if m['role'] == 'user' else 'Jarvis'}: {m['content']}"
            for m in st.session_state.get("messages", [])
        )
        st.download_button(
            "💾 Export",
            data=chat_text if chat_text else "No messages yet.",
            file_name="jarvis_chat.txt",
            mime="text/plain",
            use_container_width=True,
            disabled=not st.session_state.get("messages", []),
            key="export_chat_button"
        )

# ---------------------------------------------------------------------------
# MAIN CHAT AREA
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if clear_chat:
    st.session_state.messages = []
    st.rerun()

# नया और बदला हुआ वेलकम कार्ड (Welcome to Jarvis 2.0)
st.markdown(
    """
    <div class="jarvis-card">
    <span class="jarvis-tag">JARVIS 2.0 · ONLINE</span>
    <h2 style="margin-top:6px;">🤖 Welcome to Jarvis 2.0</h2>
    </div>
    """,
    unsafe_allow_html=True,
)

# चैट मैसेजेस को स्क्रीन पर रेंडर करना
for i, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        # पुराना ऑडियो रेंडर करना (ताकि गायब न हो)
        if message["role"] == "assistant" and voice_toggle and "audio" in message:
            if message["audio"]:
                st.audio(message["audio"], format="audio/mp3")

# चैट इनपुट लॉजिक
if prompt := st.chat_input("Ask me anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = route_message(prompt, gemini_client, selected_model)
        st.markdown(response)
        
        # तुरंत न्यू ऑडियो जेनरेट करना
        audio_data = None
        if voice_toggle:
            audio_data = text_to_speech_bytes(response)
            if audio_data:
                st.audio(audio_data, format="audio/mp3")
                
    # मैसेज हिस्ट्री में डेटा डालना (रिरन हटा दिया गया है ताकि प्लेयर टिका रहे)
    st.session_state.messages.append({
        "role": "assistant", 
        "content": response, 
        "audio": audio_data
    })
