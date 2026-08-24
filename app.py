"""Streamlit interface for the VAL (Vendor Analysis) Foundry agent."""

import os
import time

import streamlit as st
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, AuthenticationError


load_dotenv()

AGENT_NAME = "VAL - Vendor Analysis Agent"
MODEL_NAME = "Foundry-managed agent"
ANALYSIS_MODE = "JSON Dataset Analysis"

QUICK_ACTIONS = (
    "📊 Detect Tool Overlaps",
    "⚠️ High Risk Contracts",
    "📅 Upcoming Renewals",
    "🔍 Audit Missing Clauses",
)


def configuration() -> tuple[str | None, str | None, str | None, str | None]:
    """Return configuration required to invoke the deployed VAL agent."""
    return (
        os.getenv("AZURE_AIPROJECT_ENDPOINT") or os.getenv("AZURE_EXISTING_AIPROJECT_ENDPOINT"),
        os.getenv("OPENAI_API_VERSION") or os.getenv("AZURE_AIPROJECT_API_VERSION"),
        os.getenv("AZURE_VAL_AGENT_NAME") or os.getenv("AZURE_CLASSIFY_AGENT_NAME"),
        os.getenv("AZURE_VAL_AGENT_VERSION") or os.getenv("AZURE_CLASSIFY_AGENT_VERSION"),
    )


@st.cache_resource(show_spinner=False)
def get_foundry_openai_client(project_endpoint: str, api_version: str):
    """Create an OpenAI Responses client authorized through the Foundry project."""
    if not project_endpoint or not project_endpoint.startswith(("https://", "http://")):
        raise ValueError(
            "AZURE_AIPROJECT_ENDPOINT must be the Foundry project endpoint URL, "
            "for example https://<resource>.services.ai.azure.com/api/projects/<project>."
        )
    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=DefaultAzureCredential(),
    )
    # AIProjectClient reads this value when it constructs its Azure OpenAI client.
    # Passing api_version directly is incompatible with some current SDK paths.
    os.environ["OPENAI_API_VERSION"] = api_version
    return project_client.get_openai_client()


def invoke_val_agent(messages: list[dict[str, str]]) -> str:
    """Run the deployed VAL agent using Foundry's Responses API."""
    project_endpoint, api_version, agent_name, agent_version = configuration()
    if not all((project_endpoint, api_version, agent_name, agent_version)):
        raise RuntimeError(
            "Set AZURE_AIPROJECT_ENDPOINT, OPENAI_API_VERSION, "
            "AZURE_VAL_AGENT_NAME, and AZURE_VAL_AGENT_VERSION in .env."
        )

    input_items = [
        {
            "role": message["role"],
            "content": [{"type": "input_text", "text": message["content"]}],
        }
        for message in messages
        if message["content"].strip()
    ]
    if not input_items:
        raise RuntimeError("VAL received no non-empty messages.")

    client = get_foundry_openai_client(project_endpoint, api_version)
    response = client.responses.create(
        input=input_items,
        extra_body={
            "agent_reference": {
                "name": agent_name,
                "version": agent_version,
                "type": "agent_reference",
            }
        },
    )
    return (response.output_text or "").strip()


def new_conversation() -> None:
    """Reset the local multi-turn conversation."""
    st.session_state.messages = []
    st.session_state.connection_error = None


def render_response_time(seconds: float | None) -> None:
    """Display an end-to-end Foundry agent response time."""
    if seconds is not None:
        st.caption(f"⏱️ VAL response time: {seconds:.2f} seconds")


def ask_val(prompt: str) -> None:
    """Send a prompt to VAL and append its answer to local chat history."""
    project_endpoint, api_version, agent_name, agent_version = configuration()
    if not all((project_endpoint, api_version, agent_name, agent_version)):
        st.error(
            "Missing Foundry agent configuration. Add `AZURE_AIPROJECT_ENDPOINT`, "
            "`OPENAI_API_VERSION`, `AZURE_VAL_AGENT_NAME`, and "
            "`AZURE_VAL_AGENT_VERSION` to `.env`, then restart Streamlit."
        )
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        with st.chat_message("assistant"):
            with st.spinner("VAL is analyzing contract data..."):
                started_at = time.perf_counter()
                response = invoke_val_agent(st.session_state.messages)
                response_time_seconds = time.perf_counter() - started_at
                if not response:
                    response = "VAL completed the analysis but did not return a text response."
            st.markdown(response)
            render_response_time(response_time_seconds)
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": response,
                "response_time_seconds": response_time_seconds,
            }
        )
    except AuthenticationError as error:
        st.error("Azure rejected the identity used to access the Foundry project.")
        st.info("Run `az login` or configure a managed identity with Foundry project access.")
        with st.expander("Technical details"):
            st.code(str(error))
    except (APIConnectionError, APIStatusError) as error:
        st.error("Azure OpenAI could not process this request.")
        with st.expander("Technical details"):
            st.code(str(error))
    except Exception as error:
        st.error("An unexpected error occurred while contacting Azure OpenAI.")
        with st.expander("Technical details"):
            st.code(str(error))


st.set_page_config(page_title="VAL | Vendor Analysis", page_icon="📋", layout="wide")
st.title("Vendor Analysis Agent")
st.caption("Ask VAL to identify cost, risk, renewal, and governance insights across your contracts.")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "connection_error" not in st.session_state:
    st.session_state.connection_error = None

project_endpoint, api_version, agent_name, agent_version = configuration()

with st.sidebar:
    st.header("VAL Control Center")
    if all((project_endpoint, api_version, agent_name, agent_version)):
        st.success("● Foundry agent configuration detected")
    else:
        st.warning("● Configuration required")
        st.caption("Set the Foundry endpoint, `OPENAI_API_VERSION`, and `AZURE_VAL_AGENT_*` variables in `.env`.")

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

    response_times = [
        message["response_time_seconds"]
        for message in st.session_state.messages
        if message["role"] == "assistant"
        and message.get("response_time_seconds") is not None
    ]
    if response_times:
        st.subheader("Response Performance")
        latest_time, average_time = st.columns(2)
        latest_time.metric("Latest", f"{response_times[-1]:.2f}s")
        average_time.metric("Average", f"{sum(response_times) / len(response_times):.2f}s")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            render_response_time(message.get("response_time_seconds"))

pending_prompt = st.session_state.pop("pending_prompt", None)
prompt = pending_prompt or st.chat_input("Ask VAL about your vendor and contract data...")
if prompt:
    ask_val(prompt)
