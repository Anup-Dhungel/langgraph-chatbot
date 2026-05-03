import streamlit as st
from langgraph_tool_backend import chatbot, retrieve_all_threads
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
import uuid

# =========================== Utilities ===========================

def generate_thread_id():
    return str(uuid.uuid4())

def load_conversation(thread_id):
    state = chatbot.get_state(config={"configurable": {"thread_id": thread_id}})
    return state.values.get("messages", [])

def delete_thread(thread_id):

    st.session_state["chat_threads"] = [
        chat for chat in st.session_state["chat_threads"]
        if chat["id"] != thread_id
    ]

    if st.session_state["thread_id"] == thread_id:
        new_id = generate_thread_id()
        st.session_state["thread_id"] = new_id
        st.session_state["message_history"] = []

        st.session_state["chat_threads"].append({
            "id": new_id,
            "title": "New Chat"
        })

    try:
        conn = chatbot.checkpointer.conn
        conn.execute(
            "DELETE FROM checkpoints WHERE thread_id = ?",
            (thread_id,)
        )
        conn.commit()
    except:
        pass


# ======================= Session Initialization ===================

if "message_history" not in st.session_state:
    st.session_state["message_history"] = []

if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = generate_thread_id()

if "chat_threads" not in st.session_state:
    existing_threads = retrieve_all_threads()

    chat_threads = []

    for t in existing_threads:
        state = chatbot.get_state(config={"configurable": {"thread_id": t}})
        messages = state.values.get("messages", [])

        title = "New Chat"

        for msg in messages:
            if isinstance(msg, HumanMessage):
                title = msg.content[:30] + "..."
                break

        chat_threads.append({
            "id": t,
            "title": title
        })

    if not chat_threads:
        chat_threads = [{
            "id": st.session_state["thread_id"],
            "title": "New Chat"
        }]

    st.session_state["chat_threads"] = chat_threads


# ============================ Sidebar ============================

st.sidebar.title("LangGraph Chatbot")

if st.sidebar.button("➕ New Chat"):
    new_id = generate_thread_id()
    st.session_state["thread_id"] = new_id
    st.session_state["message_history"] = []

    st.session_state["chat_threads"].append({
        "id": new_id,
        "title": "New Chat"
    })

    st.rerun()

st.sidebar.header("My Conversations")

for chat in st.session_state["chat_threads"][::-1]:

    col1, col2 = st.sidebar.columns([0.8, 0.2])

    chat_id = chat["id"]

    # OPEN CHAT
    if col1.button(chat["title"], key=f"open_{chat_id}"):

        st.session_state["thread_id"] = chat_id
        messages = load_conversation(chat_id)

        temp_messages = []

        for msg in messages:
            role = "user" if isinstance(msg, HumanMessage) else "assistant"
            temp_messages.append({
                "role": role,
                "content": msg.content
            })

        st.session_state["message_history"] = temp_messages
        st.rerun()

    # DELETE CHAT
    if col2.button("🗑", key=f"del_{chat_id}"):
        delete_thread(chat_id)
        st.rerun()


# ============================ Main UI ============================

for message in st.session_state["message_history"]:
    with st.chat_message(message["role"]):
        st.text(message["content"])

user_input = st.chat_input("Type here")

# ====================== MAIN FIXED LOGIC ======================

if user_input:

    # save user message
    st.session_state["message_history"].append(
        {"role": "user", "content": user_input}
    )

    chat_id = st.session_state["thread_id"]

    # ================= AUTO TITLE UPDATE =================
    for chat in st.session_state["chat_threads"]:
        if chat["id"] == chat_id and chat["title"] == "New Chat":
            chat["title"] = user_input[:30] + "..."

    with st.chat_message("user"):
        st.text(user_input)

    CONFIG = {
        "configurable": {"thread_id": chat_id},
        "metadata": {"thread_id": chat_id},
        "run_name": "chat_turn",
    }

    with st.chat_message("assistant"):

        status_holder = {"box": None}

        def ai_only_stream():
            for message_chunk, metadata in chatbot.stream(
                {"messages": [HumanMessage(content=user_input)]},
                config=CONFIG,
                stream_mode="messages",
            ):

                if isinstance(message_chunk, ToolMessage):
                    tool_name = getattr(message_chunk, "name", "tool")

                    if status_holder["box"] is None:
                        status_holder["box"] = st.status(
                            f"🔧 Using `{tool_name}` ...",
                            expanded=True
                        )
                    else:
                        status_holder["box"].update(
                            label=f"🔧 Using `{tool_name}` ...",
                            state="running",
                            expanded=True,
                        )

                if isinstance(message_chunk, AIMessage):
                    yield message_chunk.content

        ai_message = st.write_stream(ai_only_stream())

        if status_holder["box"] is not None:
            status_holder["box"].update(
                label="✅ Tool finished",
                state="complete",
                expanded=False
            )

    st.session_state["message_history"].append(
        {"role": "assistant", "content": ai_message}
    )