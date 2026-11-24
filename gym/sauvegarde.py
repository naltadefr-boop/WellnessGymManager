"""
Sauvegarde et restauration.

Une sauvegarde est une archive .zip contenant :
  - la base SQLite copiée « à chaud » avec l'API officielle de sauvegarde SQLite
    (copie cohérente même si le logiciel est en cours d'utilisation) ;
  - le dossier media (logo, cachet).
Avec PostgreSQL, utilisez pg_dump (voir la documentation d'installation).
"""
import logging
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone

log = logging.getLogger(__name__)
PREFIXE_AUTO = "auto_"
PREFIXE_MANUEL = "manuelle_"
PREFIXE_SECURITE = "avant_restauration_"


def _chemin_base() -> Path:
    return Path(settings.DATABASES["default"]["NAME"])


def est_sqlite() -> bool:
    return settings.DATABASES["default"]["ENGINE"].endswith("sqlite3")


def creer_sauvegarde(auto=False, dossier: Path | None = None, prefixe: str | None = None) -> Path:
    if not est_sqlite():
        raise RuntimeError("Sauvegarde intégrée disponible uniquement avec SQLite (utilisez pg_dump pour PostgreSQL).")
    from .models import Parametres
    dossier = Path(dossier or settings.BACKUP_DIR)
    dossier.mkdir(parents=True, exist_ok=True)
    horodatage = timezone.localtime().strftime("%Y-%m-%d_%Hh%M%S")
    prefixe = prefixe or (PREFIXE_AUTO if auto else PREFIXE_MANUEL)
    cible = dossier / f"{prefixe}{horodatage}.zip"
    n = 2
    while cible.exists():  # jamais d'écrasement d'une sauvegarde existante
        cible = dossier / f"{prefixe}{horodatage}_{n}.zip"
        n += 1
    with tempfile.TemporaryDirectory() as tmp:
        copie = Path(tmp) / "wellness_gym.sqlite3"
        src = sqlite3.connect(str(_chemin_base()))
        dst = sqlite3.connect(str(copie))
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        with zipfile.ZipFile(cible, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copie, "wellness_gym.sqlite3")
            media = Path(settings.MEDIA_ROOT)
            if media.exists():
                for f in media.rglob("*"):
                    if f.is_file():
                        z.write(f, f"media/{f.relative_to(media).as_posix()}")
            z.writestr("LISEZMOI.txt", "Sauvegarde WELLNESS GYM MANAGER du "
                       + timezone.localtime().strftime("%d/%m/%Y %H:%M:%S")
                       + "\nRestauration : Paramètres > Sauvegardes > Restaurer.\n")
    p = Parametres.get()
    Parametres.objects.filter(pk=p.pk).update(derniere_sauvegarde=timezone.now())
    if p.dossier_sauvegarde_externe:
        try:
            ext = Path(p.dossier_sauvegarde_externe)
            ext.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cible, ext / cible.name)
        except Exception as e:  # clé USB absente, etc. : on n'interrompt pas
            log.warning("Copie externe impossible : %s", e)
    if auto:
        _rotation(dossier, p.sauvegarde_conservation)
    return cible


def _rotation(dossier: Path, garder: int):
    autos = sorted(dossier.glob(f"{PREFIXE_AUTO}*.zip"))
    for f in autos[:-max(1, garder)]:
        f.unlink(missing_ok=True)


def lister_sauvegardes():
    d = Path(settings.BACKUP_DIR)
    fichiers = sorted(d.glob("*.zip"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [{"nom": f.name, "taille": f.stat().st_size,
             "date": timezone.datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.get_current_timezone()),
             "auto": f.name.startswith(PREFIXE_AUTO),
             "type": "Automatique" if f.name.startswith(PREFIXE_AUTO) else
             "Avant restauration" if f.name.startswith(PREFIXE_SECURITE) else "Manuelle"} for f in fichiers]


def restaurer(fichier_zip) -> Path:
    """Restaure une archive (chemin ou fichier téléversé). Crée d'abord une
    sauvegarde de sécurité de l'état actuel."""
    if not est_sqlite():
        raise RuntimeError("Restauration intégrée disponible uniquement avec SQLite.")
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(fichier_zip) as z:
            noms = z.namelist()
            if "wellness_gym.sqlite3" not in noms:
                raise ValueError("Ce fichier n'est pas une sauvegarde WELLNESS GYM MANAGER valide.")
            for n in noms:
                if n.startswith("/") or ".." in Path(n).parts:
                    raise ValueError("Archive invalide.")
            z.extractall(tmp)
        base = Path(tmp) / "wellness_gym.sqlite3"
        test = sqlite3.connect(str(base))
        try:
            ok = test.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            test.execute("SELECT count(*) FROM gym_client").fetchone()
        finally:
            test.close()
        if not ok:
            raise ValueError("La base contenue dans la sauvegarde est endommagée.")
        # L'archive est vérifiée et extraite : on sauvegarde l'état actuel avant de le remplacer.
        securite = creer_sauvegarde(prefixe=PREFIXE_SECURITE)
        connection.close()
        src = sqlite3.connect(str(base))
        dst = sqlite3.connect(str(_chemin_base()))
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        media_src = Path(tmp) / "media"
        if media_src.exists():
            shutil.copytree(media_src, settings.MEDIA_ROOT, dirs_exist_ok=True)
    return securite


def demarrer_sauvegarde_automatique():
    """Thread lancé par lancer.py : vérifie toutes les 10 minutes s'il faut sauvegarder."""
    def boucle():
        time.sleep(30)
        while True:
            try:
                from .models import Parametres
                p = Parametres.get()
                if p.sauvegarde_auto and est_sqlite():
                    derniere = p.derniere_sauvegarde
                    if derniere is None or timezone.now() - derniere >= timedelta(hours=p.sauvegarde_intervalle_heures):
                        chemin = creer_sauvegarde(auto=True)
                        log.warning("Sauvegarde automatique créée : %s", chemin)
            except Exception:
                log.exception("Échec de la sauvegarde automatique")
            finally:
                connection.close()
            time.sleep(600)
    t = threading.Thread(target=boucle, name="sauvegarde-auto", daemon=True)
    t.start()
    return t
