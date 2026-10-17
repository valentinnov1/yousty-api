"""Start this example: python run.py"""

from pathlib import Path

import uvicorn

if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        app_dir=str(folder),
        reload_dirs=[str(folder)],
    )
