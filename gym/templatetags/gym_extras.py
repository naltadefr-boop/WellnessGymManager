from django import template
from django.utils import timezone

from ..services import duree_lisible
from ..models import Parametres

register = template.Library()


@register.filter
def fcfa(v):
    if v in (None, ""):
        return "—"
    try:
        n = int(v)
    except (TypeError, ValueError):
        return v
    return f"{n:,}".replace(",", " ") + " " + Parametres.get().devise


@register.filter
def duree(minutes):
    return duree_lisible(minutes)


@register.filter
def heure(d):
    return timezone.localtime(d).strftime("%H:%M") if d else "—"


@register.filter
def dateheure(d):
    return timezone.localtime(d).strftime("%d/%m/%Y %H:%M") if d else "—"


@register.filter
def get(d, k):
    try:
        return d.get(k)
    except AttributeError:
        return None


@register.simple_tag
def etat_badge(etat):
    classes = {"ACTIF": "ok", "A_VENIR": "info", "EXPIRE": "danger", "CONSOMME": "neutre", "ANNULE": "neutre"}
    return classes.get(etat, "neutre")


@register.filter
def initiales(client):
    return (client.prenom[:1] + client.nom[:1]).upper()


@register.filter
def pourcentage(a, b):
    try:
        return max(0, min(100, round(100 * float(a) / float(b))))
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.simple_tag(takes_context=True)
def actif(context, *prefixes):
    """Renvoie « actif » si la page courante correspond à l'une des routes."""
    req = context.get("request")
    nom = getattr(getattr(req, "resolver_match", None), "url_name", "") or ""
    return "actif" if any(nom == p or (p.endswith("*") and nom.startswith(p[:-1])) for p in prefixes) else ""


@register.inclusion_tag("gym/_icone.html")
def icone(nom):
    return {"nom": nom}
