"""Sert l'application mobile (PWA) sous /m/ et le manifeste du poste de réception."""
import json
from pathlib import Path

from django.http import FileResponse, Http404, HttpResponse
from django.templatetags.static import static

DOSSIER = Path(__file__).resolve().parent.parent / "static" / "gym" / "mobile"
TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".png": "image/png", ".webmanifest": "application/manifest+json",
         ".txt": "text/plain; charset=utf-8"}


def fichier(request, nom="index.html"):
    chemin = (DOSSIER / (nom or "index.html")).resolve()
    if chemin.parent != DOSSIER.resolve() or not chemin.is_file() or chemin.suffix not in TYPES:
        raise Http404
    r = FileResponse(open(chemin, "rb"), content_type=TYPES[chemin.suffix])
    if chemin.name == "sw.js":
        r["Service-Worker-Allowed"] = "/m/"
    r["Cache-Control"] = "no-cache"
    return r


def manifeste_bureau(request):
    """Permet d'« installer » le logiciel de réception comme une application (Chrome / Edge)."""
    data = {"name": "Wellness Gym Manager", "short_name": "Wellness Gym", "start_url": "/", "scope": "/",
            "display": "standalone", "background_color": "#0F3D36", "theme_color": "#0F3D36", "lang": "fr",
            "icons": [{"src": static("gym/img/icone-192.png"), "sizes": "192x192", "type": "image/png"},
                      {"src": static("gym/img/icone-512.png"), "sizes": "512x512", "type": "image/png"}]}
    return HttpResponse(json.dumps(data), content_type="application/manifest+json")
