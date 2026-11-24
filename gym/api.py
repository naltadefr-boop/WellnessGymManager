"""
API JSON v1 — utilisée par l'application mobile (Android / iPhone).

Authentification : en-tête « Authorization: Token <jeton> » obtenu via
POST /api/v1/connexion. Les mêmes règles métier que le logiciel de réception
s'appliquent (services.py) : un téléphone ne peut contourner aucun contrôle.
"""
import json
from datetime import timedelta
from decimal import Decimal
from functools import wraps

from django.contrib.auth import authenticate
from django.core.cache import cache
from django.db import transaction as db_tx
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import services as S
from .models import (
    Client, Coach, Formule, JetonAPI, ModePaiement, Observation, Parametres, Presence, Transaction,
)
from .views.commun import chercher_clients, clients_visibles

DUREE_JETON = timedelta(days=30)


# ---------------------------------------------------------------------------
# Infrastructure : CORS, authentification, sérialisation
# ---------------------------------------------------------------------------
def _cors(r):
    r["Access-Control-Allow-Origin"] = "*"  # authentification par jeton, sans cookie
    r["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    r["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    r["Access-Control-Max-Age"] = "86400"
    return r


def reponse(data, status=200):
    return _cors(JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False}))


def erreur(message, status=400, **extra):
    return reponse({"erreur": message, **extra}, status)


