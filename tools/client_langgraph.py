# Create server parameters for stdio connection
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from langchain_openai import AzureChatOpenAI


async def process_query(query: str):
    server_params = StdioServerParameters(
        command="python",
        # Make sure to update to the full absolute path to your math_server.py file
        args=["src/server.py"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()

            # Get tools
            tools = await load_mcp_tools(session)
            model = AzureChatOpenAI(azure_deployment="gpt-4o-mini")  # Azure deployment name
            # Create and run the agent
            agent = create_react_agent(model, tools)
            agent_response = await agent.ainvoke({"messages": query})
            print(agent_response)
            return agent_response


async def chat_loop():
    """Run an interactive chat loop"""
    print("\nMCP Client Started!")
    print("Type your queries or 'quit' to exit.")

    while True:
        try:
            query = input("\nQuery: ").strip()

            if query.lower() == "quit":
                break

            response = await process_query(query)
            print("\n" + response["messages"][-1].content)

        except Exception as e:
            print(f"\nError: {str(e)}")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)
    await chat_loop()


if __name__ == "__main__":
    import sys

    asyncio.run(main())
