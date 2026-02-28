"""
Modal app definition.

Deploy:  modal deploy modal/app.py
Serve (dev):  modal serve modal/app.py
"""

import modal

app = modal.App(name="hackillinois2026")

image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "pydantic==2.10.4",
)


@app.function(image=image)
def hello(name: str) -> str:
    """Placeholder function — replace with real workloads."""
    return f"Hello from Modal, {name}!"
