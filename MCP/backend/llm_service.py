"""
LLM Service Module
Orchestrates communication with Google Gemini API and bridges LLM Tool Calls to the MCP Client.
"""

import os
import re
import logging
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types

from backend.mcp_client import mcp_client

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


def _convert_json_schema_to_gemini(prop: Dict[str, Any]) -> types.Schema:
    """Recursively converts a JSON Schema dict into a Gemini types.Schema."""
    t = prop.get("type", "string").lower() if isinstance(prop, dict) else "string"
    type_map = {
        "string": types.Type.STRING,
        "number": types.Type.NUMBER,
        "integer": types.Type.INTEGER,
        "boolean": types.Type.BOOLEAN,
        "object": types.Type.OBJECT,
        "array": types.Type.ARRAY,
    }
    schema_type = type_map.get(t, types.Type.STRING)
    desc = prop.get("description", "") if isinstance(prop, dict) else ""
    
    if schema_type == types.Type.OBJECT and "properties" in prop:
        props = {k: _convert_json_schema_to_gemini(v) for k, v in prop["properties"].items()}
        required = prop.get("required", [])
        return types.Schema(type=schema_type, description=desc, properties=props, required=required)
    elif schema_type == types.Type.ARRAY and "items" in prop:
        return types.Schema(type=schema_type, description=desc, items=_convert_json_schema_to_gemini(prop["items"]))
    
    return types.Schema(type=schema_type, description=desc)


