"""
Paramètres Django de WELLNESS GYM MANAGER.

Les données (base SQLite, logo, sauvegardes, clé secrète, config.ini) sont
stockées dans un DOSSIER DE DONNÉES séparé du programme :
  - variable d'environnement WGM_DATA_DIR si elle est définie ;
  - sinon, sous Windows : C:\\ProgramData\\WellnessGymManager ;
  - sinon : <dossier du projet>/donnees.
Ainsi, une mise à jour du logiciel n'efface jamais les données.
"""
import configparser
import os
import secrets
import sys
from pathlib import Path

# --- Emplacements -----------------------------------------------------------
if getattr(sys, "frozen", False):  # exécutable PyInstaller
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    BASE_DIR = Path(__file__).resolve().parent.parent


def _dossier_donnees() -> Path:
    if os.environ.get("WGM_DATA_DIR"):
        return Path(os.environ["WGM_DATA_DIR"])
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "WellnessGymManager"
    return BASE_DIR / "donnees"


DATA_DIR = _dossier_donnees()
DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR = DATA_DIR / "sauvegardes"
BACKUP_DIR.mkdir(exist_ok=True)

# --- Fichier de configuration (config.ini) ---------------------------------
CONFIG_FILE = DATA_DIR / "config.ini"
CONFIG = configparser.ConfigParser()
if not CONFIG_FILE.exists():
    CONFIG["serveur"] = {
        "; hote": "127.0.0.1 = ce poste seulement ; 0.0.0.0 = accessible aux autres appareils du réseau",
        "hote": "127.0.0.1",
        "port": "8000",
        "fuseau_horaire": "Africa/Douala",
        "ouvrir_navigateur": "oui",
    }
    CONFIG["base_de_donnees"] = {
        "; moteur": "sqlite (local, par défaut) ou postgresql (base centralisée multi-postes)",
        "moteur": "sqlite",
        "nom": "wellness_gym",
        "utilisateur": "",
        "mot_de_passe": "",
        "hote": "localhost",
        "port": "5432",
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        CONFIG.write(f)
CONFIG.read(CONFIG_FILE, encoding="utf-8")

# --- Sécurité ----------------------------------------------------------------
_secret_file = DATA_DIR / "secret.key"
if not _secret_file.exists():
    _secret_file.write_text(secrets.token_urlsafe(50), encoding="utf-8")
SECRET_KEY = os.environ.get("WGM_SECRET_KEY") or _secret_file.read_text(encoding="utf-8").strip()

DEBUG = os.environ.get("WGM_DEBUG", "0") == "1"
# Application installée sur un réseau local : on accepte tous les noms d'hôte.
ALLOWED_HOSTS = ["*"]

# --- Applications --------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "gym.apps.GymConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "gym.middleware.PremierDemarrageMiddleware",
    "gym.middleware.InactiviteMiddleware",
]

ROOT_URLCONF = "wellness_gym.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "gym.context_processors.contexte_global",
            ],
        },
    },
]

WSGI_APPLICATION = "wellness_gym.wsgi.application"

# --- Base de données -----------------------------------------------------------
_db = CONFIG["base_de_donnees"] if CONFIG.has_section("base_de_donnees") else {}
if _db.get("moteur", "sqlite").lower().startswith("postgres"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _db.get("nom", "wellness_gym"),
            "USER": _db.get("utilisateur", ""),
            "PASSWORD": _db.get("mot_de_passe", ""),
            "HOST": _db.get("hote", "localhost"),
            "PORT": _db.get("port", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": DATA_DIR / "wellness_gym.sqlite3",
            "OPTIONS": {"timeout": 20},
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "gym.Utilisateur"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 6}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LOGIN_URL = "connexion"
LOGIN_REDIRECT_URL = "tableau_de_bord"
LOGOUT_REDIRECT_URL = "connexion"

SESSION_COOKIE_AGE = 60 * 60 * 10  # plafond absolu ; l'inactivité est gérée par le middleware
SESSION_SAVE_EVERY_REQUEST = True

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --- Langue / heure ------------------------------------------------------------
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = CONFIG.get("serveur", "fuseau_horaire", fallback="Africa/Douala")
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True

# --- Fichiers statiques et médias ---------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
try:
    STATIC_ROOT.mkdir(exist_ok=True)
except OSError:
    pass
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
WHITENOISE_USE_FINDERS = True  # fonctionne même sans collectstatic
MEDIA_URL = "media/"
MEDIA_ROOT = DATA_DIR / "media"

# --- Messages ------------------------------------------------------------------
from django.contrib.messages import constants as messages  # noqa: E402

MESSAGE_TAGS = {messages.ERROR: "danger"}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "fichier": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": DATA_DIR / "journal_technique.log",
            "maxBytes": 2_000_000,
            "backupCount": 3,
            "encoding": "utf-8",
        },
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["fichier", "console"], "level": "WARNING"},
}
