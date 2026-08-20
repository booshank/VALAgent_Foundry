# VAL Vendor Analysis Assistant
## Windows local deployment guide

This guide runs the current Streamlit application locally on Windows. The application uses the Azure OpenAI Python client with an Azure OpenAI endpoint, deployment name, API key, and API version. It does not require Azure CLI authentication or Azure AI Foundry thread access.

### 1. Prerequisites

Install:

- Python 3.11 or newer from https://www.python.org/downloads/windows/
- Git for Windows from https://git-scm.com/download/win (only if you need to clone the repository)

During Python installation, select **Add Python to PATH**.

### 2. Get the application

Open PowerShell and either clone the repository or change to the project folder:

```powershell
git clone <repository-url>
cd VALAgent_Foundry
```

If the application work is on a feature branch, check out that branch before installing dependencies:

```powershell
git checkout cursor/vendor-analysis-chat-a1f3
```

### 3. Create and activate a virtual environment

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks the activation script, allow it only for the current terminal session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 4. Configure Azure OpenAI credentials

Create a local configuration file:

```powershell
Copy-Item .env.example .env
notepad .env
```

Replace every placeholder in `.env`:

```dotenv
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

Use the endpoint and one of the API keys shown on the Azure OpenAI resource's **Keys and Endpoint** page. Use the deployment name from the Azure AI Foundry/Azure OpenAI deployment page; it can differ from the underlying model name.

Keep `.env` private. It is ignored by Git and must never be committed or shared. If an API key was exposed in source control, rotate it in Azure immediately and update `.env` with the replacement.

### 5. Run the application

With the virtual environment still active:

```powershell
streamlit run app.py
```

Open the URL Streamlit prints, normally:

```text
http://localhost:8501
```

Stop the server with `Ctrl+C`.

### 6. Verify the application

1. The sidebar should show **Azure OpenAI configuration detected**.
2. Confirm the sidebar model equals your deployment name.
3. Click **New Conversation**.
4. Send a prompt such as `Summarize the highest contract risks.`
5. Verify the assistant responds and that a follow-up question retains the prior chat context.

### Troubleshooting

| Symptom | Cause and resolution |
| --- | --- |
| `py` is not recognized | Reinstall Python and select **Add Python to PATH**, then open a new PowerShell window. |
| `streamlit` is not recognized | Activate `.venv` and run `pip install -r requirements.txt` again. |
| Configuration required | Check all four `AZURE_OPENAI_*` values in `.env`; restart Streamlit after editing the file. |
| Azure OpenAI rejected the API key | Verify the key belongs to the resource in `AZURE_OPENAI_ENDPOINT`; rotate and replace the key if needed. |
| Deployment not found | Set `AZURE_OPENAI_DEPLOYMENT` to the Azure deployment name, not only the model name. |
| Network or firewall error | Configure Azure OpenAI resource networking to allow the Windows machine's network, or use the organization-approved private endpoint/VPN path. |

### Security checklist

- Store secrets only in `.env` or a managed secret store.
- Do not place credentials in `app.py`, `.env.example`, screenshots, tickets, or commits.
- Use a least-privilege Azure OpenAI key and rotate it according to your organization's policy.
- Restrict Azure OpenAI network access according to your organization's security requirements.
