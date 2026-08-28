"""
MCP Server Implementation using Model Context Protocol (MCP) Python SDK.
This server exposes two genuine MCP tools:
1. get_current_time: Returns the current date and time for a given timezone.
2. calculate: Evaluates mathematical expressions safely.
"""

import ast
import math
import operator
from datetime import datetime, timezone, timedelta
import zoneinfo
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("SimpleMCPToolsServer")

# Safe Math Evaluator using AST
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

SAFE_FUNCTIONS = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "abs": abs,
    "round": round,
    "pow": math.pow,
    "factorial": math.factorial,
}

SAFE_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
}


def _eval_ast(node):
    if isinstance(node, ast.Constant):  # Python 3.8+ numbers/constants
        return node.value
    elif isinstance(node, ast.BinOp):
        left = _eval_ast(node.left)
        right = _eval_ast(node.right)
        op_type = type(node.op)
        if op_type in SAFE_OPERATORS:
            return SAFE_OPERATORS[op_type](left, right)
        raise ValueError(f"Unsupported binary operator: {op_type.__name__}")
    elif isinstance(node, ast.UnaryOp):
        operand = _eval_ast(node.operand)
        op_type = type(node.op)
        if op_type in SAFE_OPERATORS:
            return SAFE_OPERATORS[op_type](operand)
        raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in SAFE_FUNCTIONS:
            args = [_eval_ast(arg) for arg in node.args]
            return SAFE_FUNCTIONS[node.func.id](*args)
        raise ValueError(f"Unsupported function call: {getattr(node.func, 'id', 'unknown')}")
    elif isinstance(node, ast.Name):
        if node.id in SAFE_CONSTANTS:
            return SAFE_CONSTANTS[node.id]
        raise ValueError(f"Unknown variable/constant: {node.id}")
    else:
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")


@mcp.tool()
def get_current_time(timezone_name: str = "UTC") -> str:
    """
    Get the current date and time for a specified timezone.
    
    Args:
        timezone_name: The timezone identifier (e.g., 'UTC', 'Asia/Kolkata', 'America/New_York', 'Europe/London', 'Asia/Tokyo', 'PST', 'EST', 'IST'). Defaults to 'UTC'.
    
    Returns:
        A formatted string with the current date, time, weekday, and timezone offset.
    """
    try:
        tz_aliases = {
            "ist": ("Asia/Kolkata", 5.5),
            "india": ("Asia/Kolkata", 5.5),
            "est": ("America/New_York", -5.0),
            "edt": ("America/New_York", -4.0),
            "pst": ("America/Los_Angeles", -8.0),
            "pdt": ("America/Los_Angeles", -7.0),
            "cst": ("America/Chicago", -6.0),
            "gmt": ("UTC", 0.0),
            "utc": ("UTC", 0.0),
            "tokyo": ("Asia/Tokyo", 9.0),
            "london": ("Europe/London", 0.0),
            "paris": ("Europe/Paris", 1.0),
            "berlin": ("Europe/Berlin", 1.0),
            "sydney": ("Australia/Sydney", 11.0),
        }
        
        cleaned_tz = timezone_name.strip()
        tz_key = cleaned_tz.lower()
        
        target_tz = None
        target_name = cleaned_tz
        
        # 1. Check aliases first
        if tz_key in tz_aliases:
            iana_name, offset_hours = tz_aliases[tz_key]
            try:
                target_tz = zoneinfo.ZoneInfo(iana_name)
                target_name = iana_name
            except Exception:
                target_tz = timezone(timedelta(hours=offset_hours), name=tz_key.upper())
                target_name = f"{tz_key.upper()} (UTC{'+' if offset_hours>=0 else ''}{offset_hours})"
        
        # 2. Try direct zoneinfo lookup
        if target_tz is None:
            try:
                target_tz = zoneinfo.ZoneInfo(cleaned_tz)
                target_name = cleaned_tz
            except Exception:
                # 3. Fallback to UTC
                target_tz = timezone.utc
                target_name = f"UTC (fallback, requested '{timezone_name}')"
        
        now = datetime.now(target_tz)
        formatted_time = now.strftime("%Y-%m-%d %H:%M:%S %Z (UTC%z)")
        day_of_week = now.strftime("%A")
        
        return (
            f"Current Time: {formatted_time}\n"
            f"Day: {day_of_week}\n"
            f"Timezone: {target_name}"
        )
    except Exception as e:
        return f"Error retrieving time for timezone '{timezone_name}': {str(e)}"


@mcp.tool()
def calculate(expression: str) -> str:
    """
    Safely evaluate a mathematical expression.
    
    Args:
        expression: A mathematical expression string, e.g. '(256 * 48) + (1024 / 8)' or 'sqrt(144) + 5^2'.
        
    Returns:
        The calculated result or an error message if invalid.
    """
    try:
        sanitized = expression.replace("^", "**").strip()
        parsed = ast.parse(sanitized, mode="eval")
        result = _eval_ast(parsed.body)
        
        if isinstance(result, float) and result.is_integer():
            result = int(result)
            
        return f"Result: {result}"
    except Exception as e:
        return f"Error evaluating expression '{expression}': {str(e)}"


if __name__ == "__main__":
    # Run server on stdio transport for MCP clients
    mcp.run(transport="stdio")
