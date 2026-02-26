import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

ARCADE_API_KEY = os.environ["ARCADE_API_KEY"]
ARCADE_USER_ID = os.environ["ARCADE_USER_ID"]
ARCADE_GATEWAY_URL = os.environ["ARCADE_GATEWAY_URL"]
PIXELCORP_REPO = os.environ.get("PIXELCORP_GITHUB_REPO", "pong-init/pixelcorp-backend")
VP_ENG_EMAIL = os.environ.get("VP_ENG_EMAIL", "")


def get_mcp_client() -> MultiServerMCPClient:
    """Create an MCP client connected to the Arcade Gateway."""
    return MultiServerMCPClient({
        "arcade": {
            "transport": "streamable_http",
            "url": ARCADE_GATEWAY_URL,
            "headers": {
                "Authorization": f"Bearer {ARCADE_API_KEY}",
                "Arcade-User-Id": ARCADE_USER_ID,
            },
        }
    })


def get_model() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        google_api_key=os.environ["GOOGLE_API_KEY"],
    )


def get_langgraph_config(thread_id: str) -> dict:
    return {
        "configurable": {
            "thread_id": thread_id,
            "user_id": ARCADE_USER_ID,
        }
    }
