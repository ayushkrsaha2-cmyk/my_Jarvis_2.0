"""
Jarvis 2.0 -- Selective Grounding + Quota-Safe Edition (Creator & Boss: Ayush)
---------------------------------------------------------------------------------
pip install streamlit google-genai gtts pytesseract pillow

You also need Tesseract OCR installed at the system level for the Math Image
Solver (separate from the pytesseract Python package):
    Windows : https://github.com/UB-Mannheim/tesseract/wiki
    macOS   : brew install tesseract
    Linux   : sudo apt install tesseract-ocr

==============================================================================
WHAT CHANGED FROM YOUR VERSION, AND WHY -- READ THIS BEFORE RUNNING
==============================================================================
Your 429 errors and wrong-date answers both trace back to the same root
cause, confirmed against Google's current docs:

1. Google Search grounding is billed PER PROMPT on Gemini 2.5 models --
   every single message sent with the search tool attached counts against
   your quota, whether or not the model actually decides to search. Your
   old code attached `tools=[{"google_search": {}}]` to EVERY message,
   every turn, re-sending the whole chat history each time. On a free-tier
   key with already-tight rate limits, that's a fast path to 429s.

2. Your tools syntax was also non-standard: `{"google_search": {}}` is a
   raw dict that isn't what any current official example uses. The
   documented, correct form is `types.Tool(google_search=types.GoogleSearch())`.

3. The "wrong date" symptom (June 26/27 instead of the real date) is the
   classic sign of the search tool silently failing or not being invoked --
   the model then answers from its own internal sense of "now" instead of
   live data. Rather than fight that, this version computes the real
   current date/time locally with Python's own datetime (always correct,
   costs nothing, no API call needed) and injects it directly into context
   whenever a message looks date/time-related. That problem is now solved
   outside the API entirely, which is more reliable than depending on
   grounding succeeding.

THE FIX, CONCRETELY:
  - Google Search grounding is now SELECTIVE: only attached when a message
    actually looks time-sensitive (news, scores, "latest", "current", etc.)
    via a simple keyword check -- not on every single turn. This directly
    cuts the per-prompt grounding charges to roughly the fraction of your
    traffic that actually needs it.
  - The search tool now uses the documented typed object:
    types.Tool(google_search=types.GoogleSearch())
  - All Gemini calls now retry with exponential backoff specifically on 429
    errors (this is Google's own documented guidance for handling
    spend-based rate limits -- wait and retry, don't hammer the endpoint).
  - Current date/time questions are answered from local system time
    directly, with zero API/grounding cost and zero risk of being wrong.
  - The gTTS "Speak Response" rerun-ordering bug from your earlier version
    is fixed the same way as before: the assistant message is appended to
    session_state BEFORE any interactive widget (the speak button) that
    could trigger an early rerun and skip the append.
  - 'user'/'model' role alternation for the Gemini history is preserved
    exactly as your version had it.
==============================================================================
"""

import re
import io
import os
import time
from datetime import datetime

import streamlit as st

