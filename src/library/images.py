"""Diagrams (Step 4): render the real manual pages to images, and let Claude
*see* them so it can tell the user what they're looking at.
"""
from __future__ import annotations

import base64

import fitz  # PyMuPDF

from ..ai import get_provider
from ..config import settings


def render_page(subdir: str, source_file: str, page: int, dpi: int = 150) -> str:
    """Render one manual page to a PNG and return its path."""
    settings.images_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = settings.manuals_dir / subdir / source_file
    out_path = settings.images_dir / f"{subdir}__{source_file.replace('.pdf', '')}__p{page}.png"

    doc = fitz.open(pdf_path)
    zoom = dpi / 72  # 72 dpi is the PDF default; scale up for a crisp image
    pix = doc[page - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    pix.save(out_path)
    doc.close()
    return str(out_path)


def _image_block(png_path: str) -> dict:
    data = base64.b64encode(open(png_path, "rb").read()).decode()
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": data},
    }


def illustrate(problem: str, hits: list[dict], subdir: str, max_images: int = 2) -> dict:
    """Render the top referenced manual pages and have Claude caption them.

    Returns {'images': [paths], 'captions': str}.
    """
    # Unique (file, page) pairs, in relevance order.
    seen: list[tuple[str, int]] = []
    for h in hits:
        key = (h["source_file"], h["page"])
        if key not in seen:
            seen.append(key)
        if len(seen) >= max_images:
            break

    images = [render_page(subdir, sf, pg) for sf, pg in seen]

    brain = get_provider()
    if not getattr(brain, "supports_vision", True):
        # Text-only brain (Ollama): still show the real manual pages, but caption
        # them from chunk metadata instead of having a model read the diagram.
        sections = {(h["source_file"], h["page"]): h["section"] for h in hits}
        captions = "\n".join(
            f"Page {i}: {sections.get((sf, pg), 'Manual')} — {sf} p.{pg}, "
            "the manual page this fix cites."
            for i, (sf, pg) in enumerate(seen, 1)
        )
        return {"images": images, "captions": captions}

    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"PROBLEM: {problem}\n\n"
                f"Here are {len(images)} manual pages referenced in the fix, in order. "
                "For each, in ONE short, practical sentence, say what it shows and what "
                "the user should focus on. Label them 'Page 1', 'Page 2', etc. If a page "
                "has no useful diagram, say so."
            ),
        }
    ]
    content += [_image_block(p) for p in images]

    captions = brain.complete(
        system="You are GEARHEAD. Describe workshop-manual diagram pages briefly and practically.",
        messages=[{"role": "user", "content": content}],
        max_tokens=400,
    )
    return {"images": images, "captions": captions}
