import datetime as dt
import os
import re
import time

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential


load_dotenv()


# =====================================================
# CONFIG
# =====================================================

PROJECT_ENDPOINT = os.getenv("AZURE_AIPROJECT_ENDPOINT")
AGENT_ID = os.getenv("AZURE_VAL_AGENT_ID")

QUICK_ACTIONS = (
    "📊 Detect Tool Overlaps",
    "⚠️ High Risk Contracts",
    "📅 Upcoming Renewals",
    "🔍 Audit Missing Clauses",
)


# =====================================================
# CLIENT
# =====================================================

@st.cache_resource(show_spinner=False)
def get_project_client() -> AIProjectClient:
    """Create and cache the Azure AI Project client."""

    if not PROJECT_ENDPOINT:
        raise RuntimeError(
            "AZURE_AIPROJECT_ENDPOINT is not configured."
        )

    credential = DefaultAzureCredential(
        exclude_interactive_browser_credential=False
    )

    return AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=credential,
    )


# =====================================================
# THREAD MANAGEMENT
# =====================================================

def create_thread() -> str:
    """Create a new agent conversation thread."""

    client = get_project_client()
    thread = client.agents.threads.create()

    return thread.id


def get_thread_id() -> str:
    """Return the current thread ID or create one if needed."""

    if "thread_id" not in st.session_state:
        st.session_state.thread_id = create_thread()

    return st.session_state.thread_id


def new_conversation() -> None:
    """Clear the current conversation and create a new thread."""

    st.session_state.messages = []
    st.session_state.thread_id = create_thread()

def render_response_time(seconds: float | None) -> None:
    """Display an end-to-end Foundry agent response time."""
    if seconds is not None:
        st.caption(f"⏱️ VAL response time: {seconds:.2f} seconds")


# =====================================================
# AGENT EXECUTION
# =====================================================

def invoke_agent(prompt: str) -> tuple[str, float]:
    """Send a prompt to the Azure AI agent and return text and response time."""

    if not AGENT_ID:
        raise RuntimeError(
            "AZURE_VAL_AGENT_ID is not configured."
        )

    start_time = time.perf_counter()

    client = get_project_client()
    thread_id = get_thread_id()

    client.agents.messages.create(
        thread_id=thread_id,
        role="user",
        content=prompt,
    )

    run = client.agents.runs.create(
        thread_id=thread_id,
        agent_id=AGENT_ID,
    )

    while run.status in {
        "queued",
        "in_progress",
        "cancelling",
    }:
        time.sleep(2)

        run = client.agents.runs.get(
            thread_id=thread_id,
            run_id=run.id,
        )

    if run.status == "requires_action":
        raise RuntimeError(
            "The agent requires an action that this application does not support."
        )

    if run.status != "completed":
        raise RuntimeError(
            f"Agent run failed with status: {run.status}"
        )

    response = client.agents.messages.get_last_message_by_role(
        thread_id=thread_id,
        role="assistant",
    )

    if response is None:
        raise RuntimeError(
            "The agent returned no assistant response."
        )

    response_text = extract_agent_text(response)

    elapsed_time = round(
        time.perf_counter() - start_time,
        2
    )

    return response_text, elapsed_time


def extract_agent_text(response) -> str:
    """
    Extract the assistant text from an Azure AI message.

    Supports both dictionary-style and SDK-object responses.
    """

    if response is None:
        return ""

    # Handle dictionary-style responses.
    if isinstance(response, dict):
        content = response.get("content", [])

        for item in content:
            if item.get("type") != "text":
                continue

            text_data = item.get("text", {})

            if isinstance(text_data, dict):
                return str(text_data.get("value", ""))

            return str(text_data)

        return ""

    # Handle SDK object responses.
    content = getattr(response, "content", [])

    for item in content:
        item_type = getattr(item, "type", None)

        if item_type != "text":
            continue

        text_data = getattr(item, "text", None)

        if text_data is None:
            continue

        text_value = getattr(text_data, "value", None)

        if text_value is not None:
            return str(text_value)

        return str(text_data)

    # Fallback for SDK versions exposing response.text.
    response_text = getattr(response, "text", None)

    if response_text is not None:
        text_value = getattr(response_text, "value", None)

        if text_value is not None:
            return str(text_value)

        return str(response_text)

    return str(response)


# =====================================================
# RESPONSE PROCESSING
# =====================================================

def clean_response(text: str) -> str:
    """Remove Azure Foundry citation markers and normalize whitespace."""

    if not text:
        return ""

    # Removes markers such as:
    #
    cleaned_text = re.sub(
        r"【[^】]*】",
        "",
        text,
    )

    # Remove excessive blank lines.
    cleaned_text = re.sub(
        r"\n{3,}",
        "\n\n",
        cleaned_text,
    )

    return cleaned_text.strip()


def is_markdown_separator(line: str) -> bool:
    """Return True when a line is a Markdown table separator."""

    cells = [
        cell.strip()
        for cell in line.strip().split("|")[1:-1]
    ]

    if not cells:
        return False

    return all(
        re.fullmatch(r":?-{3,}:?", cell) is not None
        for cell in cells
    )


