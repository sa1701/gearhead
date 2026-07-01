"""Launch the GEARHEAD web app.

  python run_app.py
Then open http://127.0.0.1:8000 in your browser.
"""
import uvicorn

if __name__ == "__main__":
    print("GEARHEAD starting at http://127.0.0.1:8000  (Ctrl+C to stop)")
    uvicorn.run("src.web.server:app", host="127.0.0.1", port=8000, reload=False)
