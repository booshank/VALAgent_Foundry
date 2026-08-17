"""Streamlit interface for the VAL (Vendor Analysis) Foundry agent."""

import os
from typing import Any

import streamlit as st
from azure.ai.projects import AIProjectClient
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv


load_dotenv()

AGENT_NAME = "VAL - Vendor Analysis Agent"
MODEL_NAME = "gpt-4o"
ANALYSIS_MODE = "JSON Dataset Analysis"

QUICK_ACTIONS = (
    "📊 Detect Tool Overlaps",
    "⚠️ High Risk Contracts",
    "📅 Upcoming Renewals",
    "🔍 Audit Missing Clauses",
)


def configuration() -> tuple[str | None, str | None]:
    """Return the Foundry project connection string and VAL agent ID."""
    return (
        os.getenv("PROJECT_CONNECTION_STRING"),
        os.getenv("VAL_AGENT_ID"),
    )


@st.cache_resource(show_spinner=False)
def get_project_client(connection_string: str) -> AIProjectClient:
    """Create one authenticated Azure AI Foundry client per Streamlit process."""
    return AIProjectClient.from_connection_string(
        conn_str=connection_string,
        credential=DefaultAzureCredential(),
    )


def setup_thread() -> None:
    """Create a Foundry thread for the current browser session."""
    connection_string, agent_id = configuration()
    if not connection_string or not agent_id:
        st.session_state.thread_id = None
        return

    try:
        client = get_project_client(connection_string)
        st.session_state.thread_id = client.agents.create_thread().id
    except (ClientAuthenticationError, HttpResponseError, OSError) as error:
        st.session_state.thread_id = None
        st.session_state.connection_error = str(error)


def new_conversation() -> None:
    """Reset local history and begin a separate Foundry conversation."""
    st.session_state.messages = []
    st.session_state.connection_error = None
    setup_thread()


def message_text(message: Any) -> str:
    """Extract text from an Azure AI Foundry message object."""
    content = getattr(message, "content", []) or []
    text_parts: list[str] = []

    for item in content:
        if getattr(item, "type", None) != "text":
            continue
        text = getattr(item, "text", None)
        value = getattr(text, "value", None)
        if value:
            text_parts.append(value)

    return "\n\n".join(text_parts)


def latest_assistant_response(client: AIProjectClient, thread_id: str) -> str:
    """Return the newest text response produced on a Foundry thread."""
    messages = client.agents.list_messages(thread_id=thread_id)
    for message in messages.data:
        if getattr(message, "role", None) == "assistant":
            response = message_text(message)
            if response:
                return response
    return "VAL completed the analysis but did not return a text response."


def troubleshoot_authentication(error: Exception) -> None:
    """Show actionable, safe credentials guidance."""
    st.error("VAL could not authenticate with Azure AI Foundry.")
    st.info(
        "Check that you signed in with `az login` (or configured a managed "
        "identity), that the identity can access the Foundry project, and that "
        "`PROJECT_CONNECTION_STRING` points to the correct project."
    )
    with st.expander("Technical details"):
        st.code(str(error))


def ask_val(prompt: str) -> None:
    """Send a prompt to VAL and append its answer to local chat history."""
    connection_string, agent_id = configuration()
    if not connection_string or not agent_id:
        st.error(
            "Missing Foundry configuration. Add `PROJECT_CONNECTION_STRING` and "
            "`VAL_AGENT_ID` to `.env`, then restart Streamlit."
        )
        return

    if not st.session_state.thread_id:
        setup_thread()
    if not st.session_state.thread_id:
        st.error("A Foundry conversation could not be created. Check the connection details.")
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        client = get_project_client(connection_string)
        # create_message is the Azure AI Projects API for posting to a thread.
        client.agents.create_message(
            thread_id=st.session_state.thread_id,
            role="user",
            content=prompt,
        )
        with st.chat_message("assistant"):
            with st.spinner("VAL is analyzing contract data..."):
                client.agents.create_and_process_run(
                    thread_id=st.session_state.thread_id,
                    assistant_id=agent_id,
                )
                response = latest_assistant_response(client, st.session_state.thread_id)
            st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
    except ClientAuthenticationError as error:
        troubleshoot_authentication(error)
    except HttpResponseError as error:
        if getattr(error, "status_code", None) in (401, 403):
            troubleshoot_authentication(error)
        else:
            st.error("Foundry could not process this request. Verify the agent and project configuration.")
            with st.expander("Technical details"):
                st.code(str(error))
    except Exception as error:
        st.error("An unexpected error occurred while contacting VAL.")
        with st.expander("Technical details"):
            st.code(str(error))


st.set_page_config(page_title="VAL | Vendor Analysis", page_icon="📋", layout="wide")
st.title("Vendor Analysis Agent")
st.caption("Ask VAL to identify cost, risk, renewal, and governance insights across your contracts.")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "connection_error" not in st.session_state:
    st.session_state.connection_error = None

connection_string, agent_id = configuration()

with st.sidebar:
    st.header("VAL Control Center")
    if connection_string and agent_id:
        st.success("● Foundry configuration detected")
    else:
        st.warning("● Configuration required")
        st.caption("Set `PROJECT_CONNECTION_STRING` and `VAL_AGENT_ID` in `.env`.")

    st.subheader("Agent Information")
    st.markdown(
        f"**Name**  \n{AGENT_NAME}\n\n"
        f"**Model**  \n{MODEL_NAME}\n\n"
        f"**Mode**  \n{ANALYSIS_MODE}"
    )

    if st.button("＋ New Conversation", use_container_width=True):
        new_conversation()
        st.rerun()

    st.subheader("Quick Actions")
    for action in QUICK_ACTIONS:
        if st.button(action, use_container_width=True):
            st.session_state.pending_prompt = action

if st.session_state.connection_error:
    st.warning("Unable to create a Foundry thread. See the authentication guidance after sending a prompt.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

pending_prompt = st.session_state.pop("pending_prompt", None)
prompt = pending_prompt or st.chat_input("Ask VAL about your vendor and contract data...")
if prompt:
    ask_val(prompt)
