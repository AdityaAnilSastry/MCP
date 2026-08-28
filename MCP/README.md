# Modular Full-Stack LLM Chat Application with Model Context Protocol (MCP)

A production-ready, modular full-stack AI chat application implementing the **Model Context Protocol (MCP)**. The system integrates **Google Gemini** for inference with a local Python **MCP Server** via an official **MCP Client**, orchestrating dynamic tool execution over JSON-RPC 2.0 (stdio transport) and rendering through a responsive Tailwind CSS frontend.

---

## Architecture & MCP Flow

### Architectural Diagram

```
┌────────────────────────────────────────────────────────┐
│               Frontend (HTML5 / Tailwind CSS / JS)     │
│                 (chat_logic.js via fetch API)          │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP POST /api/chat
                            ▼
┌────────────────────────────────────────────────────────┐
│               FastAPI Backend (main.py)                │
│                 (CORS, Routing, Schemas)               │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│               LLM Service (llm_service.py)             │
│            (Google Gemini API + Tool Binding)          │
└───────────────┬────────────────────────▲───────────────┘
  1. Tool Call  │                        │ 4. Tool Result
    Request     ▼                        │    Synthesis
┌────────────────────────────────────────────────────────┐
│               MCP Client (mcp_client.py)               │
│         (ClientSession & stdio_client Transport)       │
└───────────────────────────┬────────────────────────────┘
                            │ 2. JSON-RPC (stdio)
                            ▼
┌────────────────────────────────────────────────────────┐
│               MCP Server (mcp_server.py)               │
│          (FastMCP Server exposing Tools)               │
│   • get_current_time(timezone_name)                    │
│   • calculate(expression)                              │
└────────────────────────────────────────────────────────┘
```

### Complete End-to-End Request/Response Flow:
1. **User Query**: The user types a question in the UI (e.g. *"What is the current time in Tokyo?"* or *"Calculate (256 * 48) + sqrt(144)"*).
2. **Frontend Dispatch**: `frontend/js/chat_logic.js` submits `POST /api/chat` with `{ message: "...", history: [...] }`.
3. **Tool Discovery**: `backend/llm_service.py` connects to `backend/mcp_client.py` and retrieves available tools and input schemas via `session.list_tools()`.
4. **Tool Registration**: MCP tool schemas are converted into Gemini Function Declarations and passed into Gemini's `generate_content` request.
5. **Model Decision**: Gemini analyzes the user prompt and determines that a tool call is required (e.g., `get_current_time(timezone_name="Asia/Tokyo")`).
6. **MCP Tool Execution**:
   - `mcp_client.py` opens a stdio subprocess connection to `mcp_server.py`.
   - Sends a JSON-RPC `CallToolRequest`.
   - `mcp_server.py` evaluates the tool function safely and returns structured output.
7. **Context Synthesis**: The tool result is injected back into the Gemini conversation turn as a function response. Gemini synthesizes the final natural language answer.
8. **Frontend Rendering**: FastAPI returns JSON containing the final response and metadata (`tools_used: [...]`). The UI renders the response with a badge displaying the executed MCP tool.

---

## 📁 Repository Structure

```
project-root/
├── backend/
│   ├── main.py              # FastAPI application, routes, CORS middleware
│   ├── llm_service.py       # Gemini LLM integration & MCP tool binding
│   ├── mcp_client.py        # Official MCP ClientSession & stdio client
│   ├── mcp_server.py        # MCP Tool Server (get_current_time, calculate)
│   ├── requirements.txt     # Python dependencies
│   ├── .env.example         # Template for environment variables
│   └── .env                 # Secret environment variables (ignored by Git)
├── frontend/
│   ├── index.html           # HTML5 structure (Header, Chat Area, Sticky Input)
│   ├── css/
│   │   └── styles.css       # Custom styles, animations, scrollbars, markdown
│   └── js/
│       └── chat_logic.js    # Async fetch logic, history state, UI updates
├── .gitignore               # Excludes .env, virtual environments, caches
└── README.md                # Project documentation and execution guide
```

---

## ⚙️ Prerequisites

