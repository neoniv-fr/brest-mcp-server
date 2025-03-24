import asyncio
import json
import os
import sys
from typing import Optional
import requests
from mcp.client.sse import sse_client
from dotenv import load_dotenv
import logging

# Charger les variables d'environnement
load_dotenv()

# Configuration
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
MCP_HOST = os.getenv("MCP_HOST", "localhost")
MCP_PORT = int(os.getenv("MCP_PORT", "3001"))
SSE_PATH = os.getenv("SSE_PATH", "/sse")
BASE_URL = f"http://{MCP_HOST}:{MCP_PORT}"
SSE_URL = f"{BASE_URL}{SSE_PATH}"

# Configuration du logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

class MCPClientSSE:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.sse_url = f"{base_url}{SSE_PATH}"
        self.session = requests.Session()
        self.running = False
        self.tools = []

    async def connect_to_server(self):
        """Établit une connexion au serveur MCP via SSE et récupère les outils disponibles."""
        try:
            logging.info(f"Connexion au serveur MCP via SSE : {self.sse_url}")
            # Récupérer la liste des outils via l'API HTTP
            tools_response = self.session.get(f"{self.base_url}/tools")
            tools_response.raise_for_status()
            self.tools = tools_response.json().get("tools", [])
            logging.info(f"Connecté au serveur avec les outils disponibles : {[tool['name'] for tool in self.tools]}")
            self.running = True
        except requests.RequestException as e:
            logging.error(f"Erreur de connexion au serveur MCP : {str(e)}")
            raise

    async def call_ollama(self, prompt: str) -> str:
        """Interroger LLaMA 3.2 via Ollama avec les outils disponibles."""
        tools_desc = "\n".join([f"- {tool['name']}: {tool.get('description', 'No description')}" for tool in self.tools])
        full_prompt = (
            f"Tu es un assistant utile. Voici la requête de l'utilisateur : '{prompt}'.\n"
            f"Tu as accès aux outils suivants du serveur MCP :\n{tools_desc}\n\n"
            "Si tu as besoin d'utiliser un outil, réponds au format JSON suivant :\n"
            "{\n"
            "    \"tool\": \"nom_de_l_outil\",\n"
            "    \"args\": { \"arg1\": \"valeur1\", ... }\n"
            "}"
        )

        payload = {"model": "llama3.2", "prompt": full_prompt, "stream": False}
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        result = response.json().get("response", "")
        return result

    async def process_query(self, query: str) -> str:
        """Traitement d'une requête avec LLaMA 3.2 et les outils MCP via SSE."""
        ollama_response = await self.call_ollama(query)

        try:
            tool_call = json.loads(ollama_response)
            if isinstance(tool_call, dict) and "tool" in tool_call:
                tool_name = tool_call["tool"]
                tool_args = tool_call.get("args", {})
                # Appeler l'outil via l'API HTTP du serveur MCP
                url = f"{self.base_url}/tools/{tool_name}"
                response = self.session.post(url, json={"args": tool_args})
                response.raise_for_status()
                result = response.json()
                return f"Résultat de l'outil {tool_name} : {json.dumps(result, indent=2)}"
        except json.JSONDecodeError:
            return ollama_response

        return ollama_response

    async def chat_loop(self):
        """Boucle interactive pour le CLI avec intégration SSE."""
        print("\nClient MCP avec LLaMA 3.2 démarré en mode SSE !")
        print("Tapez vos requêtes ou 'quit' pour quitter.")

        # Démarrer l'écoute SSE en arrière-plan
        sse_task = asyncio.create_task(self.listen_sse())

        while self.running:
            try:
                query = input("\nRequête : ").strip()
                if query.lower() == 'quit':
                    self.running = False
                    break
                response = await self.process_query(query)
                print("\n" + response)
            except Exception as e:
                print(f"\nErreur : {str(e)}")
        
        # Attendre la fin de la tâche SSE
        sse_task.cancel()
        try:
            await sse_task
        except asyncio.CancelledError:
            pass

    async def listen_sse(self):
        """Écoute les événements SSE en continu."""
        while self.running:
            try:
                response = self.session.get(self.sse_url, stream=True)
                response.raise_for_status()
                client = sse_client.SSEClient(response)
                logging.info("Écoute des événements SSE démarrée")
                
                for event in client.events():
                    if not self.running:
                        break
                    self.handle_event(event)
            except requests.RequestException as e:
                logging.error(f"Erreur dans l'écoute SSE : {str(e)}")
                await asyncio.sleep(5)  # Attendre avant de retenter
            finally:
                client.close() if 'client' in locals() else None

    def handle_event(self, event: sse_client.Event):
        """Traite un événement SSE reçu."""
        logging.debug(f"Événement brut reçu : {event}")
        if event.event == "message":
            try:
                data = json.loads(event.data)
                print(f"\n[Événement SSE] Message reçu : {json.dumps(data, indent=2)}")
            except json.JSONDecodeError:
                print(f"\n[Événement SSE] Données non JSON : {event.data}")
        elif event.event == "error":
            print(f"\n[Événement SSE] Erreur : {event.data}")
        else:
            print(f"\n[Événement SSE] Type {event.event} : {event.data}")

    async def cleanup(self):
        """Nettoyer les ressources."""
        self.running = False
        self.session.close()
        logging.info("Ressources nettoyées")

async def main():
    client = MCPClientSSE()
    try:
        await client.connect_to_server()
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())