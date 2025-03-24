import reflex as rx
import asyncio
import ollama
import re
import json
import logging
from mcp.client.sse import sse_client
from mcp.types import JSONRPCMessage
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:3001/sse")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
SYSTEM_PROMPT = "Vous êtes un assistant utile pour Brest utilisant exclusivement les outils MCP."

class MCPState(rx.State):
    query: str = ""
    messages: list[dict] = []
    tools: list[dict] = []
    loading: bool = False

    async def fetch_tools(self):
        async with sse_client(MCP_SERVER_URL) as (read_stream, write_stream):
            await write_stream.send(JSONRPCMessage(
                jsonrpc="2.0",
                method="initialize",
                params={"protocolVersion": "1.0", "capabilities": {}, "clientInfo": {"name": "Reflex-Client", "version": "1.0"}},
                id=0
            ))

            # Attends explicitement la fin de l'initialisation
            initialized = False
            async for message in read_stream:
                if message.root.id == 0:
                    initialized = True
                    break

            if not initialized:
                raise RuntimeError("Échec de l'initialisation du serveur MCP")

            # Une fois initialisé, tu peux appeler tools/list
            await write_stream.send(JSONRPCMessage(jsonrpc="2.0", method="tools/list", params={}, id=1))
            async for message in read_stream:
                if message.root.id == 1:
                    return message.root.result["tools"]
            return []

    async def call_tool(self, tool_name, tool_args=None):
        async with sse_client(MCP_SERVER_URL) as (read_stream, write_stream):
            await write_stream.send(JSONRPCMessage(
                jsonrpc="2.0",
                method="initialize",
                params={"protocolVersion": "1.0", "capabilities": {}, "clientInfo": {"name": "Reflex-Client", "version": "1.0"}},
                id=0
            ))

            initialized = False
            async for message in read_stream:
                if message.root.id == 0:
                    initialized = True
                    break

            if not initialized:
                raise RuntimeError("Échec de l'initialisation du serveur MCP")

            request_id = int(datetime.now().timestamp())
            await write_stream.send(JSONRPCMessage(
                jsonrpc="2.0",
                method="tools/call",
                params={"name": tool_name, "args": tool_args or {}},
                id=request_id
            ))
            async for message in read_stream:
                if message.root.id == request_id:
                    return message.root.result
            return {}

    async def process_query(self):
        self.loading = True
        tools_description = "\n".join([f"- {tool['name']}: {tool['description']}" for tool in self.tools])
        prompt = f"""
        {SYSTEM_PROMPT}

        Outils disponibles :
        {tools_description}

        Question : {self.query}
        Utilisez les outils en appelant explicitement [call_tool:nom_du_tool] si nécessaire.
        """

        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )

        answer = response["message"]["content"]
        matches = re.findall(r"\[call_tool:(\w+)\]", answer)

        for tool_name in matches:
            result = await self.call_tool(tool_name)
            answer = answer.replace(f"[call_tool:{tool_name}]", json.dumps(result, ensure_ascii=False))

        self.messages.append({"role": "user", "content": self.query})
        self.messages.append({"role": "assistant", "content": answer})
        self.query = ""
        self.loading = False

    # Méthode correcte pour charger au lancement
    async def on_load(self):
        self.tools = await self.fetch_tools()

def index():
    return rx.vstack(
        rx.heading("Chatbot Brest - Informations en temps réel", size="6"),
        rx.box(
            rx.foreach(MCPState.messages, lambda msg:
                rx.box(
                    rx.markdown(msg["content"], width="100%"),
                    bg=rx.cond(msg["role"] == "assistant", "gray.100", "blue.100"),
                    border_radius="md",
                    padding="3",
                    margin_y="1"
                )
            ),
            width="100%",
            height="60vh",
            overflow_y="scroll",
            padding="4",
            border="1px solid #eaeaea",
            border_radius="lg",
        ),
        rx.input(
            placeholder="Votre question ici",
            on_change=MCPState.set_query,
            value=MCPState.query,
            is_disabled=MCPState.loading
        ),
        rx.button(
            "Envoyer",
            on_click=MCPState.process_query,
            is_loading=MCPState.loading
        ),
        spacing="4",
        padding="6",
        max_width="600px",
        margin="auto"
    )

app = rx.App()
app.add_page(index)

if __name__ == "__main__":
    app.run()