def extract_table(response_text: str):
    """
    Extract the first Markdown table.

    Returns:
        intro_text, dataframe, remaining_text
    """

    lines = response_text.splitlines()
    table_start = None

    for index in range(len(lines) - 1):
        current_line = lines[index].strip()
        next_line = lines[index + 1].strip()

        if (
            current_line.startswith("|")
            and next_line.startswith("|")
            and is_markdown_separator(next_line)
        ):
            table_start = index
            break

    if table_start is None:
        return response_text.strip(), None, ""

    table_end = table_start

    while table_end < len(lines):
        if not lines[table_end].strip().startswith("|"):
            break

        table_end += 1

    table_lines = [
        line.strip()
        for line in lines[table_start:table_end]
        if line.strip()
    ]

    if len(table_lines) < 3:
        return response_text.strip(), None, ""

    headers = [
        value.strip()
        for value in table_lines[0].split("|")[1:-1]
    ]

    if not headers:
        return response_text.strip(), None, ""

    rows = []

    for line in table_lines[2:]:
        values = [
            value.strip()
            for value in line.split("|")[1:-1]
        ]

        if len(values) == len(headers):
            rows.append(values)

    if not rows:
        return response_text.strip(), None, ""

    dataframe = pd.DataFrame(
        rows,
        columns=headers,
    )

    intro_text = "\n".join(
        lines[:table_start]
    ).strip()

    remaining_text = "\n".join(
        lines[table_end:]
    ).strip()

    return intro_text, dataframe, remaining_text


def convert_to_date(value):
    """Convert a YYYY-MM-DD value to a date."""

    if value is None:
        return None

    value = str(value).strip()

    if value in {
        "",
        "-",
        "—",
        "N/A",
        "None",
        "NaN",
    }:
        return None

    try:
        return dt.datetime.strptime(
            value,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return None


def add_contract_status_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Add date, days remaining, and readable status columns."""

    dataframe = dataframe.copy()

    today = dt.date.today()

    if "Renewal date" in dataframe.columns:
        dataframe["Renewal date"] = dataframe[
            "Renewal date"
        ].apply(convert_to_date)

    if "Cancellation deadline" in dataframe.columns:
        dataframe["Cancellation deadline"] = dataframe[
            "Cancellation deadline"
        ].apply(convert_to_date)

    def calculate_status(row) -> str:
        cancellation_deadline = row.get(
            "Cancellation deadline"
        )

        renewal_date = row.get("Renewal date")

        if (
            cancellation_deadline is not None
            and cancellation_deadline < today
        ):
            return "Overdue"

        if renewal_date is not None:
            days_until_renewal = (
                renewal_date - today
            ).days

            if days_until_renewal <= 7:
                return "Due within 7 days"

            if days_until_renewal <= 30:
                return "Due within 30 days"

        return "Upcoming"

    def calculate_days_to_renewal(row):
        renewal_date = row.get("Renewal date")

        if renewal_date is None:
            return None

        return (
            renewal_date - today
        ).days

    dataframe["Days to renewal"] = dataframe.apply(
        calculate_days_to_renewal,
        axis=1,
    )

    dataframe["Status"] = dataframe.apply(
        calculate_status,
        axis=1,
    )

    return dataframe


def style_contract_table(dataframe: pd.DataFrame):
    """Apply background colors to contract status values."""

    def highlight_status(value):
        if value == "Overdue":
            return (
                "background-color: #ffcccc; "
                "color: #8b0000; "
                "font-weight: bold;"
            )

        if value == "Due within 7 days":
            return (
                "background-color: #ffe5b4; "
                "color: #8a4500; "
                "font-weight: bold;"
            )

        if value == "Due within 30 days":
            return (
                "background-color: #fff4cc; "
                "color: #735c00;"
            )

        if value == "Upcoming":
            return (
                "background-color: #d9f2d9; "
                "color: #246b24;"
            )

        return ""

    if "Status" not in dataframe.columns:
        return dataframe.style

    return dataframe.style.map(
        highlight_status,
        subset=["Status"],
    )


def format_display_dates(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Format date columns for display as DD-MM-YYYY."""

    dataframe = dataframe.copy()

    date_columns = [
        "Renewal date",
        "Cancellation deadline",
    ]

    for column in date_columns:
        if column in dataframe.columns:
            dataframe[column] = dataframe[column].apply(
                lambda value: (
                    value.strftime("%d-%m-%Y")
                    if value is not None
                    else "—"
                )
            )

    return dataframe


# =====================================================
# RESPONSE RENDERING
# =====================================================

def render_response(raw_response: str) -> None:
    """Render the agent response using structured Streamlit components."""

    response = clean_response(raw_response)

    if not response:
        st.info("The agent returned an empty response.")
        return

    intro_text, dataframe, remaining_text = extract_table(
        response
    )

    # Display introductory text above the table.
    if intro_text:
        st.markdown(intro_text)

    if dataframe is not None:
        dataframe = add_contract_status_columns(dataframe)

        total_contracts = len(dataframe)

        supplier_count = (
            dataframe["Supplier"].nunique()
            if "Supplier" in dataframe.columns
            else 0
        )

        overdue_count = (
            int(
                (
                    dataframe["Status"] == "Overdue"
                ).sum()
            )
            if "Status" in dataframe.columns
            else 0
        )

        due_within_30_count = (
            int(
                dataframe["Status"].isin(
                    [
                        "Overdue",
                        "Due within 7 days",
                        "Due within 30 days",
                    ]
                ).sum()
            )
            if "Status" in dataframe.columns
            else 0
        )

        st.subheader("Renewal Overview")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Contracts",
                total_contracts,
            )

        with col2:
            st.metric(
                "Suppliers",
                supplier_count,
            )

        with col3:
            st.metric(
                "Overdue deadlines",
                overdue_count,
            )

        with col4:
            st.metric(
                "Due within 30 days",
                due_within_30_count,
            )

        if overdue_count > 0:
            st.error(
                f"{overdue_count} cancellation deadline(s) "
                "have already passed."
            )
        elif due_within_30_count > 0:
            st.warning(
                "Some contracts require attention within "
                "the next 30 days."
            )
        else:
            st.success(
                "No overdue cancellation deadlines were found."
            )

        st.subheader("Renewal Schedule")

        display_dataframe = format_display_dates(
            dataframe
        )

        st.dataframe(
            style_contract_table(display_dataframe),
            use_container_width=True,
            hide_index=True,
        )

        if overdue_count > 0:
            overdue_dataframe = dataframe[
                dataframe["Status"] == "Overdue"
            ].copy()

            overdue_columns = [
                column
                for column in (
                    "Contract ID",
                    "Supplier",
                    "Contract name",
                    "Renewal date",
                    "Cancellation deadline",
                    "Status",
                )
                if column in overdue_dataframe.columns
            ]

            overdue_dataframe = format_display_dates(
                overdue_dataframe
            )

            with st.expander(
                "View overdue contracts",
                expanded=True,
            ):
                st.dataframe(
                    overdue_dataframe[overdue_columns],
                    use_container_width=True,
                    hide_index=True,
                )

    # Display callouts or remaining narrative after the table.
    if remaining_text:
        callout_markers = (
            "Actionable callouts",
            "Notes and callouts",
            "Notes and Recommendations",
        )

        matched_marker = next(
            (
                marker
                for marker in callout_markers
                if marker.lower() in remaining_text.lower()
            ),
            None,
        )

        if matched_marker:
            marker_pattern = re.compile(
                re.escape(matched_marker),
                re.IGNORECASE,
            )

            callout_text = marker_pattern.sub(
                "",
                remaining_text,
                count=1,
            ).strip()

            if callout_text:
                with st.expander(
                    "Actionable Callouts and Recommendations",
                    expanded=True,
                ):
                    st.markdown(callout_text)
        else:
            st.markdown(remaining_text)