def _corps(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return {}


def api(roles=None, methode="GET", public=False):
    """roles : None = tout utilisateur connecté ; ("RECEPTION",) = réception + admin ; () = admin."""
    def deco(vue):
        @csrf_exempt
        @wraps(vue)
        def env(request, *a, **k):
            if request.method == "OPTIONS":
                return _cors(HttpResponse())
            if request.method != methode:
                return erreur("Méthode non autorisée.", 405)
            if not public:
                entete = request.META.get("HTTP_AUTHORIZATION", "")
                brut = entete[6:].strip() if entete.startswith("Token ") else ""
                jeton = JetonAPI.objects.select_related("utilisateur").filter(
                    empreinte=JetonAPI.hacher(brut), actif=True).first() if brut else None
                if not jeton or not jeton.utilisateur.is_active:
                    return erreur("Session expirée : reconnectez-vous.", 401)
                ref = jeton.derniere_utilisation or jeton.cree_le
                if timezone.now() - ref > DUREE_JETON:
                    jeton.actif = False
                    jeton.save(update_fields=["actif"])
                    return erreur("Session expirée : reconnectez-vous.", 401)
                JetonAPI.objects.filter(pk=jeton.pk).update(derniere_utilisation=timezone.now())
                request.user = u = jeton.utilisateur
                request.jeton = jeton
                if roles is not None and not (u.est_admin or u.role in roles):
                    return erreur("Action non autorisée pour votre rôle.", 403)
            try:
                return vue(request, *a, **k)
            except S.ErreurMetier as e:
                return erreur(str(e), 409)
        return env
    return deco


def _m(v):
    return int(v) if v is not None else None


def _h(d):
    return timezone.localtime(d).strftime("%H:%M") if d else None


def ser_utilisateur(u):
    return {"id": u.pk, "nom": u.nom_complet, "identifiant": u.username, "role": u.role,
            "role_libelle": u.get_role_display(), "voit_finances": u.voit_finances,
            "peut_pointer": not u.est_coach, "est_admin": u.est_admin}


def ser_etablissement():
    p = Parametres.get()
    return {"nom": p.nom_etablissement, "service": p.service, "devise": p.devise, "telephone": p.telephone,
            "logo": p.logo.url if p.logo else None}


def ser_client_court(c):
    abo = S.abonnement_courant(c)
    return {"id": c.pk, "identifiant": c.identifiant, "nom": c.nom_complet, "telephone": c.telephone,
            "etat": abo.etat if abo else "AUCUN", "etat_libelle": abo.etat_libelle if abo else "Sans abonnement",
            "present": c.presences.filter(statut=Presence.Statut.EN_COURS).exists()}


def ser_presence(p):
    return {"id": p.pk, "client_id": p.client_id, "client": p.client.nom_complet,
            "identifiant": p.client.identifiant, "formule": p.type_abonnement, "date": p.date.isoformat(),
            "arrivee": _h(p.heure_entree), "depart": _h(p.heure_sortie), "statut": p.statut,
            "statut_libelle": p.get_statut_display(),
            "duree_minutes": p.duree_minutes if p.heure_sortie else p.duree_actuelle(),
            "duree": S.duree_lisible(p.duree_minutes if p.heure_sortie else p.duree_actuelle()),
            "depassement_minutes": p.depassement_minutes if p.heure_sortie else p.depassement_en_cours(),
            "supplement": _m(p.supplement), "exception": bool(p.autorisation_id),
            "solde_semaine": p.seances_restantes_semaine, "solde_total": p.seances_restantes_total}


def ser_droits(d):
    if not d:
        return None
    c = d["courante"]
    return {"illimite": d["illimite"], "total_droits": d["total_droits"], "total_utilisees": d["total_utilisees"],
            "total_restantes": d["total_restantes"],
            "semaine": {"numero": c["numero"], "debut": c["debut"].isoformat(), "fin": c["fin"].isoformat(),
                        "autorisees": c["autorisees"], "utilisees": c["utilisees"], "restantes": c["restantes"],
                        "report": c["report_entrant"]} if c else None,
            "semaines": [{"numero": s["numero"], "debut": s["debut"].isoformat(), "fin": s["fin"].isoformat(),
                          "autorisees": s["autorisees"], "utilisees": s["utilisees"], "statut": s["statut"]}
                         for s in d["semaines"]]}


def ser_client(c, user):
    r = S.resume_client(c)
    abo, acces = r["abonnement"], r["acces"]
    data = {
        **ser_client_court(c), "email": c.email, "sexe": c.get_sexe_display(),
        "date_inscription": c.date_inscription.isoformat(), "coach": str(c.coach) if c.coach else None,
        "qr": c.identifiant, "actif": c.actif,
        "abonnement": {"id": abo.pk, "designation": abo.designation, "type": abo.type,
                       "debut": abo.date_debut.isoformat(), "fin": abo.date_fin.isoformat(),
                       "etat": abo.etat, "etat_libelle": abo.etat_libelle, "jours_restants": abo.jours_restants,
                       "duree_minutes": abo.duree_minutes, "report_seances": abo.report_seances} if abo else None,
        "droits": ser_droits(r["droits"]) if abo and abo.etat not in ("EXPIRE", "ANNULE") else None,
        "acces": {"autorise": acces.autorise, "code": acces.code, "message": acces.message,
                  "avertissements": acces.avertissements, "peut_deroger": acces.peut_deroger,
                  "proposer_renouvellement": acces.proposer_renouvellement},
        "presence": ser_presence(r["presence"]) if r["presence"] else None,
        "passages": [ser_presence(p) for p in c.presences.select_related("client")[:10]],
        "observations": [{"date": timezone.localtime(o.date).strftime("%d/%m/%Y"), "type": o.get_type_display(),
                          "texte": o.texte} for o in c.observations_suivi.all()[:5]],
    }
    if user.voit_finances:
        data["reste_a_payer"] = _m(r["reste_a_payer"])
        data["factures"] = [{"id": t.facture.pk, "numero": t.facture.numero, "transaction_id": t.pk,
                             "date": timezone.localtime(t.cree_le).strftime("%d/%m/%Y"), "designation": t.designation,
                             "montant": _m(t.montant_du), "reste": _m(t.reste), "statut": t.statut}
                            for t in c.transactions.select_related("facture")[:10]]
    return data


def _client_visible(request, pk):
    c = get_object_or_404(clients_visibles(request.user), pk=pk)
    return c


# ---------------------------------------------------------------------------
# Points d'accès
# ---------------------------------------------------------------------------
@api(methode="POST", public=True)
def connexion(request):
    d = _corps(request)
    ident = (d.get("identifiant") or "").strip()
    cle = f"echecs:{ident.lower()}"
    if cache.get(cle, 0) >= 5:
        return erreur("Trop de tentatives échouées. Réessayez dans 5 minutes.", 429)
    u = authenticate(username=ident, password=d.get("mot_de_passe") or "")
    if not u or not u.is_active:
        cache.set(cle, cache.get(cle, 0) + 1, 300)
        return erreur("Identifiant ou mot de passe incorrect.", 401)
    cache.delete(cle)
    brut = JetonAPI.emettre(u, d.get("appareil") or request.META.get("HTTP_USER_AGENT", "")[:120])
    S.journaliser(u, "CONNEXION", u.username, "Connexion depuis l'application mobile", request=request)
    return reponse({"jeton": brut, "utilisateur": ser_utilisateur(u), "etablissement": ser_etablissement()})


@api(methode="POST")
def deconnexion(request):
    request.jeton.actif = False
    request.jeton.save(update_fields=["actif"])
    S.journaliser(request.user, "DECONNEXION", request.user.username, "Déconnexion de l'application mobile",
                  request=request)
    return reponse({"ok": True})


@api()
def moi(request):
    return reponse({"utilisateur": ser_utilisateur(request.user), "etablissement": ser_etablissement()})


@api()
def tableau(request):
    u, jour = request.user, timezone.localdate()
    pres = Presence.objects.filter(date=jour).exclude(statut=Presence.Statut.ANNULEE)
    en_cours = Presence.objects.filter(statut=Presence.Statut.EN_COURS)
    if u.est_coach:
        visibles = clients_visibles(u)
        pres, en_cours = pres.filter(client__in=visibles), en_cours.filter(client__in=visibles)
        return reponse({"presents": en_cours.count(), "entrees": pres.count(),
                        "frequentation": pres.values("client").distinct().count(), "mes_clients": visibles.count(),
                        "alertes": []})
    al = S.alertes(jour)
    data = {"presents": en_cours.count(), "entrees": pres.count(),
            "sorties": pres.filter(statut=Presence.Statut.TERMINEE).count(),
            "frequentation": pres.values("client").distinct().count(),
            "alertes": [
                {"type": "renouveler", "niveau": "alerte", "titre": "Abonnements à renouveler",
                 "elements": [{"client_id": a.client_id, "texte": f"{a.client.nom_complet} — fin le {a.date_fin:%d/%m}"}
                              for a in al["a_renouveler"][:10]], "total": len(al["a_renouveler"])},
                {"type": "expires", "niveau": "danger", "titre": "Abonnements expirés",
                 "elements": [{"client_id": a.client_id, "texte": f"{a.client.nom_complet} — depuis le {a.date_fin:%d/%m}"}
                              for a in al["expires"][:10]], "total": len(al["expires"])},
                {"type": "quota", "niveau": "danger", "titre": "Quota hebdomadaire épuisé",
                 "elements": [{"client_id": a.client_id, "texte": a.client.nom_complet} for a, _ in al["quota_epuise"][:10]],
                 "total": len(al["quota_epuise"])},
                {"type": "depassement", "niveau": "danger", "titre": "Dépassements horaires",
                 "elements": [{"client_id": p.client_id, "texte": f"{p.client.nom_complet} — +"
                               f"{p.depassement_en_cours() if p.statut == 'EN_COURS' else p.depassement_minutes} min"}
                              for p in al["depassements"][:10]], "total": len(al["depassements"])},
                {"type": "paiements", "niveau": "danger", "titre": "Paiements en attente",
                 "elements": [{"client_id": t.client_id, "texte": f"{t.client.nom_complet} — reste {S.fcfa(t.reste)}"}
                              for t in al["paiements_attente"][:10]], "total": len(al["paiements_attente"])},
            ]}
    debut_sem = jour - timedelta(days=jour.weekday())
    data.update(encaisse_jour=_m(S.total_encaisse(jour, jour)),
                encaisse_semaine=_m(S.total_encaisse(debut_sem, jour)),
                encaisse_mois=_m(S.total_encaisse(jour.replace(day=1), jour)))
    return reponse(data)


@api()
def clients(request):
    q = request.GET.get("q", "")
    qs = chercher_clients(q, clients_visibles(request.user)).filter(actif=True)
    if not q:
        qs = qs.order_by("-modifie_le")
    return reponse({"resultats": [ser_client_court(c) for c in qs[:30]]})


@api()
def client(request, pk):
    return reponse(ser_client(_client_visible(request, pk), request.user))


@api()
def scan(request):
    code = (request.GET.get("code") or "").strip().upper()
    c = clients_visibles(request.user).filter(identifiant__iexact=code).first()
    if not c:
        return erreur(f"Aucun client ne correspond au code « {code} ».", 404)
    return reponse(ser_client(c, request.user))


@api(roles=("RECEPTION",), methode="POST")
def client_creer(request):
    from .forms import ClientForm
    d = _corps(request)
    form = ClientForm({"nom": d.get("nom", ""), "prenom": d.get("prenom", ""), "telephone": d.get("telephone", ""),
                       "email": d.get("email", ""), "sexe": d.get("sexe", ""),
                       "date_inscription": timezone.localdate().isoformat()})
    if not form.is_valid():
        return erreur(" ".join(f"{form.fields[k].label} : {v[0]}" for k, v in form.errors.items()), 422)
    doublon = Client.objects.filter(telephone=form.cleaned_data["telephone"]).first()
    if doublon and not d.get("confirmer_doublon"):
        return erreur(f"Un client possède déjà ce numéro : {doublon.nom_complet} ({doublon.identifiant}).", 409,
                      doublon={"id": doublon.pk, "nom": doublon.nom_complet})
    c = form.save(commit=False)
    c.cree_par = request.user
    c.save()
    S.journaliser(request.user, "CLIENT_CREE", c.identifiant, f"Nouveau client (mobile) : {c.nom_complet}",
                  request=request)
    return reponse(ser_client(c, request.user), 201)


@api(roles=("RECEPTION",), methode="POST")
def entree(request, pk):
    c = _client_visible(request, pk)
    coach = Coach.objects.filter(pk=_corps(request).get("coach")).first()
    p = S.enregistrer_entree(c, request.user, coach=coach, request=request)
    return reponse({"presence": ser_presence(p), "client": ser_client(c, request.user)})


@api(roles=("RECEPTION",), methode="POST")
def entree_exceptionnelle(request, pk):
    c = _client_visible(request, pk)
    d = _corps(request)
    with db_tx.atomic():
        resp = request.user if request.user.est_admin else S.verifier_responsable(
            d.get("resp_identifiant"), d.get("resp_mot_de_passe"))
        auto = S.accorder_autorisation(c, d.get("motif") or "AUTRE", d.get("justification"), resp, request.user,
                                       request=request)
        p = S.enregistrer_entree(c, request.user, autorisation=auto, request=request)
    return reponse({"presence": ser_presence(p), "client": ser_client(c, request.user)})


@api(roles=("RECEPTION",), methode="POST")
def sortie(request, pk):
    p = get_object_or_404(Presence, pk=pk)
    p, tx = S.enregistrer_sortie(p, request.user, request=request)
    return reponse({"presence": ser_presence(p),
                    "supplement": {"transaction_id": tx.pk, "montant": _m(tx.montant_du),
                                   "designation": tx.designation} if tx else None})


@api()
def presences(request):
    jour = timezone.localdate()
    qs = Presence.objects.filter(date=jour).select_related("client", "abonnement")
    anciennes = Presence.objects.filter(statut=Presence.Statut.EN_COURS, date__lt=jour).select_related("client")
    if request.user.est_coach:
        qs = qs.filter(client__in=clients_visibles(request.user))
        anciennes = anciennes.filter(client__in=clients_visibles(request.user))
    liste = list(anciennes) + sorted(qs, key=lambda p: (p.statut != "EN_COURS", p.heure_entree))
    return reponse({"presences": [ser_presence(p) for p in liste]})


@api(roles=("RECEPTION",))
def catalogue(request):
    return reponse({
        "formules": [{"id": f.pk, "nom": f.nom, "type": f.type, "type_libelle": f.get_type_display(),
                      "prix": _m(f.prix)} for f in Formule.objects.filter(actif=True).order_by("type", "prix")],
        "modes": [{"id": m.pk, "nom": m.nom} for m in ModePaiement.objects.filter(actif=True)],
        "coachs": [{"id": c.pk, "nom": str(c)} for c in Coach.objects.filter(statut=Coach.Statut.ACTIF)]})


@api(roles=("RECEPTION",), methode="POST")
def vente(request, pk):
    c = _client_visible(request, pk)
    d = _corps(request)
    formule = get_object_or_404(Formule, pk=d.get("formule"))
    mode = ModePaiement.objects.filter(pk=d.get("mode"), actif=True).first()
    tx = S.creer_vente(c, formule, request.user, None, Decimal(str(d.get("montant") or 0)), mode,
                       d.get("reference", ""), Coach.objects.filter(pk=d.get("coach")).first(), "", request)
    return reponse({"transaction": _ser_tx(tx), "client": ser_client(c, request.user)}, 201)


def _ser_tx(tx):
    return {"id": tx.pk, "numero": tx.numero, "facture_id": tx.facture.pk, "facture": tx.facture.numero,
            "designation": tx.designation, "montant": _m(tx.montant_du), "paye": _m(tx.montant_paye),
            "reste": _m(tx.reste), "statut": tx.statut, "type": tx.get_type_display(),
            "client": tx.client.nom_complet, "client_id": tx.client_id}


@api(roles=("RECEPTION",))
def transaction(request, pk):
    return reponse(_ser_tx(get_object_or_404(Transaction, pk=pk)))


@api(roles=("RECEPTION",), methode="POST")
def encaisser(request, pk):
    tx = get_object_or_404(Transaction, pk=pk)
    d = _corps(request)
    mode = ModePaiement.objects.filter(pk=d.get("mode"), actif=True).first()
    reg = S.encaisser(tx, Decimal(str(d.get("montant") or 0)), mode, request.user, d.get("reference", ""),
                      request=request)
    return reponse({"recu": reg.numero, "transaction": _ser_tx(tx)})


@api(roles=("RECEPTION",))
def facture_pdf(request, pk):
    from .models import Facture
    from .pdf import facture_pdf as generer
    f = get_object_or_404(Facture, pk=pk)
    r = HttpResponse(generer(f), content_type="application/pdf")
    r["Content-Disposition"] = f'inline; filename="Facture_{f.numero}.pdf"'
    return _cors(r)


@api(methode="POST")
def observation(request, pk):
    c = _client_visible(request, pk)
    d = _corps(request)
    texte = (d.get("texte") or "").strip()
    if not texte:
        return erreur("Le texte est obligatoire.", 422)
    type_ = d.get("type") if d.get("type") in Observation.Type.values else Observation.Type.OBSERVATION
    o = Observation.objects.create(
        client=c, auteur=request.user, type=type_, texte=texte,
        coach=getattr(request.user, "coach", None) if request.user.est_coach else None,
        presence=c.presences.filter(date=timezone.localdate()).first())
    S.journaliser(request.user, type_, c.identifiant, f"{o.get_type_display()} (mobile) : {texte[:100]}",
                  request=request)
    return reponse({"ok": True}, 201)
