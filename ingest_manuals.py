"""Read the Nissan Patrol manuals into the local search DB.

Run from the project root:  python ingest_manuals.py
(First run downloads a small local embedding model ~ once.)
"""
from src.library.ingest import ingest

if __name__ == "__main__":
    ingest(subdir="nissan-patrol-y61", reset=True)
