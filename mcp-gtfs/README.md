# mcp-gtfs MCP server

An MCP server project that enables access to GTFS and GTFS-RT data feeds.

## Components

### Resources

The server implements a simple note storage system with:
- Custom note:// URI scheme for accessing individual notes
- Each note resource has a name, description, and text/plain mimetype

### Prompts

The server provides a single prompt:
- summarize-notes: Creates summaries of all stored notes
  - Optional "style" argument to control detail level (brief/detailed)
  - Generates prompt combining all current notes with style preference

### Tools

The server implements one tool:
- add-note: Adds a new note to the server
  - Takes "name" and "content" as required string arguments
  - Updates server state and notifies clients of resource changes

## Configuration

### Environment Variables

Create a `.env` file at the root of the project with the URLs of the GTFS-RT feeds. An example is provided in `.env.example`:

```bash
# URLs of GTFS-RT feeds (default: Bibus Brest)
GTFS_VEHICLE_POSITIONS_URL=https://proxy.transport.data.gouv.fr/resource/bibus-brest-gtfs-rt-vehicle-position
GTFS_TRIP_UPDATES_URL=https://proxy.transport.data.gouv.fr/resource/bibus-brest-gtfs-rt-trip-update
GTFS_SERVICE_ALERTS_URL=https://proxy.transport.data.gouv.fr/resource/bibus-brest-gtfs-rt-alerts

# MCP Configuration
MCP_HOST=localhost
MCP_PORT=3000
MCP_TRANSPORT=stdio

# Data refresh interval (in seconds)
GTFS_REFRESH_INTERVAL=30
```

### Installation

1. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate     # Windows
```

2. Install dependencies:
```bash
pip install -e .
```

## Starting the Server

### With MCP Inspector (recommended)

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) provides a web interface to easily test endpoints:

```bash
npx @modelcontextprotocol/inspector uv --directory /home/pi/Documents/IF-SRV/SynologyDrive/create-python-server/mcp-gtfs run mcp-gtfs
```

The interface will be available at http://localhost:5173

### Direct Mode

To start the server without the Inspector:

```bash
python -m mcp_gtfs
```

## Testing Endpoints

The server exposes several GTFS-RT endpoints for different Breton transport networks:

### 1. List of Available Networks
```
GET gtfs://networks
```
Returns the list of configured networks (Bibus, STAR, TUB).

### 2. Vehicles by Network
```
GET gtfs://network/{network}/vehicles
```
Replace `{network}` with:
- `bibus` for Brest
- `star` for Rennes
- `tub` for Saint-Brieuc

Example response:
```json
{
    "status": "success",
    "network": "bibus",
    "data": [
        {
            "vehicle_id": "12345",
            "position": {
                "latitude": 48.3905,
                "longitude": -4.4860,
                "bearing": 180,
                "speed": 35
            },
            "trip_id": "ABC123",
            "route_id": "A",
            "current_status": "IN_TRANSIT_TO",
            "timestamp": "2025-03-21T00:55:35+01:00"
        }
    ],
    "count": 1,
    "timestamp": "2025-03-21T00:55:35+01:00"
}
```

### 3. Network Statistics
```
GET gtfs://network/stats
```
Returns global statistics about the network (active vehicles, delays, etc.).

## Debugging

For better debugging:

1. Logs are displayed in the console with:
- Called URLs
- Number of retrieved entities
- Any errors

2. Check raw GTFS-RT data:
```bash
curl -s GTFS_URL | protoc --decode_raw
```
Replace `GTFS_URL` with one of the feed URLs.

## Quickstart

### Install

#### Claude Desktop

On MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`
On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

<details>
  <summary>Development/Unpublished Servers Configuration</summary>
  ```
  "mcpServers": {
    "mcp-gtfs": {
      "command": "uv",
      "args": [
        "--directory",
        "/home/pi/Documents/IF-SRV/SynologyDrive/create-python-server/mcp-gtfs",
        "run",
        "mcp-gtfs"
      ]
    }
  }
  ```
</details>

<details>
  <summary>Published Servers Configuration</summary>
  ```
  "mcpServers": {
    "mcp-gtfs": {
      "command": "uvx",
      "args": [
        "mcp-gtfs"
      ]
    }
  }
  ```
</details>

## Development

### Building and Publishing

To prepare the package for distribution:

1. Sync dependencies and update lockfile:
```bash
uv sync
```

2. Build package distributions:
```bash
uv build
```

This will create source and wheel distributions in the `dist/` directory.

3. Publish to PyPI:
```bash
uv publish
```

Note: You'll need to set PyPI credentials via environment variables or command flags:
- Token: `--token` or `UV_PUBLISH_TOKEN`
- Or username/password: `--username`/`UV_PUBLISH_USERNAME` and `--password`/`UV_PUBLISH_PASSWORD`

### Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging
experience, we strongly recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).

You can launch the MCP Inspector via [`npm`](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) with this command:

```bash
npx @modelcontextprotocol/inspector uv --directory /home/pi/Documents/IF-SRV/SynologyDrive/create-python-server/mcp-gtfs run mcp-gtfs
```

Upon launching, the Inspector will display a URL that you can access in your browser to begin debugging.
