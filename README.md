# VAL Vendor Analysis Agent

A Streamlit application for querying a deployed Azure AI Foundry vendor-analysis agent. It keeps a Foundry thread per browser session, renders agent responses as structured contract insights, and displays the end-to-end response time for every query.

## Features

- Azure AI Foundry agent integration using `AIProjectClient` and `DefaultAzureCredential`
- Persistent multi-turn conversations through Foundry threads
- Quick actions for tool overlaps, high-risk contracts, renewals, and missing clauses
- Selectable vendor-risk, procurement, and compliance-audit response personas
- Downloadable JSON exports of the active conversation
- Markdown response cleanup, including removal of Foundry citation markers
- Automatic extraction and rendering of Markdown contract tables
- Renewal status indicators for overdue, 7-day, and 30-day deadlines
- Response-time capture for each agent query, displayed beneath each assistant response
- New Conversation control for starting a fresh Foundry thread

## Prerequisites

- Python 3.11 or later
- A deployed Azure AI Foundry VAL agent
- Azure CLI authentication or another `DefaultAzureCredential` source with access to the Foundry project

## Configure

Create a local `.env` file in the repository root:

```dotenv
AZURE_AIPROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
AZURE_VAL_AGENT_ID=<your-agent-id>
```

Authenticate with Azure CLI when developing locally:

```bash
az login
```

The Azure identity must be authorized to access the Foundry project and agent. Do not commit `.env` or credentials.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open the URL shown by Streamlit, usually `http://localhost:8501`.

## Response timing

The app measures the time from the agent request through completion, including message submission, run polling, and assistant-response retrieval. Each assistant response displays its elapsed time at the bottom and retains it when the chat is rerendered.
