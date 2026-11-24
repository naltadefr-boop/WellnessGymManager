"""
WELLNESS GYM MANAGER — lanceur.

Double-cliquez sur « Lancer Wellness Gym.bat » (ou sur l'exécutable installé) :
  1. met à jour la base de données si nécessaire ;
  2. démarre le serveur local (Waitress, fiable sous Windows) ;
  3. démarre la sauvegarde automatique ;
  4. ouvre le logiciel dans le navigateur.

Options :  --sans-navigateur   --port 8000   --hote 0.0.0.0
"""
import argparse
import os
import socket
import sys
import threading
import time
import webbrowser

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wellness_gym.settings")


def port_occupe(hote, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1" if hote in ("0.0.0.0", "") else hote, port)) == 0


def adresses_reseau():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(i for i in ips if not i.startswith("127."))


def main():
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command

    cfg = settings.CONFIG
    p = argparse.ArgumentParser()
    p.add_argument("--hote", default=cfg.get("serveur", "hote", fallback="127.0.0.1"))
    p.add_argument("--port", type=int, default=cfg.getint("serveur", "port", fallback=8000))
    p.add_argument("--sans-navigateur", action="store_true")
    a = p.parse_args()
    url = f"http://127.0.0.1:{a.port}/"

    print("=" * 64)
    print("  WELLNESS HOTEL — WELLNESS GYM MANAGER")
    print("=" * 64)
    if port_occupe(a.hote, a.port):
        print(f"Le logiciel est déjà en cours d'exécution : ouverture de {url}")
        webbrowser.open(url)
        return

    print("Vérification de la base de données…")
    call_command("migrate", interactive=False, verbosity=0)
    from gym.sauvegarde import demarrer_sauvegarde_automatique
    demarrer_sauvegarde_automatique()

    print(f"Données : {settings.DATA_DIR}")
    print(f"Adresse sur ce poste : {url}")
    if a.hote in ("0.0.0.0", ""):
        for ip in adresses_reseau():
            print(f"Adresse pour les autres appareils (téléphones, tablettes) : http://{ip}:{a.port}/  ·  mobile : http://{ip}:{a.port}/m/")
    else:
        print("Accès réservé à ce poste (hote = 127.0.0.1 dans config.ini).")
    print("\nNE FERMEZ PAS CETTE FENÊTRE pendant l'utilisation du logiciel.\n")

    if not a.sans_navigateur and cfg.get("serveur", "ouvrir_navigateur", fallback="oui").lower() in ("oui", "1", "true"):
        threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(url)), daemon=True).start()

    from waitress import serve
    from wellness_gym.wsgi import application
    serve(application, host=a.hote, port=a.port, threads=8, ident="WellnessGym")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # message lisible pour la réception
        print("\nERREUR AU DÉMARRAGE :", e)
        import traceback
        traceback.print_exc()
        if sys.stdin and sys.stdin.isatty():
            input("\nAppuyez sur Entrée pour fermer…")
        sys.exit(1)