st.set_page_config(
    page_title="Jarvis 2.0",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

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

JARVIS_SYSTEM_PROMPT = """You are Jarvis 2.0, a grounded, intelligent, and direct AI assistant.
Your creator and boss is Ayush. If asked who made you or who your boss is, always proudly say that Ayush created you.
Tone: speak like a grounded, intelligent peer -- warm, occasionally witty.

When the current date or time is provided to you directly in a message (you will see a line like
"[Current real-world date/time: ...]"), treat that as ground truth and use it -- it comes from the
system clock, not your training data, and is always correct.

When Google Search results are attached to a query, ground your answer in them and prefer them over
your own training data for anything time-sensitive.
"""

# Keywords that trigger attaching the (billed) Google Search tool. Kept
# deliberately narrow -- the whole point is to NOT pay the per-prompt
# grounding cost on every casual message.
TIME_SENSITIVE_KEYWORDS = [
    "news", "latest", "current", "today", "score", "scores", "cricket",
    "match", "live", "weather", "election", "stock", "price of", "breaking",
    "happened", "yesterday", "this week", "recent", "update", "trending",
]

# Keywords specifically about date/time -- answered from local system clock,
# never sent to the API at all, since this is the one thing Python itself
# always knows correctly and for free.
DATETIME_KEYWORDS = [
    "what time is it", "current time", "what's the time", "what is the time",
    "today's date", "current date", "what day is it", "what's today's date",
    "what date is it",
]


def is_datetime_query(text):
    lower = text.lower()
    return any(kw in lower for kw in DATETIME_KEYWORDS)


def is_time_sensitive_query(text):
    lower = text.lower()
    return any(kw in lower for kw in TIME_SENSITIVE_KEYWORDS)


def local_datetime_answer():
    now = datetime.now()
    return (
        f"Right now it's **{now.strftime('%I:%M %p')}** on "
        f"**{now.strftime('%A, %B %d, %Y')}** (based on this system's local clock)."
    )


def get_gemini_client(api_key):
    if not api_key or not api_key.strip():
        return None, "No API key provided."
    try:
        from google import genai
        return genai.Client(api_key=api_key.strip()), None
    except ImportError:
        return None, "The `google-genai` package isn't installed. Run: pip install google-genai"
    except Exception as e:
        return None, f"Couldn't create Gemini client: {e}"


def call_gemini(client, messages_history, model_id="gemini-2.5-flash", use_search=False, max_retries=3):
    """Calls Gemini with the full chat history, optionally attaching the
    (billed, per-prompt on 2.5 models) Google Search grounding tool. Retries
    with exponential backoff specifically on 429 RESOURCE_EXHAUSTED, per
    Google's own documented guidance for spend-based rate limits."""
    try:
        from google.genai import types
    except ImportError:
        return None, "The `google-genai` package isn't installed."

    formatted_contents = []
    for msg in messages_history:
        role_type = "user" if msg["role"] == "user" else "model"
        formatted_contents.append(
            types.Content(role=role_type, parts=[types.Part.from_text(text=msg["content"])])
        )

    config_kwargs = {"system_instruction": JARVIS_SYSTEM_PROMPT}
    if use_search:
        config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]

    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=formatted_contents,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            text = response.text
            if not text:
                return None, "Gemini returned an empty response (possibly safety-filtered)."
            return text, None
        except Exception as e:
            last_error = e
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str.upper():
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 1.5  # 1.5s, 3s, 6s
                    time.sleep(wait_time)
                    continue
                return None, (
                    "Gemini's free-tier quota is exhausted right now (429 RESOURCE_EXHAUSTED), "
                    "even after retrying with backoff. This is expected free-tier behavior under "
                    "load, not a bug in this app -- wait a bit and try again, or reduce how often "
                    "Google Search grounding is triggered."
                )
            # Non-429 error -- don't retry, just report it.
            return None, error_str

    return None, str(last_error) if last_error else "Unknown error after retries."


def text_to_speech_bytes(text):
    try:
        from gtts import gTTS
    except ImportError:
        return None, "gTTS isn't installed. Run: pip install gTTS"

    clean = re.sub(r"\*\*|\*|__|_|#+|`|http\S+", "", text).strip()
    if not clean:
        return None, "Nothing to speak."

    try:
        tts = gTTS(text=clean[:1000], lang="en", tld="co.uk")
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read(), None
    except Exception as e:
        return None, f"Voice synthesis failed: {e}"


def run_ocr_on_image(uploaded_file):
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None, "OCR isn't available -- pytesseract/Pillow aren't installed."

    try:
        text = pytesseract.image_to_string(Image.open(uploaded_file)).strip()
        if not text:
            return None, "OCR ran but found no readable text. Try a clearer photo."
        return text, None
    except Exception as e:
        return None, f"OCR failed: {e}"


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("⚙️ Settings")

    try:
        secret_key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        secret_key = ""
    api_key = os.environ.get("GEMINI_API_KEY") or secret_key

    client = None
    if api_key:
        client, client_error = get_gemini_client(api_key)

    if api_key and client:
        st.success("🤖 Jarvis is Fully Active")
    elif api_key and not client:
        st.error(f"API Key found but client failed: {client_error}")
    else:
        st.error("API Key missing. Add GEMINI_API_KEY to environment or secrets.toml.")

    st.info("🎯 Engine: Gemini 2.5 Flash (Locked)")
    chosen_model_id = "gemini-2.5-flash"

    st.caption(
        "🔎 Google Search grounding is applied SELECTIVELY (only for messages that "
        "look time-sensitive: news, scores, 'latest', etc.) to avoid burning free-tier "
        "quota on every single message. Date/time questions are answered from the "
        "local system clock directly, at zero API cost."
    )

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
        chat_text = "\n\n".join(
            f"{'You' if m['role'] == 'user' else 'Jarvis'}: {m['content']}"
            for m in st.session_state.get("messages", [])
        )
        st.download_button(
            "💾 Export",
            data=chat_text or "No messages yet.",
            file_name="jarvis_chat.txt",
            mime="text/plain",
            use_container_width=True,
        )

