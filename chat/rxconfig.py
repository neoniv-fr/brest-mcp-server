import reflex as rx

config = rx.Config(
    app_name="chat",
    frontend_port=3003,
    backend_port=8008,
    api_url="http://localhost:8008",
    telemetry_enabled=False,
)
