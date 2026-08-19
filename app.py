"""Streamlit interface for the VAL (Vendor Analysis) Azure OpenAI assistant."""

import os

import streamlit as st
from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, AuthenticationError, AzureOpenAI


load_dotenv()

AGENT_NAME = "VAL - Vendor Analysis Assistant"
MODEL_NAME = "gpt-5-mini"
ANALYSIS_MODE = "JSON Dataset Analysis"
SYSTEM_PROMPT = """You are VAL, a vendor and contract analysis assistant.
Analyze the available vendor dataset carefully. Present clear, actionable insights in Markdown.
Use tables when they improve comparison and call out material contract risks explicitly."""

QUICK_ACTIONS = (
    "📊 Detect Tool Overlaps",
    "⚠️ High Risk Contracts",
    "📅 Upcoming Renewals",
    "🔍 Audit Missing Clauses",
)


def configuration() -> tuple[str | None, str | None, str | None, str | None]:
    """Return the Azure OpenAI endpoint, deployment, API key, and API version."""
    return (
        os.getenv("AZURE_OPENAI_ENDPOINT"),
        os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        os.getenv("AZURE_OPENAI_API_KEY"),
        os.getenv("AZURE_OPENAI_API_VERSION"),
    )


@st.cache_resource(show_spinner=False)
def get_openai_client(endpoint: str, api_version: str, api_key: str) -> AzureOpenAI:
    """Create one API-key authenticated Azure OpenAI client per Streamlit process."""
    if not endpoint.startswith(("https://", "http://")):
        raise ValueError(
            "AZURE_OPENAI_ENDPOINT must be an Azure OpenAI endpoint URL, "
            "for example https://<resource>.openai.azure.com/."
        )
    return AzureOpenAI(
        api_version=api_version,
        azure_endpoint=endpoint,
        api_key=api_key,
    )


def new_conversation() -> None:
    """Reset the local multi-turn conversation."""
    st.session_state.messages = []
    st.session_state.connection_error = None


def ask_val(prompt: str) -> None:
    """Send a prompt to VAL and append its answer to local chat history."""
    endpoint, deployment, subscription_key, api_version = configuration()
    if not all((endpoint, deployment, subscription_key, api_version)):
        st.error(
            "Missing Azure OpenAI configuration. Add `AZURE_OPENAI_ENDPOINT`, "
            "`AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_KEY`, and "
            "`AZURE_OPENAI_API_VERSION` to `.env`, then restart Streamlit."
        )
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        client = get_openai_client(endpoint, api_version, subscription_key)
        conversation = [{"role": "system", "content": SYSTEM_PROMPT}, *st.session_state.messages]
        with st.chat_message("assistant"):
            with st.spinner("VAL is analyzing contract data..."):
                completion = client.chat.completions.create(
                    model=deployment,
                    messages=conversation,
                )
                response = completion.choices[0].message.content or (
                    "VAL completed the analysis but did not return a text response."
                )
            st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
    except AuthenticationError as error:
        st.error("Azure OpenAI rejected the API key.")
        st.info("Verify `AZURE_OPENAI_API_KEY` and the target Azure OpenAI resource.")
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

endpoint, deployment, subscription_key, api_version = configuration()

with st.sidebar:
    st.header("VAL Control Center")
    if all((endpoint, deployment, subscription_key, api_version)):
        st.success("● Azure OpenAI configuration detected")
    else:
        st.warning("● Configuration required")
        st.caption("Set the `AZURE_OPENAI_*` variables in `.env`.")

    st.subheader("Agent Information")
    st.markdown(
        f"**Name**  \n{AGENT_NAME}\n\n"
        f"**Model**  \n{deployment or MODEL_NAME}\n\n"
        f"**Mode**  \n{ANALYSIS_MODE}"
    )

    if st.button("＋ New Conversation", use_container_width=True):
        new_conversation()
        st.rerun()

    st.subheader("Quick Actions")
    for action in QUICK_ACTIONS:
        if st.button(action, use_container_width=True):
            st.session_state.pending_prompt = action

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

pending_prompt = st.session_state.pop("pending_prompt", None)
prompt = pending_prompt or st.chat_input("Ask VAL about your vendor and contract data...")
if prompt:
    ask_val(prompt)