# ---------------------------------------------------------------------------
# MAIN CHAT AREA
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

if clear_chat:
    st.session_state.messages = []
    st.rerun()

st.markdown(
    '<div class="jarvis-card"><span class="jarvis-tag">JARVIS 2.0 · ONLINE</span>'
    "<h2>🤖 Welcome to Jarvis 2.0</h2></div>",
    unsafe_allow_html=True,
)

if run_ocr_clicked and uploaded_file is not None:
    with st.spinner("Extracting text from image..."):
        extracted_text, ocr_error = run_ocr_on_image(uploaded_file)

    if ocr_error:
        ocr_result = f"⚠️ {ocr_error}"
    else:
        ocr_header = (
            "📐 **Extracted text from your image (OCR):**\n\n"
            f"```\n{extracted_text}\n```\n\n"
            "Heads up: OCR commonly mangles exponents, fractions, and square roots -- "
            "check the extracted text above is correct before trusting the answer below.\n\n"
        )
        if client:
            with st.spinner("Solving..."):
                solve_prompt = (
                    "The following text was extracted via OCR from a math/textbook "
                    "problem photo and may contain OCR errors. Solve it step by step, "
                    "and flag explicitly if the text looks garbled or ambiguous:\n\n"
                    f"{extracted_text}"
                )
                solution, solve_err = call_gemini(
                    client, [{"role": "user", "content": solve_prompt}], chosen_model_id, use_search=False
                )
            ocr_result = ocr_header + (solution if solution else f"⚠️ Couldn't solve: {solve_err}")
        else:
            ocr_result = ocr_header + "Connect a Gemini API key to get a step-by-step solution."

    st.session_state.messages.append({"role": "user", "content": "[Uploaded a math image]"})
    st.session_state.messages.append({"role": "model", "content": ocr_result})

for i, msg in enumerate(st.session_state.messages):
    display_role = "assistant" if msg["role"] == "model" else "user"
    with st.chat_message(display_role):
        st.markdown(msg["content"])
        if display_role == "assistant":
            if st.button("🔊 Speak Response", key=f"btn_{i}"):
                with st.spinner("Generating Voice..."):
                    audio, tts_err = text_to_speech_bytes(msg["content"])
                if audio:
                    st.audio(audio, format="audio/mp3", autoplay=True)
                else:
                    st.warning(f"Couldn't generate audio: {tts_err}")

if prompt := st.chat_input("Ask me anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    if is_datetime_query(prompt):
        # Answered locally -- zero API cost, always correct, no grounding needed.
        resp, err = local_datetime_answer(), None
    elif client:
        use_search = is_time_sensitive_query(prompt)
        # If it's a datetime-adjacent but not exact-match query (e.g. "what's
        # happening today"), still hand Gemini the real local time as context
        # so it isn't guessing from training data even when grounding doesn't fire.
        history_for_call = list(st.session_state.messages)
        if use_search or "today" in prompt.lower() or "now" in prompt.lower():
            now_str = datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")
            history_for_call = history_for_call[:-1] + [
                {"role": "user", "content": f"[Current real-world date/time: {now_str}]\n\n{prompt}"}
            ]
        with st.spinner("Thinking..." + (" (searching live web...)" if use_search else "")):
            resp, err = call_gemini(client, history_for_call, chosen_model_id, use_search=use_search)
    else:
        resp, err = "Please connect a Gemini API key to chat with me.", None

    if not resp:
        resp = f"⚠️ Error: {err or 'no response received.'}"

    # Append BEFORE rendering the speak button -- this is the fix for the
    # rerun-ordering bug. st.button clicks trigger their own rerun; on that
    # rerun st.chat_input(...) returns None, so anything after this point
    # that depends on `prompt` being truthy would be skipped. Appending here
    # means the message is durable regardless of what happens next.
    st.session_state.messages.append({"role": "model", "content": resp})

    with st.chat_message("assistant"):
        st.markdown(resp)
        current_idx = len(st.session_state.messages) - 1
        if st.button("🔊 Speak Response", key=f"btn_now_{current_idx}"):
            with st.spinner("Generating Voice..."):
                audio, tts_err = text_to_speech_bytes(resp)
            if audio:
                st.audio(audio, format="audio/mp3", autoplay=True)
            else:
                st.warning(f"Couldn't generate audio: {tts_err}")
