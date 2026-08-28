"""
FastAPI Backend Application
Entry point for the Modular Full-Stack LLM + MCP Chat Application.
Exposes REST endpoints (/api/chat, /api/health, /api/tools) and configures CORS middleware.
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from backend.mcp_client import mcp_client
from backend.llm_service import llm_service

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("MCPChatBackend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to check services on startup."""
    logger.info("Initializing MCP Chat Backend...")
    try:
        tools = await mcp_client.list_tools()
        logger.info(f"Connected to MCP Server. Available tools: {[t['name'] for t in tools]}")
    except Exception as e:
        logger.warning(f"MCP Server initial probe warning: {e}. (Will retry on-demand)")
    yield
    logger.info("Shutting down MCP Chat Backend.")


# Initialize FastAPI App
app = FastAPI(
    title="Modular LLM + MCP Chat API",
    description="Full-stack AI Chat API integrating Google Gemini with Model Context Protocol (MCP) tools.",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for local frontend serving and file:// access
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request and Response Schemas ---
class ChatMessage(BaseModel):
    role: str = Field(..., description="Role: 'user' or 'model' / 'assistant'")
    content: str = Field(..., description="Text content of the message")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User query message")
    history: Optional[List[ChatMessage]] = Field(default=[], description="Previous conversation turns")


class ChatResponse(BaseModel):
    response: str
    tools_used: List[Dict[str, Any]] = []
    model: Optional[str] = None
    success: bool = True


# --- API Routes ---
@app.get("/")
async def root():
    """Root status endpoint."""
    return {
        "project": "Modular Full-Stack LLM + MCP Chat Application",
        "status": "online",
        "docs_url": "/docs"
    }


@app.get("/api/health")
async def health_check():
    """
    Healthcheck endpoint reporting backend status, Gemini configuration, and MCP server status.
    """
    mcp_status = "unavailable"
    available_tools = []
    
    try:
        tools = await mcp_client.list_tools(timeout=5.0)
        available_tools = [t["name"] for t in tools]
        mcp_status = "connected"
    except Exception as e:
        logger.warning(f"Healthcheck MCP probe failed: {e}")
        mcp_status = f"error: {str(e)}"
    
    return {
        "status": "healthy",
        "llm_provider": "Google Gemini",
        "gemini_configured": llm_service.is_configured(),
        "gemini_model": llm_service.model_name,
        "mcp_status": mcp_status,
        "mcp_tools": available_tools
    }


@app.get("/api/tools")
async def get_tools():
    """Returns the list of tools discovered from the MCP Server."""
    try:
        tools = await mcp_client.list_tools()
        return {"tools": tools, "count": len(tools)}
    except Exception as e:
        logger.error(f"Error fetching MCP tools: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"MCP Server unreachable: {str(e)}"
        )


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Primary chat endpoint.
    Accepts user message and history, invokes Gemini LLM with dynamic MCP tools, and returns the response.
    """
    user_msg = request.message.strip()
    if not user_msg:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty."
        )
    
    # Convert history models to dicts
    history_dicts = [{"role": msg.role, "content": msg.content} for msg in request.history]
    
    try:
        result = await llm_service.process_chat(user_msg, history=history_dicts)
        return ChatResponse(
            response=result.get("response", "No response generated."),
            tools_used=result.get("tools_used", []),
            model=result.get("model", "unknown"),
            success=result.get("success", True)
        )
    except Exception as e:
        logger.error(f"Error processing chat in endpoint: {e}", exc_info=True)
        return ChatResponse(
            response=f"Server error: {str(e)}",
            tools_used=[],
            model=llm_service.model_name,
            success=False
        )


if __name__ == "__main__":
    import uvicorn
    # Allow running directly via python backend/main.py
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