# =====================================================
# PAGE
# =====================================================

st.set_page_config(
    page_title="VAL | Vendor Analysis",
    page_icon="📋",
    layout="wide",
)

st.title("Vendor Analysis Agent")

st.caption(
    "Ask VAL to identify cost, risk, renewal, governance, "
    "and vendor insights."
)


if "messages" not in st.session_state:
    st.session_state.messages = []

if "thread_id" not in st.session_state:
    st.session_state.thread_id = create_thread()


# =====================================================
# SIDEBAR
# =====================================================

with st.sidebar:
    st.header("VAL Control Center")

    if AGENT_ID:
        st.success("Connected")

        st.markdown(
            f"""
**Agent ID**

`{AGENT_ID}`
"""
        )
    else:
        st.error(
            "AZURE_VAL_AGENT_ID is missing from the .env file."
        )

    if st.button(
        "＋ New Conversation",
        use_container_width=True,
    ):
        new_conversation()
        st.rerun()

    st.subheader("Quick Actions")

    for action in QUICK_ACTIONS:
        if st.button(
            action,
            use_container_width=True,
        ):
            st.session_state.pending_prompt = action


# =====================================================
# EXISTING CHAT
# =====================================================

for message in st.session_state.messages:
    with st.chat_message(message["role"]):

        if message["role"] == "assistant":
            render_response(
                message["content"]
            )
            render_response_time(
                message.get("response_time")
            )

        else:
            st.markdown(
                message["content"]
            )

# =====================================================
# INPUT
# =====================================================

pending_prompt = st.session_state.pop(
    "pending_prompt",
    None,
)

prompt = pending_prompt or st.chat_input(
    "Ask VAL about your vendor and contract data..."
)


if prompt:
    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt,
        }
    )

    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        with st.chat_message("assistant"):
            with st.spinner("VAL is analyzing..."):
                response, response_time = invoke_agent(prompt)

            render_response(response)
            render_response_time(response_time)

        timestamp = dt.datetime.now().strftime(
            "%d-%m-%Y %H:%M:%S"
        )

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": response,
                "response_time": response_time,
                "timestamp": timestamp,
            }
        )

    except Exception as ex:
        st.error("Failed to invoke the VAL Agent.")

        with st.expander("Technical Details"):
            st.code(str(ex))