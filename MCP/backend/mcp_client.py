"""
MCP Client Module
Handles connection and interaction with the MCP Server over stdio transport.
Uses the official Model Context Protocol (MCP) Python SDK (ClientSession, stdio_client).
Compatible with Python 3.10+.
"""

import sys
import os
import asyncio
import logging
from typing import Dict, Any, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class MCPClientService:
    def __init__(self, server_script_path: Optional[str] = None):
        """
        Initialize the MCP Client with the path to the MCP server script.
        """
        if server_script_path is None:
            # Default to backend/mcp_server.py
            current_dir = os.path.dirname(os.path.abspath(__file__))
            server_script_path = os.path.join(current_dir, "mcp_server.py")
        
        self.server_script_path = server_script_path
        self.python_executable = sys.executable

    def _get_server_params(self) -> StdioServerParameters:
        """Create StdioServerParameters for launching the MCP server subprocess."""
        # Ensure UTF-8 encoding for stdio communication on Windows
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        
        return StdioServerParameters(
            command=self.python_executable,
            args=[self.server_script_path],
            env=env
        )

    async def _list_tools_internal(self) -> List[Dict[str, Any]]:
        server_params = self._get_server_params()
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                
                tool_list = []
                for tool in tools_result.tools:
                    tool_list.append({
                        "name": tool.name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema if hasattr(tool, "inputSchema") else {}
                    })
                return tool_list

    async def list_tools(self, timeout: float = 10.0) -> List[Dict[str, Any]]:
        """
        Connects to the MCP server, initializes a session, and lists available tools.
        
        Returns:
            A list of dictionaries with tool definitions (name, description, inputSchema).
        """
        try:
            return await asyncio.wait_for(self._list_tools_internal(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error("MCP Server connection timed out while listing tools.")
            raise RuntimeError("MCP Server connection timed out.")
        except Exception as e:
            logger.error(f"Failed to list MCP tools: {e}", exc_info=True)
            raise RuntimeError(f"Failed to communicate with MCP Server: {str(e)}")

    async def _call_tool_internal(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        server_params = self._get_server_params()
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments)
                
                # Extract text content from MCP result blocks
                text_outputs = []
                if hasattr(result, "content") and result.content:
                    for content_item in result.content:
                        if hasattr(content_item, "text"):
                            text_outputs.append(content_item.text)
                        else:
                            text_outputs.append(str(content_item))
                
                output_str = "\n".join(text_outputs) if text_outputs else "Tool executed successfully (no output returned)."
                
                if hasattr(result, "isError") and result.isError:
                    return f"[MCP Tool Error]: {output_str}"
                    
                return output_str

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], timeout: float = 15.0) -> str:
        """
        Connects to the MCP server, initializes a session, and executes a specific tool.
        
        Args:
            tool_name: The name of the tool to execute.
            arguments: The arguments dictionary for the tool.
            timeout: Timeout in seconds.
            
        Returns:
            The string output from the MCP tool.
        """
        try:
            return await asyncio.wait_for(self._call_tool_internal(tool_name, arguments), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"MCP tool '{tool_name}' timed out after {timeout}s.")
            return f"[Error]: MCP Server call for tool '{tool_name}' timed out."
        except Exception as e:
            logger.error(f"MCP tool '{tool_name}' execution failed: {e}", exc_info=True)
            return f"[Error]: Failed to execute MCP tool '{tool_name}': {str(e)}"


# Singleton instance for easy import across the backend
mcp_client = MCPClientService()
