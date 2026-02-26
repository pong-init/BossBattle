import os
from dotenv import load_dotenv
from langchain_arcade import ToolManager
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

ARCADE_API_KEY = os.environ["ARCADE_API_KEY"]
ARCADE_USER_ID = os.environ["ARCADE_USER_ID"]
ARCADE_GATEWAY_URL = os.environ.get(
    "ARCADE_GATEWAY_URL", "https://api.arcade.dev/mcp/bossbattle-incident"
)
PIXELCORP_REPO = os.environ.get("PIXELCORP_GITHUB_REPO", "pong-init/pixelcorp-backend")
VP_ENG_EMAIL = os.environ.get("VP_ENG_EMAIL", "")

# Initialize Arcade ToolManager
manager = ToolManager(api_key=ARCADE_API_KEY)
manager.init_tools(toolkits=["GitHub", "Linear", "Slack", "Gmail"])
tools = manager.to_langchain(use_interrupts=True)
tools_by_name = {t.name: t for t in tools}

# Gemini model
model = ChatGoogleGenerativeAI(
    model="gemini-2.5-pro",
    google_api_key=os.environ["GOOGLE_API_KEY"],
)
model_with_tools = model.bind_tools(tools)

# LangGraph config — user_id required for Arcade auth
def get_langgraph_config(thread_id: str) -> dict:
    return {
        "configurable": {
            "thread_id": thread_id,
            "user_id": ARCADE_USER_ID,
        }
    }