- **Python 3.10+** (Tested on Python 3.10.7)
- **A modern web browser** (Chrome, Firefox, Edge, Safari)
- **Google Gemini API Key** (Free tier available at [Google AI Studio](https://aistudio.google.com/))

---

## 🚀 Setup & Execution Instructions

### 1. Set Up Virtual Environment

Open a terminal (PowerShell, Command Prompt, or Bash) in the project root directory:

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

Install the locked requirements from `backend/requirements.txt`:

```bash
pip install -r backend/requirements.txt
```

### 3. Configure Environment Variables

Create your `.env` file in the `backend/` directory:

```bash
# Copy example file
copy backend\.env.example backend\.env    # Windows CMD
cp backend/.env.example backend/.env       # Linux / macOS / PowerShell
```

Edit `backend/.env` and add your Gemini API key:

```env
# Get key from https://aistudio.google.com/
GEMINI_API_KEY=your_actual_gemini_api_key_here

GEMINI_MODEL=gemini-2.5-flash
PORT=8000
LOG_LEVEL=INFO
```

> **Note:** If you run without a `GEMINI_API_KEY`, the application operates in **Live MCP Demo Mode**, allowing you to execute and test MCP tools directly with informative notices.

---

### 4. Start the FastAPI Backend

Run the backend server using `uvicorn`:

```bash
# From the project root
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Or run directly with Python:

```bash
python backend/main.py
```

The backend server will start at: `http://localhost:8000`  
- Swagger API Docs: `http://localhost:8000/docs`
- Healthcheck Endpoint: `http://localhost:8000/api/health`
- MCP Tools List: `http://localhost:8000/api/tools`

---

### 5. Serve the Frontend

You can serve the frontend using any static web server or Python's built-in HTTP server:

```bash
# In a new terminal window:
python -m http.server 3000 --directory frontend
```

Now open your browser and navigate to: **`http://localhost:3000`**

*(Alternatively, you can also open `frontend/index.html` directly in your browser or use the VS Code Live Server extension).*

---

## 🧪 Demonstrating MCP to an Evaluator / Professor

Here is how you can effectively demonstrate the genuine MCP integration:

### 1. Test MCP Time Tool (`get_current_time`)
Ask:
- *"What is the current time in Tokyo, London, and New York?"*
- *"What day of the week is it in India right now?"*

**What happens:**
1. Gemini recognizes it has no internal real-time clock.
2. It requests a tool call to `get_current_time` with the target timezone.
3. The backend MCP Client communicates with the MCP Server over stdio.
4. The MCP server returns the real timestamp and timezone offset.
5. The UI shows a badge: `🛠️ MCP: get_current_time`.

### 2. Test MCP Math Tool (`calculate`)
Ask:
- *"Calculate (256 * 48) + sqrt(144)"*
- *"What is 2^16 - 1024?"*

**What happens:**
1. Gemini calls the MCP `calculate` tool with the expression.
2. The MCP server safely evaluates the AST expression.
3. The exact mathematical answer is returned to Gemini and synthesized in the answer.
4. The UI displays the `🛠️ MCP: calculate` tool badge.

### 3. Inspect Live Health & Tools API
- Open `http://localhost:8000/api/health` to demonstrate live MCP status and active tools.
- Open `http://localhost:8000/api/tools` to view the JSON Schemas exported directly by the MCP Server.

---

## 🛡️ Error Handling & Edge Cases

The application handles edge cases gracefully:
- **Empty Messages**: Frontend validates input before sending; backend returns `400 Bad Request` if an empty payload is submitted.
- **MCP Server Timeout**: If the MCP server subprocess is slow or unresponsiveness, `asyncio.wait_for` triggers a timeout and returns a user-friendly notice without crashing the server.
- **Math Evaluation Safety**: Expressions evaluated by `calculate` use an AST validator allowing only safe arithmetic operations, preventing arbitrary code injection.
- **Backend Offline**: If the backend is stopped, the frontend displays an active error banner and retry button.
- **Missing API Keys**: Handled gracefully with informational banners and fallback live MCP execution.

---