class LLMService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
        self._client: Optional[genai.Client] = None
        if self.api_key:
            self._client = genai.Client(api_key=self.api_key)

    def is_configured(self) -> bool:
        """Returns True if a valid Gemini API key is configured."""
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        return bool(self.api_key)

    async def _get_gemini_tools(self) -> Optional[List[types.Tool]]:
        """Discovers tools from the MCP Server and builds Gemini Tool declarations."""
        try:
            mcp_tools = await mcp_client.list_tools()
            if not mcp_tools:
                return None
            
            function_declarations = []
            for t in mcp_tools:
                input_schema = t.get("input_schema", {})
                gemini_schema = _convert_json_schema_to_gemini(input_schema)
                
                func_decl = types.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"] or f"Execute {t['name']}",
                    parameters=gemini_schema
                )
                function_declarations.append(func_decl)
            
            return [types.Tool(function_declarations=function_declarations)]
        except Exception as e:
            logger.warning(f"Could not load MCP tools for Gemini: {e}")
            return None

    async def process_chat(self, user_message: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """
        Processes a chat request:
        1. Prepares prompt and history.
        2. Retrieves MCP tools and binds them to Gemini.
        3. Calls Gemini API.
        4. If Gemini calls an MCP tool, executes it via MCP Client and sends the tool result back.
        5. Returns the final generated response and metadata of any MCP tools used.
        """
        # Reload API key from env in case it was updated dynamically
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if self.api_key and (self._client is None or getattr(self, "_last_key", None) != self.api_key):
            self._client = genai.Client(api_key=self.api_key)
            self._last_key = self.api_key

        if not self.api_key or not self._client:
            # Fallback demo response explaining setup and showing direct MCP capability
            return await self._handle_unconfigured_demo(user_message)

        tools_used = []
        
        try:
            # Discover MCP Tools
            gemini_tools = await self._get_gemini_tools()
            
            # Format chat contents
            contents = []
            if history:
                for msg in history:
                    role = "user" if msg.get("role") == "user" else "model"
                    content_text = msg.get("content", "")
                    if content_text:
                        contents.append(types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=content_text)]
                        ))
            
            # Append latest user message
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_message)]
            ))
            
            config = types.GenerateContentConfig(
                system_instruction=(
                    "You are a helpful AI assistant equipped with real-time Model Context Protocol (MCP) tools: "
                    "'get_current_time' (for accurate local times across any timezone) and 'calculate' (for precise mathematical computations). "
                    "Always use these tools when asked about current dates/times or mathematical expressions. "
                    "Synthesize tool outputs clearly and naturally for the user."
                ),
                tools=gemini_tools,
                temperature=0.7,
            )
            
            # Initial LLM Call
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config
            )
            
            # Check for Function Calls (MCP Tools)
            if response.function_calls:
                # Append model's tool call turn to contents
                contents.append(response.candidates[0].content)
                
                tool_parts = []
                for call in response.function_calls:
                    tool_name = call.name
                    tool_args = call.args if isinstance(call.args, dict) else dict(call.args)
                    
                    logger.info(f"Gemini requested MCP tool: {tool_name} with args: {tool_args}")
                    
                    # Execute tool via MCP Client
                    tool_output = await mcp_client.call_tool(tool_name, tool_args)
                    
                    tools_used.append({
                        "tool": tool_name,
                        "arguments": tool_args,
                        "result": tool_output
                    })
                    
                    tool_parts.append(types.Part.from_function_response(
                        name=tool_name,
                        response={"result": tool_output}
                    ))
                
                # Append function responses to conversation
                contents.append(types.Content(role="user", parts=tool_parts))
                
                # Second LLM Call to generate final answer with tool context
                followup_response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config
                )
                
                final_text = followup_response.text or "Here is the information retrieved from the tool."
                return {
                    "response": final_text,
                    "tools_used": tools_used,
                    "model": self.model_name,
                    "success": True
                }
            
            # No tool call needed, return standard text response
            return {
                "response": response.text or "I processed your request.",
                "tools_used": [],
                "model": self.model_name,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Error in Gemini chat generation: {e}", exc_info=True)
            return {
                "response": f"An error occurred while communicating with Gemini API: {str(e)}",
                "tools_used": tools_used,
                "model": self.model_name,
                "success": False
            }

    async def _handle_unconfigured_demo(self, user_message: str) -> Dict[str, Any]:
        """
        Graceful fallback when GEMINI_API_KEY is not yet supplied.
        Detects time/math queries and executes genuine MCP tool to demonstrate the protocol flow.
        """
        lower = user_message.lower()
        tools_used = []
        
        # Check if user query matches get_current_time
        if any(w in lower for w in ["time", "clock", "date", "today", "timezone"]):
            tz = "UTC"
            if "tokyo" in lower or "japan" in lower:
                tz = "Asia/Tokyo"
            elif "ist" in lower or "india" in lower or "delhi" in lower or "mumbai" in lower:
                tz = "Asia/Kolkata"
            elif "london" in lower or "uk" in lower or "gmt" in lower:
                tz = "Europe/London"
            elif "new york" in lower or "est" in lower or "edt" in lower:
                tz = "America/New_York"
            elif "california" in lower or "pst" in lower or "los angeles" in lower:
                tz = "America/Los_Angeles"
                
            tool_output = await mcp_client.call_tool("get_current_time", {"timezone_name": tz})
            tools_used.append({"tool": "get_current_time", "arguments": {"timezone_name": tz}, "result": tool_output})
            
            return {
                "response": (
                    f"**[Demo / Live MCP Execution]**\n\n"
                    f"{tool_output}\n\n"
                    f"> *Note: `GEMINI_API_KEY` is not set in `backend/.env`. The above data was fetched live from the MCP Server (`get_current_time`). To enable full LLM responses, add your `GEMINI_API_KEY` to `backend/.env`.*"
                ),
                "tools_used": tools_used,
                "model": "MCP-Direct-Demo (Gemini Key Pending)",
                "success": True
            }
            
        # Check if user query matches calculate
        elif any(c in lower for c in ["calculate", "sqrt", "+", "*", "/", "math", "sum", "multiply"]):
            # Cleanly extract math expression: remove words like calculate, what is, please, etc.
            cleaned = re.sub(r'(?i)(calculate|what is|compute|solve|eval|\?|the result of)', '', user_message).strip()
            if not cleaned or not any(char.isdigit() for char in cleaned):
                cleaned = "256 * 48"
            
            tool_output = await mcp_client.call_tool("calculate", {"expression": cleaned})
            tools_used.append({"tool": "calculate", "arguments": {"expression": cleaned}, "result": tool_output})
            
            return {
                "response": (
                    f"**[Demo / Live MCP Execution]**\n\n"
                    f"Calculated expression `{cleaned}`:\n{tool_output}\n\n"
                    f"> *Note: `GEMINI_API_KEY` is not set in `backend/.env`. The calculation was processed live via the MCP Server (`calculate`). Add your `GEMINI_API_KEY` to `backend/.env` for full AI synthesis.*"
                ),
                "tools_used": tools_used,
                "model": "MCP-Direct-Demo (Gemini Key Pending)",
                "success": True
            }
            
        return {
            "response": (
                "Welcome to the **Full-Stack LLM + MCP Chat Application**!\n\n"
                "**To enable complete Gemini LLM generation:**\n"
                "1. Open `backend/.env`\n"
                "2. Set `GEMINI_API_KEY=your_actual_key_here`\n"
                "3. Restart the backend.\n\n"
                "**You can test MCP tools directly right now by asking:**\n"
                "- *\"What is the current time in Tokyo?\"*\n"
                "- *\"What is the time in India?\"*\n"
                "- *\"Calculate 256 * 48\"*\n"
                "- *\"Calculate sqrt(65536) + (100 * 5)\"*"
            ),
            "tools_used": [],
            "model": "None (Configuration Needed)",
            "success": True
        }


# Singleton instance
llm_service = LLMService()
