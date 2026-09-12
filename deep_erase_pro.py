#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gi
gi.require_version('Gimp', '3.0')
gi.require_version('GimpUi', '3.0')
from gi.repository import Gimp, GimpUi, GLib, Gio, Gegl, GObject

try:
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
except Exception:
    GdkPixbuf = None

import os
import sys
import json
import glob
import time
import shutil
import signal
import platform
import tempfile
import subprocess

PROCEDURE_NAME = "deep-erase-pro"
PLUGIN_ID = "deep_erase_pro"
PLUGIN_VERSION = "6.12"
SHARED_DIR_NAME = "ai_suite_shared"

# Emplacement prevu pour des empreintes de reference publiees en amont, au
# format {"<sha256 minuscule>": "description de la provenance"}. Tant que ce
# dictionnaire est vide, aucun controle de provenance n'est effectue et seul le
# mecanisme TOFU s'applique (avertissement en cas de changement du fichier,
# jamais de blocage). Le remplir active un avertissement supplementaire lorsque
# le modele depose ne correspond a aucune reference connue. Ce controle ne
# constitue pas une frontiere de securite : la valeur de reference reside dans
# ce fichier, modifiable par quiconque peut deja remplacer le modele.
KNOWN_GOOD_HASHES = {}

MODEL_FILENAME = "lama.pt"
MODEL_MIN_BYTES = 8 * 1024 * 1024
MODEL_MAX_BYTES = 2 * 1024 * 1024 * 1024

REQUIRED_PACKAGES = {
    "numpy>=1.24,<3": "numpy",
    "opencv-python-headless>=4.8,<6": "cv2",
    "torch>=2.0,<3": "torch",
}

PROBE_TIMEOUT = 5
IMPORT_TIMEOUT = 120
INSTALL_TIMEOUT = 1800
INFERENCE_TIMEOUT = 900
FALLBACK_TIMEOUT = 600

SELECTION_COVERAGE_WARN = 0.97
DEFAULT_CONTEXT_MARGIN = 0.20
DEFAULT_FEATHER = 2.0

# --- Correctif 14 : ressources partagees nommees par pile technique ---------
# 'venv' et 'ai_suite_env_ok.json' etaient generiques alors qu'ils decrivent une
# pile precise (torch, OpenCV, numpy). Un second greffon de la suite, avec
# d'autres REQUIRED_PACKAGES, voyait une signature differente, reinstallait dans
# le venv commun et ecrasait les paquets du premier, qui invalidait a son tour au
# lancement suivant : un aller-retour de reinstallation sans fin, plusieurs
# gigaoctets a chaque passage, sans aucun message permettant de le comprendre.
# Le suffixe de pile rend la collision impossible. Le fichier de confiance des
# modeles reste commun : il est indexe par nom de fichier et se partage sans
# risque entre greffons.
VENV_DIR_NAME = "venv-torch"
CACHE_FILENAME = "ai_suite_python_torch.txt"
ENVMARK_FILENAME = "ai_suite_env_torch.json"
TRUST_FILENAME = "ai_suite_model_trust.json"

LEGACY_VENV_DIR_NAME = "venv"
LEGACY_ENVMARK_FILENAME = "ai_suite_env_ok.json"
LEGACY_CACHE_FILENAME = "ai_suite_python_cache.txt"

# Bornes de l'interpreteur d'amorcage. Le plancher est celui des roues torch et
# opencv ; le plafond est la derniere version reellement testee. Le plafond
# n'interdit rien : il n'exprime qu'une preference quand plusieurs versions
# cohabitent. Le refuser reviendrait a declarer qu'aucun Python n'existe alors
# qu'il y en a un. A relever apres chaque campagne de test.
# --- Correctif 16 : canaux de decouverte ------------------------------------
# Un venv de cette suite a ete construit en production sur le Python embarque
# de Blender, decouvert par une voie qu'aucune relecture du code n'a pu
# reconstituer. Un tel interpreteur disparait a la mise a jour de
# l'application hote et emporte l'environnement avec lui. Seuls les canaux
# ci-dessous reposent sur une declaration du systeme ; un interpreteur livre
# avec une application n'y figure jamais. Le canal retenu est consigne dans le
# marqueur : une voie qu'on ne sait pas reconstituer est une voie qu'on ne sait
# pas fermer.
TRUSTED_CHANNELS = ("registry", "py_launcher", "standard_install")
CHANNEL_PATH = "path"
CHANNEL_CONVENTIONAL = "conventional_venv"

PYTHON_MIN_VERSION = (3, 10)
PYTHON_MAX_TESTED = (3, 13)

# Espace libre exige avant d'engager une installation. Une roue torch CUDA pese
# environ 2,5 Go a elle seule, et pip a besoin de place pour decompresser en
# plus de la place occupee au final. Refuser tot vaut mieux qu'un 'No space left
# on device' au milieu d'un telechargement de plusieurs gigaoctets.
# Valeurs a confirmer par mesure, cf. section des reperes de duree.
FREE_SPACE_MIN_CPU = 3 * 1024 * 1024 * 1024
FREE_SPACE_MIN_GPU = 10 * 1024 * 1024 * 1024


def get_shared_base():
    base = os.path.join(Gimp.directory(), SHARED_DIR_NAME)
    os.makedirs(base, exist_ok=True)
    return base


def _migrate_legacy_shared_resources(base, venv_path):
    """Renomme les ressources de la v6.7 et anterieures plutot que de laisser
    l'utilisateur retelecharger plusieurs gigaoctets. Silencieux et idempotent :
    si la cible existe deja, l'ancienne est laissee en place sans etre lue."""
    paires = (
        (os.path.join(base, LEGACY_VENV_DIR_NAME), venv_path),
        (os.path.join(base, LEGACY_ENVMARK_FILENAME),
         os.path.join(base, ENVMARK_FILENAME)),
        (os.path.join(base, LEGACY_CACHE_FILENAME),
         os.path.join(base, CACHE_FILENAME)),
    )
    for ancien, nouveau in paires:
        if os.path.exists(ancien) and not os.path.exists(nouveau):
            try:
                os.rename(ancien, nouveau)
            except OSError:
                pass


KEPT_INCIDENTS = 10


def get_logs_directory():
    path = os.path.join(get_shared_base(), 'logs')
    os.makedirs(path, exist_ok=True)
    return path


def archive_logs(work_dir):
    """Correctif 18 : le dossier de travail est bien detruit, mais jamais avant
    d'avoir mis a l'abri ce qui permet de comprendre l'echec. Sans cela, un
    rapport de bogue exploitable suppose que l'utilisateur sache lancer GIMP
    depuis un terminal - ce que personne ne fera."""
    if not work_dir or not os.path.isdir(work_dir):
        return None
    try:
        names = [n for n in os.listdir(work_dir)
                 if n.endswith('.log') or n.endswith('.json')]
    except OSError:
        return None
    if not names:
        return None

    target = os.path.join(get_logs_directory(),
                          time.strftime('%Y-%m-%d_%H-%M-%S'))
    try:
        os.makedirs(target, exist_ok=True)
        for name in names:
            shutil.copy2(os.path.join(work_dir, name),
                         os.path.join(target, name))
    except OSError:
        return None

    try:
        base = get_logs_directory()
        incidents = sorted(n for n in os.listdir(base)
                           if os.path.isdir(os.path.join(base, n)))
        for name in incidents[:-KEPT_INCIDENTS]:
            shutil.rmtree(os.path.join(base, name), ignore_errors=True)
    except OSError:
        pass
    return target


def get_shared_directories():
    base = get_shared_base()
    venv_path = os.path.join(base, VENV_DIR_NAME)
    models_path = os.path.join(base, "models")
    _migrate_legacy_shared_resources(base, venv_path)
    os.makedirs(venv_path, exist_ok=True)
    os.makedirs(models_path, exist_ok=True)
    return venv_path, models_path


def get_model_path(model_filename):
    """Cherche le modele dans le dossier partage, puis a cote du greffon.

    Le second emplacement est un repli de depannage, pas un usage courant : il
    se trouve dans 'plug-ins/', l'arborescence que GIMP parcourt a chaque
    demarrage. Un modele de plusieurs centaines de megaoctets ou d'un gigaoctet
    y est simplement 'stat' et ignore, donc le cout reste negligeable, mais il
    echappe alors a la mutualisation entre greffons de la suite et sera
    retelecharge par chacun d'eux. Deposez les modeles dans 'models/'.
    """
    _, models_path = get_shared_directories()
    shared_model = os.path.join(models_path, model_filename)
    if os.path.isfile(shared_model):
        return shared_model
    plugin_dir = os.path.dirname(os.path.realpath(__file__))
    local_model = os.path.join(plugin_dir, model_filename)
    if os.path.isfile(local_model):
        return local_model
    return shared_model


def venv_python_path(venv_dir):
    if os.name == 'nt':
        return os.path.join(venv_dir, 'Scripts', 'python.exe')
    return os.path.join(venv_dir, 'bin', 'python3')


# --- Correctif 12 : isolation d'environnement complete -----------------------
# GIMP (AppImage, Flatpak, bundle macOS) impose ses propres bibliotheques via
# LD_LIBRARY_PATH / DYLD_*. Un Python systeme lance en heritant de ces variables
# charge la libstdc++ ou la libpng de GIMP et echoue a importer torch/cv2 avec
# un message incomprehensible. On purge donc tout le bloc, pas seulement
# PYTHONPATH / PYTHONHOME.
_ENV_VARS_TO_DROP = (
    'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONEXECUTABLE',
    'LD_LIBRARY_PATH', 'LD_PRELOAD', 'LD_AUDIT',
    'DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH', 'DYLD_INSERT_LIBRARIES',
    'DYLD_FALLBACK_LIBRARY_PATH', 'DYLD_FALLBACK_FRAMEWORK_PATH',
    'GI_TYPELIB_PATH', 'GDK_PIXBUF_MODULE_FILE', 'GDK_PIXBUF_MODULEDIR',
    'GSETTINGS_SCHEMA_DIR', 'GEGL_PATH', 'BABL_PATH',
)


def read_log_text(path):
    """Correctif 19 : le journal melange la sortie de Python et celle des
    bibliotheques natives, qui n'utilisent pas le meme encodage. Une lecture en
    UTF-8 pur rendait une partie du texte illisible, donc inexploitable pour
    diagnostiquer."""
    try:
        with open(path, 'rb') as handle:
            raw = handle.read()
    except OSError:
        return ''
    if not raw:
        return ''
    if b'\x00' in raw[:200]:
        for codec in ('utf-16', 'utf-16-le', 'utf-16-be'):
            try:
                return raw.decode(codec)
            except Exception:
                pass
    for codec in ('utf-8', 'cp1252', 'latin-1'):
        try:
            return raw.decode(codec)
        except Exception:
            pass
    return raw.decode('utf-8', errors='replace')


def env_clean():
    clean_env = os.environ.copy()
    for var in _ENV_VARS_TO_DROP:
        clean_env.pop(var, None)
    clean_env['PYTHONNOUSERSITE'] = '1'
    clean_env['PYTHONIOENCODING'] = 'utf-8'
    # Correctif 19 : PYTHONIOENCODING seul ne suffit pas. Une partie des
    # journaux revenait en UTF-16 et devenait illisible relue en UTF-8 - or
    # c'est precisement leur role d'etre lisibles.
    clean_env['PYTHONUTF8'] = '1'
    if 'PATH' in clean_env:
        paths = clean_env['PATH'].split(os.pathsep)
        clean_env['PATH'] = os.pathsep.join(
            [p for p in paths if p and 'gimp' not in p.lower()]
        )
    return clean_env


def _popen_kwargs():
    kwargs = {}
    if os.name == 'nt':
        kwargs['creationflags'] = 0x08000000
    else:
        # Correctif : le worker tourne dans sa propre session, ce qui permet de
        # tuer tout le groupe (torch peut avoir essaime des sous-processus).
        kwargs['start_new_session'] = True
    return kwargs


def is_flatpak():
    return os.path.exists('/.flatpak-info')


def kill_process_tree(process):
    try:
        if os.name != 'nt':
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except Exception:
                process.kill()
        else:
            process.kill()
        process.wait(timeout=10)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def test_python_executable(path, timeout=PROBE_TIMEOUT):
    if not path or not os.path.isfile(path):
        return False
    gimp_dir = os.path.dirname(os.path.abspath(sys.executable)).lower()
    if gimp_dir and gimp_dir in os.path.abspath(path).lower():
        return False
    try:
        res = subprocess.run(
            [path, '-c', 'import sys; sys.exit(0)'],
            env=env_clean(), capture_output=True, timeout=timeout, **_popen_kwargs()
        )
        return res.returncode == 0
    except Exception:
        return False


def is_embedded_interpreter(path):
    """Heuristique : un dossier ancetre contient un executable qui n'est pas un
    outil Python, signe d'un interpreteur livre avec une application hote. Elle
    ne sert qu'a declasser un candidat, jamais a le rejeter seule : le canal de
    decouverte reste le critere principal."""
    if os.name != 'nt':
        return False
    allowed = ('python.exe', 'pythonw.exe', 'pip.exe', 'py.exe',
               'venvlauncher.exe', 'venvwlauncher.exe')
    folder = os.path.dirname(os.path.abspath(path))
    for _ in range(4):
        parent = os.path.dirname(folder)
        if not parent or parent == folder:
            break
        folder = parent
        try:
            entries = os.listdir(folder)
        except OSError:
            break
        for name in entries:
            lower = name.lower()
            if not lower.endswith('.exe'):
                continue
            if lower in allowed or lower.startswith('python'):
                continue
            return True
    return False


def python_version_of(path, timeout=PROBE_TIMEOUT):
    """Version majeure/mineure d'un interpreteur, None s'il ne repond pas."""
    try:
        res = subprocess.run(
            [path, '-c',
             'import sys; print(sys.version_info[0], sys.version_info[1])'],
            env=env_clean(), capture_output=True, text=True,
            encoding='utf-8', errors='replace',
            timeout=timeout, **_popen_kwargs())
        if res.returncode != 0:
            return None
        parts = (res.stdout or "").split()
        return int(parts[0]), int(parts[1])
    except Exception:
        return None


def version_label(version):
    return ".".join(str(n) for n in version)


def required_signature():
    return sorted(REQUIRED_PACKAGES.keys())


def test_python_environment(path, timeout=IMPORT_TIMEOUT):
    """Verifie que l'interpreteur demarre ET que numpy/cv2/torch y sont
    reellement importables. Retourne (ok, diagnostic)."""
    if not test_python_executable(path):
        return False, "Interpreteur Python introuvable ou non executable."
    modules = list(REQUIRED_PACKAGES.values())
    import_stmt = "; ".join("import %s" % m for m in modules)
    try:
        res = subprocess.run(
            [path, '-c', import_stmt],
            env=env_clean(), capture_output=True, text=True,
            encoding='utf-8', errors='replace',
            timeout=timeout, **_popen_kwargs()
        )
        if res.returncode != 0:
            detail = (res.stderr or res.stdout or "").strip()
            return False, detail[-800:] if detail else "Echec d'import inconnu."
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Depassement de delai pendant la verification des imports."
    except Exception as e:
        return False, str(e)


def read_env_marker():
    """Correctif : evite un 'import torch' complet (2 a 5 s) a chaque lancement.
    Le marqueur est invalide par le worker via [CACHE_INVALIDATION_REQUIRED]."""
    marker = os.path.join(get_shared_base(), ENVMARK_FILENAME)
    try:
        with open(marker, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get('packages') != required_signature():
        return None
    py = data.get('python')
    if not py or not os.path.isfile(py):
        return None
    if not test_python_executable(py):
        return None
    return py


def read_env_marker_data():
    """Contenu brut du marqueur d'environnement, dictionnaire vide si absent."""
    marker = os.path.join(get_shared_base(), ENVMARK_FILENAME)
    try:
        with open(marker, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_env_marker(python_path, extra=None):
    marker = os.path.join(get_shared_base(), ENVMARK_FILENAME)
    data = read_env_marker_data()
    data.update({'python': python_path,
                 'packages': required_signature(),
                 'plugin_version': PLUGIN_VERSION})
    if extra:
        data.update(extra)
    try:
        with open(marker, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception:
        pass


def invalidate_env_cache():
    base = get_shared_base()
    for name in (ENVMARK_FILENAME, CACHE_FILENAME):
        try:
            p = os.path.join(base, name)
            if os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass


# --- Correctif 8 : registre Windows (regle 3) -------------------------------
def _windows_registry_pythons():
    found = []
    if os.name != 'nt':
        return found
    try:
        import winreg
    except ImportError:
        return found
    hives = [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]
    subkeys = [r"Software\Python\PythonCore",
               r"Software\WOW6432Node\Python\PythonCore"]
    flags = [0]
    for extra in ('KEY_WOW64_64KEY', 'KEY_WOW64_32KEY'):
        val = getattr(winreg, extra, None)
        if val is not None:
            flags.append(val)
    for hive in hives:
        for sub in subkeys:
            for flag in flags:
                try:
                    root = winreg.OpenKey(hive, sub, 0, winreg.KEY_READ | flag)
                except OSError:
                    continue
                try:
                    index = 0
                    while True:
                        try:
                            version = winreg.EnumKey(root, index)
                        except OSError:
                            break
                        index += 1
                        try:
                            ikey = winreg.OpenKey(
                                root, version + r"\InstallPath", 0,
                                winreg.KEY_READ | flag)
                        except OSError:
                            continue
                        try:
                            exe = None
                            try:
                                exe, _ = winreg.QueryValueEx(ikey, "ExecutablePath")
                            except OSError:
                                try:
                                    base, _ = winreg.QueryValueEx(ikey, "")
                                    if base:
                                        exe = os.path.join(base, "python.exe")
                                except OSError:
                                    exe = None
                            if exe:
                                found.append(os.path.abspath(exe.strip('"')))
                        finally:
                            try:
                                winreg.CloseKey(ikey)
                            except Exception:
                                pass
                finally:
                    try:
                        winreg.CloseKey(root)
                    except Exception:
                        pass
    return found


def find_system_python():
    candidates = {}
    env = env_clean()
    kwargs = _popen_kwargs()

    def retenir(chemin, canal):
        if not chemin:
            return
        cle = os.path.normcase(os.path.abspath(chemin))
        if cle not in candidates:
            candidates[cle] = (os.path.abspath(chemin), canal)

    for cmd in ('python3', 'python', 'py'):
        p = shutil.which(cmd, path=env.get('PATH'))
        if p:
            retenir(p, CHANNEL_PATH)

    cmds = ('py', 'python', 'python3') if os.name == 'nt' else ('python3', 'python')
    for cmd in cmds:
        try:
            res = subprocess.run(
                [cmd, '-c', 'import sys; print(sys.executable)'],
                env=env, capture_output=True, text=True,
                encoding='utf-8', errors='replace',
                timeout=PROBE_TIMEOUT, **kwargs)
            if res.returncode == 0 and res.stdout.strip():
                retenir(res.stdout.strip(), CHANNEL_PATH)
        except Exception:
            pass

    if os.name == 'nt':
        try:
            res = subprocess.run(['py', '-0p'], env=env, capture_output=True,
                                 text=True, encoding='utf-8', errors='replace',
                                 timeout=PROBE_TIMEOUT, **kwargs)
            import re
            # L'ancien motif exigeait un espace apres le tiret alors que la
            # sortie reelle est ' -V:3.14 *   C:\...\python.exe'. Il ne
            # renvoyait donc jamais rien : la strategie du lanceur py etait
            # morte depuis le debut, sans que rien ne le signale.
            for match in re.findall(r"[A-Za-z]:\\.*?python(?:w)?\.exe",
                                    res.stdout or "", re.IGNORECASE):
                retenir(match, "py_launcher")
        except Exception:
            pass

        for p in _windows_registry_pythons():
            retenir(p, "registry")

        local_appdata = os.environ.get('LOCALAPPDATA', '')
        if local_appdata:
            for p in glob.glob(os.path.join(local_appdata, 'Programs', 'Python',
                                            'Python*', 'python.exe')):
                retenir(p, "standard_install")
            winapps = os.path.join(local_appdata, 'Microsoft', 'WindowsApps',
                                   'python.exe')
            if os.path.isfile(winapps):
                retenir(winapps, CHANNEL_PATH)

        roots = [os.environ.get('PROGRAMFILES', ''),
                 os.environ.get('PROGRAMFILES(X86)', ''),
                 os.environ.get('SYSTEMDRIVE', 'C:') + os.sep]
        for root in roots:
            if root:
                for p in glob.glob(os.path.join(root, 'Python*', 'python.exe')):
                    retenir(p, "standard_install")
    else:
        home = os.path.expanduser("~")
        plugin_dir = os.path.dirname(os.path.realpath(__file__))
        for direct in ('/usr/bin/python3', '/usr/local/bin/python3',
                       '/opt/homebrew/bin/python3',
                       '/Library/Frameworks/Python.framework/Versions/Current/bin/python3'):
            if os.path.isfile(direct):
                retenir(direct, "standard_install")
        search_dirs = [
            os.path.join(home, '.venvs'),
            os.path.join(home, '.virtualenvs'),
            os.path.join(home, '.venv'),
            os.path.join(home, 'venv'),
            plugin_dir,
        ]
        for base_dir in search_dirs:
            if not os.path.isdir(base_dir):
                continue
            direct = os.path.join(base_dir, 'bin', 'python3')
            if os.path.isfile(direct):
                retenir(direct, CHANNEL_CONVENTIONAL)
            try:
                for entry in os.listdir(base_dir):
                    p = os.path.join(base_dir, entry, 'bin', 'python3')
                    if os.path.isfile(p):
                        retenir(p, CHANNEL_CONVENTIONAL)
            except Exception:
                pass

    # --- Correctif 15 : le premier candidat qui demarre n'est pas le bon ------
    # La version precedente retenait le premier interpreteur repondant, sans
    # regarder sa version. Sur un poste ou coexistent un 3.9 et un 3.12, le 3.9
    # pouvait gagner et faire echouer l'installation de torch bien plus loin,
    # avec un message de pip incomprehensible. Les versions sous le plancher
    # sont ecartees ici, ou l'explication est encore possible.
    scored = []
    for cleaned, channel in candidates.values():
        if not test_python_executable(cleaned):
            continue
        version = python_version_of(cleaned)
        if version is None or version < PYTHON_MIN_VERSION:
            continue
        stub = 1 if 'WindowsApps' in cleaned else 0
        # Correctif 16 : le canal prime sur tout le reste hormis le stub. Un
        # interpreteur non declare par le systeme, ou manifestement embarque
        # dans une application, ne sert qu'a defaut de tout autre.
        if channel in TRUSTED_CHANNELS:
            trust = 0
        elif is_embedded_interpreter(cleaned):
            trust = 2
        else:
            trust = 1
        untested = 0 if version <= PYTHON_MAX_TESTED else 1
        scored.append((stub, trust, untested, version, cleaned, channel))

    if not scored:
        return None, None

    # Le stub WindowsApps ouvre le Microsoft Store : toujours en dernier recours.
    # A egalite, la version testee la plus recente, puis la plus recente tout
    # court si aucune version testee n'est disponible.
    scored.sort(key=lambda e: (e[0], e[1], e[2], -e[3][0], -e[3][1], e[4]))
    return scored[0][4], scored[0][5]


_GPU_DETECTION_CACHE = None


def _probe_cuda_driver():
    """Interroge directement la bibliotheque du pilote NVIDIA.

    C'est la source la plus fiable : elle ne depend ni du PATH, ni de la
    presence d'un utilitaire annexe, ni de PyTorch (dont la roue peut
    justement etre CPU-only). cuInit puis cuDeviceGetCount repondent a la
    seule question qui compte : y a-t-il un GPU CUDA utilisable ?
    """
    try:
        import ctypes
    except Exception:
        return False, "ctypes indisponible"

    libs = ('nvcuda.dll',) if os.name == 'nt' else ('libcuda.so.1', 'libcuda.so')
    notes = []
    for lib in libs:
        try:
            handle = ctypes.WinDLL(lib) if os.name == 'nt' else ctypes.CDLL(lib)
        except Exception:
            notes.append("%s introuvable" % lib)
            continue
        try:
            if handle.cuInit(0) != 0:
                notes.append("%s: cuInit a echoue" % lib)
                continue
            count = ctypes.c_int(0)
            if handle.cuDeviceGetCount(ctypes.byref(count)) != 0:
                notes.append("%s: cuDeviceGetCount a echoue" % lib)
                continue
            if count.value > 0:
                return True, "pilote CUDA actif, %d GPU" % count.value
            notes.append("%s: aucun GPU visible" % lib)
        except Exception as e:
            notes.append("%s: %s" % (lib, e))
    return False, "; ".join(notes) if notes else "aucun pilote CUDA"


def detect_gpu():
    """Retourne (gpu_utilisable, detail_diagnostic).

    Piege corrige en v6.7 : la version precedente se contentait de chercher
    nvidia-smi dans le PATH. Sur une machine ou cet utilitaire n'est pas
    expose au processus GIMP, la detection echouait silencieusement, le
    greffon calculait sur le processeur et - pire - n'affichait aucun message,
    puisque toutes les branches GPU etaient court-circuitees.
    """
    global _GPU_DETECTION_CACHE
    if _GPU_DETECTION_CACHE is not None:
        return _GPU_DETECTION_CACHE

    result = (False, "non determine")
    try:
        if sys.platform == 'darwin':
            if platform.machine() in ('arm64', 'aarch64'):
                result = (True, "Apple Silicon (MPS)")
            else:
                result = (False, "macOS Intel, pas d'acceleration supportee")
        else:
            ok, detail = _probe_cuda_driver()
            if ok:
                result = (True, detail)
            else:
                # Replis : le pilote peut etre present sans que la bibliotheque
                # soit chargeable depuis ce processus.
                found = shutil.which('nvidia-smi')
                if not found and os.name == 'nt':
                    root = os.environ.get('SYSTEMROOT', r'C:\Windows')
                    for sub in ('System32', 'SysWOW64'):
                        candidate = os.path.join(root, sub, 'nvidia-smi.exe')
                        if os.path.isfile(candidate):
                            found = candidate
                            break
                if not found and os.name != 'nt':
                    if os.path.exists('/dev/nvidia0') or os.path.exists('/dev/nvidiactl'):
                        found = '/dev/nvidia0'
                if found:
                    result = (True, "GPU detecte via %s (%s)"
                              % (os.path.basename(found), detail))
                else:
                    result = (False, detail)
    except Exception as e:
        result = (False, "echec de la detection : %s" % e)

    _GPU_DETECTION_CACHE = result
    return result


def _gpu_is_likely():
    """Sonde bon marche (aucun import torch) utilisee pour trois decisions :
    ne pas poser de RLIMIT_AS qui casserait l'initialisation CUDA, choisir la
    roue torch adaptee, et signaler un GPU present mais inutilise."""
    return detect_gpu()[0]


def _total_ram_bytes():
    try:
        if hasattr(os, 'sysconf'):
            if 'SC_PHYS_PAGES' in os.sysconf_names and 'SC_PAGE_SIZE' in os.sysconf_names:
                return os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
    except Exception:
        pass
    try:
        if os.name == 'nt':
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return int(stat.ullTotalPhys)
    except Exception:
        pass
    return 8 * 1024 * 1024 * 1024


def compute_memory_limit():
    total = _total_ram_bytes()
    limit = int(total * 0.75)
    return max(2 * 1024 * 1024 * 1024, limit)


TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
# Essayes dans l'ordre : le premier index qui fournit une roue installable
# gagne. Une liste evite de figer une version de CUDA qui vieillira mal, comme
# l'a fait le cu124 des versions precedentes. Les roues CUDA sont retro
# compatibles avec les pilotes plus recents, donc un pilote a jour accepte
# n'importe laquelle de ces entrees.
TORCH_CUDA_INDEXES = (
    "https://download.pytorch.org/whl/cu129",
    "https://download.pytorch.org/whl/cu128",
    "https://download.pytorch.org/whl/cu126",
)


def torch_index_candidates(module_name, gpu_likely):
    """Retourne la liste des index pip a essayer pour un paquet donne.

    Piege corrige en v6.2 : sous Windows, la roue publiee sur PyPI est
    CPU-only. Une machine equipee d'une carte NVIDIA calculait donc sur le
    processeur sans le moindre message, le greffon affichant simplement
    'IA, CPU'. Les variantes CUDA ne sont distribuees que sur l'index PyTorch.

    Sous Linux c'est l'inverse : la roue PyPI embarque les runtimes CUDA, soit
    environ 2,5 Go telecharges pour rien sur une machine sans GPU.

    Sous macOS, la roue PyPI contient deja le support MPS.

    None dans la liste signifie 'index PyPI par defaut'.
    """
    if module_name != 'torch':
        return [None]
    if sys.platform == 'darwin':
        return [None]
    if gpu_likely:
        if os.name == 'nt':
            return list(TORCH_CUDA_INDEXES)
        return [None] + list(TORCH_CUDA_INDEXES)
    return [TORCH_CPU_INDEX]


CUDA_PROBE_CODE = (
    'import torch;'
    ' ok = torch.cuda.is_available();'
    ' x = torch.zeros(1, 1, 8, 8, device="cuda") if ok else None;'
    ' c = torch.nn.Conv2d(1, 1, 3).cuda() if ok else None;'
    ' y = c(x) if ok else None;'
    ' torch.cuda.synchronize() if ok else None;'
    ' print(1 if ok else 0)'
)


def probe_cuda_available(python_executable):
    """Correctif 20 : verifier que la roue expose CUDA ne prouve rien.
    'torch.cuda.is_available()' repond oui alors qu'une convolution peut encore
    echouer - cuDNN absent, pilote trop ancien, memoire indisponible - et
    l'echec ne surviendrait qu'en pleine inference, chez l'utilisateur. La
    sonde execute donc une vraie convolution sur la carte."""
    try:
        res = subprocess.run(
            [python_executable, '-c', CUDA_PROBE_CODE],
            env=env_clean(), capture_output=True, text=True,
            encoding='utf-8', errors='replace',
            timeout=IMPORT_TIMEOUT, **_popen_kwargs())
        return res.returncode == 0 and res.stdout.strip().endswith('1')
    except Exception:
        return False


def free_space_bytes(path):
    """Espace libre du volume portant ce chemin. Remonte au premier parent
    existant : le dossier cible peut ne pas encore avoir ete cree."""
    probe = os.path.abspath(path)
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        return shutil.disk_usage(probe).free
    except Exception:
        return None


def check_free_space(path, gpu_likely):
    """Refuse une installation vouee a echouer faute de place. L'alternative
    est un 'No space left on device' au milieu de plusieurs gigaoctets deja
    telecharges, qui laisse en plus un venv a moitie peuple."""
    required = FREE_SPACE_MIN_GPU if gpu_likely else FREE_SPACE_MIN_CPU
    free = free_space_bytes(path)
    if free is None:
        return
    if free >= required:
        return
    go = 1024.0 * 1024.0 * 1024.0
    variante = "avec support CUDA" if gpu_likely else "pour processeur"
    raise RuntimeError(
        "Espace disque insuffisant pour installer l'environnement IA %s.\n\n"
        "Requis : %.1f Go. Disponible : %.1f Go sur le volume de :\n%s\n\n"
        "Liberez de la place, puis relancez le greffon. Le dossier partage de "
        "la suite peut aussi etre vide sans risque : il sera reconstruit."
        % (variante, required / go, free / go, path))


def setup_venv(system_python, log_dir):
    venv_dir, _ = get_shared_directories()
    venv_python = venv_python_path(venv_dir)
    env = env_clean()
    kwargs = _popen_kwargs()
    gpu_likely = _gpu_is_likely()

    if not os.path.isfile(venv_python):
        check_free_space(venv_dir, gpu_likely)
        Gimp.progress_set_text("Creation de l'environnement virtuel partage...")
        try:
            process = subprocess.Popen(
                [system_python, '-m', 'venv', venv_dir], env=env, **kwargs)
            start = time.time()
            while process.poll() is None:
                Gimp.progress_pulse()
                time.sleep(0.2)
                if time.time() - start > 300:
                    kill_process_tree(process)
                    raise RuntimeError("Depassement de delai a la creation du venv.")
            if process.returncode != 0 or not os.path.isfile(venv_python):
                raise RuntimeError(
                    "Echec de creation du venv.\n"
                    "Sur Debian/Ubuntu : sudo apt install python3-venv")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError("Erreur de creation venv : %s" % e)

    def _run_capture(cmd, timeout_s, progress_text):
        log_path = os.path.join(
            log_dir, "pip_%d.log" % int(time.time() * 1000))
        process = None
        try:
            with open(log_path, 'w', encoding='utf-8', errors='replace') as log_f:
                Gimp.progress_set_text(progress_text)
                process = subprocess.Popen(cmd, env=env, stdout=log_f,
                                           stderr=subprocess.STDOUT, **kwargs)
                start = time.time()
                while process.poll() is None:
                    Gimp.progress_pulse()
                    time.sleep(0.2)
                    if time.time() - start > timeout_s:
                        kill_process_tree(process)
                        raise RuntimeError(
                            "Depassement de delai (%d min)." % (timeout_s // 60))
            return process.returncode, read_log_text(log_path)
        finally:
            try:
                os.remove(log_path)
            except OSError:
                pass

    try:
        _run_capture([venv_python, '-m', 'pip', 'install', '--upgrade', 'pip'],
                     180, "Mise a jour de pip...")
    except Exception:
        pass

    missing = []
    for package_spec, module_name in REQUIRED_PACKAGES.items():
        try:
            subprocess.run([venv_python, '-c', 'import %s' % module_name],
                           env=env, check=True, capture_output=True,
                           timeout=IMPORT_TIMEOUT, **kwargs)
            continue
        except subprocess.TimeoutExpired:
            pass
        except subprocess.CalledProcessError:
            pass
        except Exception:
            pass
        missing.append((package_spec, module_name))

    # Le controle ne porte que sur une installation reellement engagee : un
    # environnement deja complet doit rester utilisable sur un disque plein.
    if missing:
        check_free_space(venv_dir, gpu_likely)

    for package_spec, module_name in missing:
        install_rc, install_out = None, ""
        for index in torch_index_candidates(module_name, gpu_likely):
            cmd = [venv_python, '-m', 'pip', 'install', '--no-input',
                   '--only-binary=:all:', package_spec]
            if index:
                cmd += ['--index-url', index]
            label = "Installation de %s" % module_name
            if index:
                label += " (%s)" % index.rsplit('/', 1)[-1]
            install_rc, install_out = _run_capture(
                cmd, INSTALL_TIMEOUT, label + "...")
            if install_rc == 0:
                break

        if install_rc != 0:
            hint = ("\n\nAucune version precompilee n'est peut-etre disponible "
                    "pour votre plateforme ou votre version de Python. "
                    "Essayez avec un Python %s a %s (64 bits)."
                    % (version_label(PYTHON_MIN_VERSION),
                       version_label(PYTHON_MAX_TESTED)))
            raise RuntimeError("Echec de l'installation de %s :\n%s%s"
                               % (module_name, (install_out or "")[-2000:], hint))

    if gpu_likely and not probe_cuda_available(venv_python):
        Gimp.message(
            "Un GPU NVIDIA a ete detecte mais la version de PyTorch installee "
            "n'expose pas CUDA : le calcul se fera sur le processeur.\n\n"
            "Supprimez le dossier '%s' sous :\n%s\n\npuis relancez le greffon "
            "pour tenter une autre variante CUDA."
            % (VENV_DIR_NAME, get_shared_base()))

    return venv_python


# --- Correctif 4 : RLIMIT_AS ne doit pas etre pose quand un GPU est probable.
# RLIMIT_AS limite l'espace d'adressage VIRTUEL ; l'initialisation d'un contexte
# CUDA en reserve couramment 20 a 60 Go sans les toucher. Une limite a 4 Go
# faisait donc systematiquement echouer l'inference sur machine equipee.
def _posix_memory_limit_preexec(limit_bytes):
    def _limiter():
        try:
            import resource
            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            target = limit_bytes
            if hard != resource.RLIM_INFINITY:
                target = min(target, hard)
            resource.setrlimit(resource.RLIMIT_AS, (target, hard))
        except Exception:
            pass
    return _limiter


# --- Correctif 5 : Job Object Windows reellement fonctionnel -----------------
# L'implementation precedente etait inoperante : structure BasicLimitInformation
# dimensionnee a 48 octets (64 en x64), LimitFlags jamais positionne, HANDLE
# tronque faute d'argtypes/restype.
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOBOBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001


def _assign_windows_job_memory_limit(process, limit_bytes):
    """Retourne le handle du Job (a fermer par l'appelant) ou None."""
    if os.name != 'nt':
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [("ReadOperationCount", ctypes.c_ulonglong),
                        ("WriteOperationCount", ctypes.c_ulonglong),
                        ("OtherOperationCount", ctypes.c_ulonglong),
                        ("ReadTransferCount", ctypes.c_ulonglong),
                        ("WriteTransferCount", ctypes.c_ulonglong),
                        ("OtherTransferCount", ctypes.c_ulonglong)]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                        ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_JOB_MEMORY)
        info.ProcessMemoryLimit = limit_bytes
        info.JobMemoryLimit = limit_bytes
        if not kernel32.SetInformationJobObject(
                job, JOBOBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                ctypes.byref(info), ctypes.sizeof(info)):
            kernel32.CloseHandle(job)
            return None

        h_process = kernel32.OpenProcess(
            PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, process.pid)
        if not h_process:
            kernel32.CloseHandle(job)
            return None
        try:
            if not kernel32.AssignProcessToJobObject(job, h_process):
                kernel32.CloseHandle(job)
                return None
        finally:
            kernel32.CloseHandle(h_process)
        return job
    except Exception:
        return None


def _close_windows_handle(handle):
    if not handle or os.name != 'nt':
        return
    try:
        import ctypes
        ctypes.WinDLL('kernel32').CloseHandle(handle)
    except Exception:
        pass


# --- Confiance du modele : TOFU + sanity-check de taille (regle 9) ----------
def read_model_trust():
    path = os.path.join(get_shared_base(), TRUST_FILENAME)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_model_trust(model_path, sha256):
    path = os.path.join(get_shared_base(), TRUST_FILENAME)
    data = read_model_trust()
    try:
        st = os.stat(model_path)
        data[os.path.basename(model_path)] = {
            'sha256': sha256,
            'size': st.st_size,
            'mtime': int(st.st_mtime),
            'path': model_path,
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception:
        pass


def check_model_size(model_path):
    try:
        size = os.path.getsize(model_path)
    except OSError as e:
        return False, "Modele illisible : %s" % e
    if size == 0:
        return False, ("Le fichier '%s' est vide (0 octet). Le telechargement a "
                       "probablement echoue." % os.path.basename(model_path))
    if size < MODEL_MIN_BYTES:
        return False, ("Le fichier '%s' ne fait que %.1f Mo : il est tronque "
                       "(telechargement interrompu). Retelechargez-le."
                       % (os.path.basename(model_path), size / 1048576.0))
    if size > MODEL_MAX_BYTES:
        return False, ("Le fichier '%s' fait %.1f Mo, bien au-dela de la taille "
                       "attendue pour ce modele. Verifiez qu'il s'agit du bon "
                       "fichier." % (os.path.basename(model_path), size / 1048576.0))
    return True, ""


def model_hash_plan(model_path):
    """Evite de rehasher plusieurs centaines de Mo a chaque execution : si la
    taille et la date de modification n'ont pas bouge, on fait confiance au
    hash memorise."""
    entry = read_model_trust().get(os.path.basename(model_path))
    if not entry:
        return False, None
    try:
        st = os.stat(model_path)
    except OSError:
        return False, None
    same = (entry.get('size') == st.st_size
            and entry.get('mtime') == int(st.st_mtime)
            and entry.get('path') == model_path)
    return bool(same), entry.get('sha256')


WORKER_CODE = r'''# -*- coding: utf-8 -*-
# Worker genere par Deep Erase Pro. Tous les parametres arrivent via un fichier
# JSON (argv[1]) : aucune interpolation de chaine cote greffon, donc aucun
# risque de casse sur des chemins exotiques.
import sys
import os
import json
import hashlib


def emit(tag, msg=""):
    try:
        line = ("[%s] %s" % (tag, msg)).rstrip()
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def main():
    try:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            params = json.load(f)
    except Exception as e:
        emit("PARAM_ERROR", str(e))
        return 1

    try:
        import numpy as np
        import cv2
    except ImportError as e:
        emit("CACHE_INVALIDATION_REQUIRED", "numpy/cv2 indisponible : %s" % e)
        return 1

    img_in = params["image"]
    mask_in = params["mask"]
    img_out = params["out"]
    model_path = params["model"]
    no_ai = bool(params.get("no_ai", False))
    margin_ratio = float(params.get("margin", 0.20))
    feather = float(params.get("feather", 2.0))
    force_cpu = bool(params.get("force_cpu", False))
    skip_hash = bool(params.get("skip_hash", False))
    known_hash = params.get("known_hash") or ""

    raw = cv2.imread(img_in, cv2.IMREAD_UNCHANGED)
    mask = cv2.imread(mask_in, cv2.IMREAD_UNCHANGED)
    if raw is None:
        emit("IO_ERROR", "Image source illisible : %s" % img_in)
        return 1
    if mask is None:
        emit("IO_ERROR", "Masque illisible : %s" % mask_in)
        return 1

    if mask.ndim == 3:
        mask = cv2.cvtColor(mask[:, :, :3], cv2.COLOR_BGR2GRAY)
    if mask.dtype == np.uint16:
        mask = (mask / 257.0).astype(np.uint8)
    elif mask.dtype != np.uint8:
        mask = np.clip(mask, 0, 255).astype(np.uint8)

    depth16 = (raw.dtype == np.uint16)
    if raw.ndim == 2:
        raw = raw[:, :, np.newaxis]
    channels = raw.shape[2]
    has_alpha = channels in (2, 4)
    was_gray = channels in (1, 2)

    if has_alpha:
        alpha_channel = raw[:, :, channels - 1].copy()
        color = raw[:, :, :channels - 1]
    else:
        alpha_channel = None
        color = raw

    if color.shape[2] == 1:
        img_native = cv2.cvtColor(color[:, :, 0], cv2.COLOR_GRAY2BGR)
    else:
        img_native = color

    # Correctif : un PNG 16 bits exporte par GIMP donnait des valeurs jusqu'a
    # 257 apres division par 255 -> image saturee sans aucune exception. On
    # travaille en 8 bits pour l'inference, puis on recompose a la profondeur
    # d'origine pour ne pas degrader le reste de l'image.
    if depth16:
        img8 = (img_native / 257.0).astype(np.uint8)
    else:
        img8 = img_native.astype(np.uint8)

    if img8.shape[:2] != mask.shape[:2]:
        mask = cv2.resize(mask, (img8.shape[1], img8.shape[0]),
                          interpolation=cv2.INTER_NEAREST)

    _, binary_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    if cv2.countNonZero(binary_mask) == 0:
        emit("EMPTY_MASK", "Le masque genere est vide.")
        return 1

    x, y, w_box, h_box = cv2.boundingRect(binary_mask)
    if w_box == 0 or h_box == 0:
        emit("EMPTY_MASK", "Boite englobante nulle.")
        return 1

    margin_x = max(32, int(w_box * margin_ratio))
    margin_y = max(32, int(h_box * margin_ratio))
    img_h, img_w = img8.shape[:2]
    x1 = max(0, x - margin_x)
    y1 = max(0, y - margin_y)
    x2 = min(img_w, x + w_box + margin_x)
    y2 = min(img_h, y + h_box + margin_y)

    img_crop = img8[y1:y2, x1:x2]
    mask_crop = binary_mask[y1:y2, x1:x2]
    crop_h, crop_w = img_crop.shape[:2]

    result_crop = None

    if not no_ai:
        try:
            if not skip_hash:
                digest = sha256_of(model_path)
                emit("MODEL_HASH", digest)
                if known_hash and digest != known_hash:
                    # Confiance a la premiere utilisation : on avertit,
                    # on ne bloque jamais un traitement legitime.
                    emit("MODEL_HASH_CHANGED",
                         "Le fichier modele a change depuis la derniere execution.")

            import torch

            # Remonte l'etat reel de l'installation PyTorch : c'est ce qui
            # permet au greffon de distinguer une roue CPU-only d'un GPU
            # simplement invisible, au lieu d'afficher 'sur processeur' sans
            # la moindre explication.
            try:
                cuda_build = getattr(torch.version, "cuda", None)
                cuda_ok = bool(torch.cuda.is_available())
                count = torch.cuda.device_count() if cuda_ok else 0
                emit("TORCH", "version=%s build_cuda=%s disponible=%s gpu=%d"
                     % (torch.__version__, cuda_build, cuda_ok, count))
            except Exception as probe_error:
                emit("TORCH", "diagnostic indisponible : %s" % probe_error)

            if force_cpu:
                device = torch.device("cpu")
            elif torch.cuda.is_available():
                device = torch.device("cuda")
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = torch.device("mps")
            else:
                device = torch.device("cpu")
            emit("DEVICE", str(device))

            model = torch.jit.load(model_path, map_location=device)
            model.eval()

            pad = 32
            pad_h = (pad - crop_h % pad) % pad
            pad_w = (pad - crop_w % pad) % pad
            work_img = cv2.copyMakeBorder(img_crop, 0, pad_h, 0, pad_w,
                                          cv2.BORDER_REFLECT)
            work_mask = cv2.copyMakeBorder(mask_crop, 0, pad_h, 0, pad_w,
                                           cv2.BORDER_REFLECT)
            work_rgb = cv2.cvtColor(work_img, cv2.COLOR_BGR2RGB)

            img_tensor = torch.from_numpy(work_rgb).float().permute(2, 0, 1)
            img_tensor = (img_tensor.unsqueeze(0) / 255.0).to(device)
            mask_tensor = torch.from_numpy(work_mask).float()
            mask_tensor = (mask_tensor.unsqueeze(0).unsqueeze(0) / 255.0).to(device)

            with torch.no_grad():
                output = model(img_tensor, mask_tensor)

            # Beaucoup de modules TorchScript LaMa renvoient un tuple.
            while isinstance(output, (tuple, list)):
                if not len(output):
                    raise RuntimeError("Sortie du modele vide.")
                output = output[0]
            if isinstance(output, dict):
                output = list(output.values())[0]

            out_np = output.detach().squeeze(0).permute(1, 2, 0).float().cpu().numpy()

            # Correctif : l'ancien test 'max <= 1.0 -> x255' eclaircissait a tort
            # les sorties 0-255 tres sombres. On compare la moyenne de sortie a
            # celle de l'entree, ce qui identifie l'echelle sans ambiguite.
            in_mean = float(work_rgb.mean()) / 255.0
            out_mean = float(np.nanmean(out_np))
            out_max = float(np.nanmax(out_np)) if out_np.size else 0.0
            if not (out_max > 1.5 or (in_mean > 0.01 and out_mean > 8.0 * in_mean)):
                out_np = out_np * 255.0

            out_np = np.clip(np.nan_to_num(out_np), 0, 255).astype(np.uint8)
            ai_crop = cv2.cvtColor(out_np, cv2.COLOR_RGB2BGR)
            if pad_h > 0 or pad_w > 0:
                ai_crop = ai_crop[:crop_h, :crop_w]
            if ai_crop.shape[:2] != (crop_h, crop_w):
                ai_crop = cv2.resize(ai_crop, (crop_w, crop_h),
                                     interpolation=cv2.INTER_LANCZOS4)
            result_crop = ai_crop
            emit("PT_SUCCESS")
        except Exception as e:
            result_crop = None
            emit("PT_ERROR", "%s: %s" % (type(e).__name__, str(e)[:500]))

    if result_crop is None:
        try:
            # Correctif : le repli travaille sur le meme recadrage que l'IA.
            # cv2.inpaint sur une image 24 Mpx avec un rayon de 15 prenait
            # plusieurs minutes.
            radius = int(max(3, min(15, 0.05 * min(w_box, h_box))))
            result_crop = cv2.inpaint(img_crop, mask_crop, radius, cv2.INPAINT_NS)
            emit("FALLBACK_SUCCESS")
        except Exception as e:
            emit("FALLBACK_ERROR", str(e)[:500])
            return 1

    # Correctif : ne reecrire que la zone masquee, avec un fondu, au lieu de
    # remplacer toute la boite englobante marge comprise (lisere visible).
    soft = mask_crop.astype(np.float32) / 255.0
    if feather > 0:
        soft = cv2.GaussianBlur(soft, (0, 0), feather)
    soft = np.clip(soft, 0.0, 1.0)[:, :, np.newaxis]

    scale = 257.0 if depth16 else 1.0
    region = img_native[y1:y2, x1:x2].astype(np.float32)
    patch = result_crop.astype(np.float32) * scale
    blended = region * (1.0 - soft) + patch * soft

    result = img_native.copy()
    max_val = 65535 if depth16 else 255
    result[y1:y2, x1:x2] = np.clip(blended, 0, max_val).astype(img_native.dtype)

    if was_gray:
        result = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
        if has_alpha:
            result = cv2.merge([result, alpha_channel])
    elif has_alpha:
        result = cv2.cvtColor(result, cv2.COLOR_BGR2BGRA)
        result[:, :, 3] = alpha_channel

    try:
        written = cv2.imwrite(img_out, result)
    except Exception as e:
        emit("WRITE_ERROR", str(e)[:500])
        return 1
    if not written or not os.path.isfile(img_out) or os.path.getsize(img_out) == 0:
        emit("WRITE_ERROR", "Ecriture du resultat impossible : %s" % img_out)
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MemoryError:
        emit("MEMORY_ERROR", "Memoire insuffisante pour traiter cette zone.")
        sys.exit(1)
    except Exception as exc:
        emit("WORKER_ERROR", "%s: %s" % (type(exc).__name__, str(exc)[:500]))
        sys.exit(1)
'''


def _first_marker_line(output, tag):
    prefix = "[%s]" % tag
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()
    return None


def run_worker_once(python_executable, work_dir, params, timeout_s):
    """Lance le worker une fois. Correctif majeur : le succes ne depend plus de
    la reussite de l'IA mais de la production effective d'un resultat, ce qui
    rend le repli OpenCV reellement exploitable."""
    worker_path = os.path.join(work_dir, "worker.py")
    params_path = os.path.join(work_dir, "params.json")
    log_path = os.path.join(work_dir, "worker.log")

    with open(worker_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(WORKER_CODE)
    with open(params_path, "w", encoding="utf-8") as f:
        json.dump(params, f)

    popen_kwargs = dict(_popen_kwargs())
    mem_limit = compute_memory_limit()
    if os.name != 'nt' and not _gpu_is_likely():
        popen_kwargs['preexec_fn'] = _posix_memory_limit_preexec(mem_limit)

    job_handle = None
    timed_out = False
    process = None
    try:
        # Correctif : le descripteur d'ecriture est ferme par le with. L'ancien
        # 'stdout=open(...)' fuyait un fd et verrouillait le log sous Windows.
        with open(log_path, "w", encoding="utf-8", errors="replace") as log_f:
            process = subprocess.Popen(
                [python_executable, worker_path, params_path],
                env=env_clean(), stdout=log_f, stderr=subprocess.STDOUT,
                **popen_kwargs)

            if os.name == 'nt' and not _gpu_is_likely():
                job_handle = _assign_windows_job_memory_limit(process, mem_limit)

            start = time.time()
            while process.poll() is None:
                Gimp.progress_pulse()
                time.sleep(0.2)
                if time.time() - start > timeout_s:
                    kill_process_tree(process)
                    timed_out = True
                    break
    finally:
        _close_windows_handle(job_handle)

    output = read_log_text(log_path)

    returncode = process.returncode if process is not None else -1
    produced = (os.path.isfile(params["out"])
                and os.path.getsize(params["out"]) > 0)

    return {
        'output': output,
        'returncode': returncode,
        'timed_out': timed_out,
        'success': (not timed_out) and returncode == 0 and produced,
        'is_ai': "[PT_SUCCESS]" in output,
        'cache_invalid': "[CACHE_INVALIDATION_REQUIRED]" in output,
        'hash_changed': "[MODEL_HASH_CHANGED]" in output,
        'model_hash': _first_marker_line(output, "MODEL_HASH"),
        'device': _first_marker_line(output, "DEVICE"),
        'torch_info': _first_marker_line(output, "TORCH"),
        'detail': (_first_marker_line(output, "PT_ERROR")
                   or _first_marker_line(output, "MEMORY_ERROR")
                   or _first_marker_line(output, "WORKER_ERROR")
                   or _first_marker_line(output, "IO_ERROR")
                   or _first_marker_line(output, "EMPTY_MASK")
                   or _first_marker_line(output, "WRITE_ERROR")
                   or _first_marker_line(output, "FALLBACK_ERROR")
                   or _first_marker_line(output, "PARAM_ERROR")
                   or ""),
    }


def execute_worker(python_executable, work_dir, params):
    result = run_worker_once(python_executable, work_dir, params,
                             INFERENCE_TIMEOUT)
    if result['timed_out'] and not params.get('no_ai'):
        # Regle 12 : ne jamais relancer un calcul deja connu pour depasser le
        # delai. On repasse directement en mode non-IA pour livrer un resultat.
        Gimp.progress_set_text("Delai IA depasse, repli OpenCV en cours...")
        retry_params = dict(params)
        retry_params['no_ai'] = True
        retry = run_worker_once(python_executable, work_dir, retry_params,
                                FALLBACK_TIMEOUT)
        retry['detail'] = ("Depassement du delai IA (%d min) : le traitement a "
                           "bascule sur OpenCV." % (INFERENCE_TIMEOUT // 60))
        retry['timed_out_ai'] = True
        return retry
    return result


# --- Export / import robustes (regle 7) -------------------------------------
def safe_export(image, drawables, gio_file, path):
    """Essaie chaque signature connue de Gimp.file_save, mais verifie en plus
    que le fichier a reellement ete ecrit : une variante peut ne pas lever de
    TypeError tout en ne produisant rien."""
    last_error = None
    attempts = (
        lambda: Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, gio_file),
        lambda: Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, drawables, gio_file),
        lambda: Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, gio_file, drawables),
        lambda: Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, drawables[0], gio_file),
    )
    for attempt in attempts:
        try:
            if os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
            attempt()
        except TypeError as e:
            last_error = e
            continue
        except Exception as e:
            last_error = e
            continue
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            return
    raise RuntimeError("Echec d'export vers %s (%s)" % (path, last_error))


def load_result_layer(image, path, layer_name):
    """Correctif : si Gimp.file_load_layers est absent, l'ancienne version
    retournait SUCCESS sans rien inserer. On dispose desormais d'un repli."""
    gio_file = Gio.File.new_for_path(path)
    layers = None
    if hasattr(Gimp, 'file_load_layers'):
        try:
            layers = Gimp.file_load_layers(Gimp.RunMode.NONINTERACTIVE, image, gio_file)
        except Exception:
            layers = None

    if layers:
        for layer in layers:
            try:
                image.insert_layer(layer, None, 0)
            except AttributeError:
                image.add_layer(layer, 0)
            try:
                layer.set_name(layer_name)
            except Exception:
                pass
        return True

    tmp_image = None
    try:
        tmp_image = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, gio_file)
    except Exception:
        tmp_image = None
    if tmp_image is None:
        return False
    try:
        new_layer = Gimp.Layer.new_from_visible(tmp_image, image, layer_name)
        try:
            image.insert_layer(new_layer, None, 0)
        except AttributeError:
            image.add_layer(new_layer, 0)
        return True
    except Exception:
        return False
    finally:
        try:
            tmp_image.delete()
        except Exception:
            pass


# --- Compatibilite API de selection (regle 7) -------------------------------
def selection_is_empty(image):
    try:
        return Gimp.Selection.is_empty(image)
    except (AttributeError, TypeError):
        pass
    try:
        return image.get_selection().is_empty()
    except Exception:
        return False


def selection_bounds(image):
    result = None
    try:
        result = Gimp.Selection.bounds(image)
    except (AttributeError, TypeError):
        try:
            result = image.get_selection().bounds()
        except Exception:
            try:
                result = image.get_selection().bounds(image)
            except Exception:
                result = None
    if result is None:
        return None
    values = tuple(result)
    if len(values) == 6:
        return values[2], values[3], values[4], values[5]
    if len(values) == 5:
        return values[1], values[2], values[3], values[4]
    if len(values) == 4:
        return values[0], values[1], values[2], values[3]
    # Correctif : ne jamais laisser x1/y1 indefinis (NameError masquee).
    return None


def selection_save(image):
    try:
        return Gimp.Selection.save(image)
    except (AttributeError, TypeError):
        return image.selection_save()


def selection_none(image):
    try:
        Gimp.Selection.none(image)
    except (AttributeError, TypeError):
        image.select_none()


def selection_load(image, channel):
    try:
        Gimp.Selection.load(channel)
    except (AttributeError, TypeError):
        image.select_item(Gimp.ChannelOps.REPLACE, channel)


# Le nom du calque est la seule trace persistante de ce qui a produit le
# resultat, le log du worker etant supprime avec le dossier temporaire. Il doit
# donc etre lisible sans connaitre le jargon : 'IA, CPU' designait en realite le
# processeur et ne nommait pas le modele, ce qui laissait croire a un echec.
DEVICE_LABELS = {
    'cuda': "GPU NVIDIA",
    'mps': "GPU Apple",
    'xpu': "GPU Intel",
    'hip': "GPU AMD",
    'rocm': "GPU AMD",
    'cpu': "processeur",
}


def normalize_device_label(raw_device):
    """Traduit la representation torch du device ('cuda', 'cuda:0', 'mps',
    'cpu') en une etiquette comprehensible, sans jamais faire echouer le
    nommage sur une valeur inattendue."""
    if not raw_device:
        return None
    label = str(raw_device).strip().lower().split(':')[0]
    if not label:
        return None
    return DEVICE_LABELS.get(label, label[:12].upper())


def build_layer_name(result, model_path=None):
    """Construit un nom de calque qui indique explicitement le modele utilise
    et le materiel sur lequel le calcul a eu lieu."""
    if not result.get('is_ai'):
        return "Deep Erase Pro - sans IA (repli OpenCV)"

    model = os.path.basename(model_path) if model_path else None
    engine = model if model else "modele IA"
    device = normalize_device_label(result.get('device'))
    if device:
        return "Deep Erase Pro - %s sur %s" % (engine, device)
    return "Deep Erase Pro - %s" % engine


def run_with_progress(cmd, timeout_s, progress_text, log_dir):
    """Execute une commande longue en animant la barre de progression de GIMP,
    sortie capturee vers un fichier (jamais un PIPE, qui se bloquerait)."""
    log_path = os.path.join(log_dir, "cmd_%d.log" % int(time.time() * 1000))
    process = None
    try:
        with open(log_path, 'w', encoding='utf-8', errors='replace') as log_f:
            Gimp.progress_set_text(progress_text)
            process = subprocess.Popen(cmd, env=env_clean(), stdout=log_f,
                                       stderr=subprocess.STDOUT, **_popen_kwargs())
            start = time.time()
            while process.poll() is None:
                Gimp.progress_pulse()
                time.sleep(0.2)
                if time.time() - start > timeout_s:
                    kill_process_tree(process)
                    return -1, "Depassement de delai (%d min)." % (timeout_s // 60)
        return process.returncode, read_log_text(log_path)
    except Exception as e:
        return -1, str(e)
    finally:
        try:
            os.remove(log_path)
        except OSError:
            pass


def ensure_cuda_torch(venv_python, log_dir):
    """Remplace automatiquement une roue PyTorch CPU-only par une variante CUDA
    quand un GPU NVIDIA est present.

    Piege corrige en v6.6 : la cascade d'index CUDA ne s'appliquait qu'a la
    creation du venv. Un environnement deja installe avec la roue CPU-only de
    PyPI (le cas par defaut sous Windows) etait reutilise indefiniment, et le
    greffon se contentait d'afficher 'sur processeur' puis de suggerer une
    commande pip a taper - ce que le cahier des charges interdit explicitement.

    Le remplacement n'est tente qu'une seule fois : en cas d'echec, un drapeau
    evite de retelecharger plusieurs gigaoctets a chaque execution.
    Retourne (cuda_actif, message_ou_None).
    """
    if not _gpu_is_likely() or sys.platform == 'darwin':
        return False, None

    marker = read_env_marker_data()
    if marker.get('cuda_ok') and marker.get('python') == venv_python:
        return True, None

    if probe_cuda_available(venv_python):
        write_env_marker(venv_python, {'cuda_ok': True,
                                       'cuda_repair_attempted': False})
        return True, None

    if marker.get('cuda_repair_attempted'):
        return False, None

    spec = next((s for s, m in REQUIRED_PACKAGES.items() if m == 'torch'),
                'torch>=2.0,<3')
    for index in TORCH_CUDA_INDEXES:
        variant = index.rsplit('/', 1)[-1]
        rc, _ = run_with_progress(
            [venv_python, '-m', 'pip', 'install', '--no-input',
             '--force-reinstall', '--only-binary=:all:',
             '--index-url', index, spec],
            INSTALL_TIMEOUT,
            "GPU detecte : installation de PyTorch %s (plusieurs minutes)..."
            % variant,
            log_dir)
        if rc == 0 and probe_cuda_available(venv_python):
            write_env_marker(venv_python, {'cuda_ok': True,
                                           'cuda_repair_attempted': False})
            return True, ("PyTorch a ete remplace par la variante %s : ce "
                          "traitement et les suivants utiliseront le GPU."
                          % variant)

    write_env_marker(venv_python, {'cuda_ok': False,
                                   'cuda_repair_attempted': True})
    return False, ("Un GPU a ete detecte mais aucune variante CUDA de PyTorch "
                   "n'a pu etre installee. Le calcul continuera sur le "
                   "processeur. Supprimez le dossier '%s' sous %s pour "
                   "relancer une tentative complete."
                   % (VENV_DIR_NAME, get_shared_base()))


def gpu_unused_warning(result, force_cpu):
    """Informe l'utilisateur des que le calcul est parti sur le processeur.

    Piege corrige en v6.7 : le message n'etait emis que si la detection GPU
    repondait positivement. Quand cette detection echouait - le cas meme qui
    provoque le calcul sur processeur - l'utilisateur ne recevait donc
    strictement rien et n'avait aucun moyen de comprendre. Le diagnostic est
    desormais joint dans tous les cas, y compris le resultat de la detection
    materielle elle-meme.

    Quand aucun GPU n'est trouve, le message n'apparait qu'une seule fois par
    environnement pour ne pas devenir une nuisance sur une machine qui n'a
    de toute facon pas d'acceleration disponible.
    """
    if force_cpu or not result.get('is_ai'):
        return None
    device = (result.get('device') or "").strip().lower().split(':')[0]
    if device and device != 'cpu':
        return None

    gpu_ok, gpu_detail = detect_gpu()
    info = result.get('torch_info') or "diagnostic indisponible"

    if gpu_ok:
        return (
            "Le calcul s'est fait sur le processeur alors qu'un GPU a ete "
            "detecte, et le remplacement automatique de PyTorch par une "
            "variante CUDA n'a pas abouti.\n\n"
            "Materiel : %s\n"
            "PyTorch : %s\n\n"
            "Supprimez le dossier '%s' sous %s puis relancez le greffon pour "
            "une reinstallation complete."
            % (gpu_detail, info, VENV_DIR_NAME, get_shared_base()))

    marker = read_env_marker_data()
    if marker.get('cpu_notice_shown'):
        return None
    write_env_marker(marker.get('python') or "", {'cpu_notice_shown': True})
    return (
        "Le calcul s'est fait sur le processeur : aucun GPU utilisable n'a ete "
        "detecte depuis GIMP.\n\n"
        "Materiel : %s\n"
        "PyTorch : %s\n\n"
        "Ce message ne sera plus affiche. Si vous possedez une carte NVIDIA, "
        "ces deux lignes indiquent ou se situe le blocage."
        % (gpu_detail, info))


def mask_coverage(mask_path, image, bbox):
    """Mesure la proportion couverte par la selection, directement sur le
    masque PNG qui vient d'etre exporte.

    Les deux tentatives precedentes passaient par Gimp.Drawable.histogram() en
    lisant un champ du tuple par son indice. La disposition de ce tuple varie
    selon la revision de GIMP 3.0, ce qui a produit des valeurs absurdes (6852 %
    puis 99 % pour une selection d'a peine quelques pour cent). On mesure donc
    le fichier reellement transmis au modele : le resultat est exact par
    construction et ne depend plus d'aucune signature d'API.

    Le masque etant noir (non selectionne) ou blanc (selectionne), sa moyenne
    est le taux de couverture. La somme des octets d'une ligne est calculee en C
    par CPython, le cout reste negligeable meme sur une grande image.
    """
    ratio = None
    if GdkPixbuf is not None and mask_path and os.path.isfile(mask_path):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(mask_path)
            data = pixbuf.get_pixels()
            channels = pixbuf.get_n_channels()
            rowstride = pixbuf.get_rowstride()
            width = pixbuf.get_width()
            height = pixbuf.get_height()
            total = width * height
            if total > 0 and channels >= 1 and data:
                accumulator = 0
                for row in range(height):
                    start = row * rowstride
                    line = data[start:start + width * channels]
                    # On ne garde que le premier canal : sur un masque RGBA,
                    # le canal alpha vaut 255 partout et fausserait la moyenne.
                    accumulator += sum(line[0::channels])
                ratio = accumulator / float(total * 255)
        except Exception:
            ratio = None

    if ratio is None and bbox:
        img_area = image.get_width() * image.get_height()
        if img_area > 0:
            x1, y1, x2, y2 = bbox
            ratio = float(max(0, x2 - x1) * max(0, y2 - y1)) / float(img_area)

    if ratio is None:
        return 0.0
    return max(0.0, min(1.0, ratio))


class DeepEraseProPlugin(Gimp.PlugIn):
    def do_query_procedures(self):
        return [PROCEDURE_NAME]

    def _add_arguments(self, procedure):
        """Les signatures d'ajout d'arguments ont varie entre revisions de
        GIMP 3.0 : chaque ajout est isole pour qu'un echec n'empeche jamais
        l'enregistrement du greffon (le dialogue se contente alors des
        valeurs par defaut)."""
        flags = GObject.ParamFlags.READWRITE
        try:
            procedure.add_double_argument(
                "context-margin", "Marge de contexte",
                "Proportion de contexte ajoutee autour de la selection",
                0.05, 1.0, DEFAULT_CONTEXT_MARGIN, flags)
        except Exception:
            pass
        try:
            procedure.add_double_argument(
                "feather", "Fondu des bords",
                "Rayon du fondu applique entre la zone traitee et l'image",
                0.0, 10.0, DEFAULT_FEATHER, flags)
        except Exception:
            pass
        try:
            procedure.add_boolean_argument(
                "force-cpu", "Forcer le CPU",
                "Ignorer le GPU (CUDA/MPS) et calculer sur le processeur",
                False, flags)
        except Exception:
            pass

    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(
            self, name, Gimp.PDBProcType.PLUGIN, self.run, None)
        procedure.set_image_types("RGB*, GRAY*")
        procedure.set_menu_label("Deep Erase Pro...")
        procedure.add_menu_path("<Image>/Filters/Enhance")
        try:
            procedure.set_documentation(
                "Efface le contenu de la selection par inpainting IA",
                "Exporte la selection vers un processus Python isole qui "
                "execute un modele LaMa TorchScript, avec repli automatique "
                "sur cv2.inpaint en cas d'echec.",
                name)
        except Exception:
            pass
        try:
            procedure.set_attribution("Deep Erase Pro", "Deep Erase Pro", "2026")
        except Exception:
            pass
        self._add_arguments(procedure)
        return procedure

    def _config_value(self, config, prop, default):
        try:
            value = config.get_property(prop)
            return default if value is None else value
        except Exception:
            return default

    def run(self, procedure, run_mode, image, drawables, config, run_data):
        work_dir = None
        pushed = False
        undo_started = False
        progress_started = False
        saved_sel = None
        temp_mask_layer = None

        try:
            if len(drawables) != 1:
                Gimp.message("Veuillez selectionner un seul calque actif.")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CALLING_ERROR, GLib.Error())

            if selection_is_empty(image):
                Gimp.message("Aucune selection detectee. Utilisez un outil de "
                             "selection autour de l'element a effacer.")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CALLING_ERROR, GLib.Error())

            GimpUi.init(PLUGIN_ID)
            if run_mode == Gimp.RunMode.INTERACTIVE:
                dialog = GimpUi.ProcedureDialog.new(procedure, config)
                dialog.fill(None)
                if not dialog.run():
                    dialog.destroy()
                    return procedure.new_return_values(
                        Gimp.PDBStatusType.CANCEL, GLib.Error())
                dialog.destroy()

            margin = float(self._config_value(config, "context-margin",
                                              DEFAULT_CONTEXT_MARGIN))
            feather = float(self._config_value(config, "feather", DEFAULT_FEATHER))
            force_cpu = bool(self._config_value(config, "force-cpu", False))

            if is_flatpak():
                Gimp.message(
                    "GIMP s'execute dans un bac a sable Flatpak : aucun Python "
                    "systeme n'y est accessible, ce greffon ne peut pas creer "
                    "son environnement IA. Utilisez une installation native de "
                    "GIMP (paquet systeme, AppImage ou installeur officiel).")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error())

            target_model_path = get_model_path(MODEL_FILENAME)
            if not os.path.isfile(target_model_path):
                _, shared_models_dir = get_shared_directories()
                Gimp.message(
                    "Le fichier modele '%s' est introuvable.\n\n"
                    "Les modeles IA sont mutualises entre les greffons de la "
                    "suite. Deposez le fichier exactement dans ce dossier :\n\n%s"
                    % (MODEL_FILENAME, shared_models_dir))
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error())

            size_ok, size_msg = check_model_size(target_model_path)
            if not size_ok:
                Gimp.message(size_msg)
                return procedure.new_return_values(
                    Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error())

            Gimp.progress_init("Deep Erase Pro : initialisation...")
            progress_started = True

            # Correctif : work_dir cree avant toute chose, et tous les fichiers
            # intermediaires (worker, params, logs, images) y sont confines.
            work_dir = tempfile.mkdtemp(prefix="%s_" % PLUGIN_ID)

            base_shared_path = get_shared_base()
            cache_path = os.path.join(base_shared_path, CACHE_FILENAME)

            valid_python = read_env_marker()
            if not valid_python:
                venv_dir, _ = get_shared_directories()
                shared_venv_python = venv_python_path(venv_dir)
                env_ok, env_diag = test_python_environment(shared_venv_python)
                if env_ok:
                    valid_python = shared_venv_python

            if not valid_python and os.path.isfile(cache_path):
                try:
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        cached = f.read().strip()
                    if cached:
                        env_ok, env_diag = test_python_environment(cached)
                        if env_ok:
                            valid_python = cached
                except Exception:
                    pass

            bootstrap_channel = None
            if not valid_python:
                sys_python, bootstrap_channel = find_system_python()
                if not sys_python:
                    raise RuntimeError(
                        "Aucun interpreteur Python systeme n'a ete trouve.\n\n"
                        "Le greffon a besoin de Python %s ou plus recent, "
                        "installe depuis python.org ou par le gestionnaire de "
                        "paquets du systeme. Un Python livre avec une autre "
                        "application n'est pas utilisable : il disparait a la "
                        "mise a jour de celle-ci."
                        % version_label(PYTHON_MIN_VERSION))
                valid_python = setup_venv(sys_python, work_dir)

            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    f.write(valid_python)
            except Exception:
                pass
            # Correctif 16 : consigner le canal et la date. Sans eux, un
            # interpreteur inattendu ne laisse qu'un chemin orphelin et des
            # hypotheses inverifiables plusieurs semaines apres.
            write_env_marker(valid_python, {
                'bootstrap': sys_python if bootstrap_channel else None,
                'channel': bootstrap_channel,
                'discovered_at': time.strftime('%Y-%m-%d %H:%M:%S')})

            # Repare sans intervention de l'utilisateur un venv installe avec
            # la roue PyTorch CPU-only alors qu'un GPU est disponible.
            cuda_ok, cuda_message = ensure_cuda_torch(valid_python, work_dir)
            if cuda_message:
                Gimp.message(cuda_message)

            # Correctif : les drapeaux garantissent que context_pop() et
            # undo_group_end() ne sont appeles que s'ils ont ete apparies.
            image.undo_group_start()
            undo_started = True
            Gimp.context_push()
            pushed = True

            path_in = os.path.join(work_dir, "in.png")
            path_mask = os.path.join(work_dir, "mask.png")
            path_out = os.path.join(work_dir, "out.png")
            file_in = Gio.File.new_for_path(path_in)
            file_mask = Gio.File.new_for_path(path_mask)

            bbox = selection_bounds(image)
            saved_sel = selection_save(image)

            selection_none(image)
            safe_export(image, drawables, file_in, path_in)

            layer_type = (Gimp.ImageType.RGBA_IMAGE
                          if image.get_base_type() == Gimp.ImageBaseType.RGB
                          else Gimp.ImageType.GRAYA_IMAGE)
            temp_mask_layer = Gimp.Layer.new(
                image, "temp_mask", image.get_width(), image.get_height(),
                layer_type, 100.0, Gimp.LayerMode.NORMAL)
            try:
                image.insert_layer(temp_mask_layer, None, 0)
            except AttributeError:
                image.add_layer(temp_mask_layer, 0)

            Gimp.context_set_background(Gegl.Color.new("black"))
            temp_mask_layer.edit_fill(Gimp.FillType.BACKGROUND)
            selection_load(image, saved_sel)
            Gimp.context_set_background(Gegl.Color.new("white"))
            temp_mask_layer.edit_fill(Gimp.FillType.BACKGROUND)
            selection_none(image)
            safe_export(image, [temp_mask_layer], file_mask, path_mask)

            # La mesure se fait sur le masque reellement transmis au modele,
            # une fois exporte : c'est la seule source exacte disponible.
            coverage = mask_coverage(path_mask, image, bbox)
            if coverage >= SELECTION_COVERAGE_WARN:
                Gimp.message(
                    "Attention : la selection couvre %.0f %% de l'image. Le "
                    "resultat sera en grande partie genere par le modele plutot "
                    "que reconstruit a partir du contexte local."
                    % (coverage * 100.0))

            if temp_mask_layer is not None and image.is_valid():
                try:
                    image.remove_layer(temp_mask_layer)
                except Exception:
                    pass
                temp_mask_layer = None

            skip_hash, known_hash = model_hash_plan(target_model_path)
            params = {
                'image': path_in,
                'mask': path_mask,
                'out': path_out,
                'model': target_model_path,
                'no_ai': False,
                'margin': margin,
                'feather': feather,
                'force_cpu': force_cpu,
                'skip_hash': skip_hash,
                'known_hash': known_hash or "",
            }

            Gimp.progress_set_text("Inpainting en cours...")
            result = execute_worker(valid_python, work_dir, params)

            if result['cache_invalid']:
                invalidate_env_cache()

            if not result['success']:
                detail = result['detail'] or ""
                if result['timed_out']:
                    detail = ("Depassement du delai (%d min)."
                              % (INFERENCE_TIMEOUT // 60))
                tail = (result['output'] or "").strip()[-1200:]
                raise RuntimeError(
                    "%s\n\nDetail technique :\n%s"
                    % (detail or "Le traitement n'a produit aucun resultat.", tail))

            if result['model_hash']:
                write_model_trust(target_model_path, result['model_hash'])

            messages = []
            if result['hash_changed']:
                messages.append(
                    "Le fichier modele '%s' a change depuis la derniere "
                    "execution (le traitement s'est poursuivi normalement)."
                    % MODEL_FILENAME)
            if (KNOWN_GOOD_HASHES and result['model_hash']
                    and result['model_hash'].lower() not in KNOWN_GOOD_HASHES):
                messages.append(
                    "Le fichier modele '%s' ne correspond a aucune empreinte de "
                    "reference connue. Le traitement a eu lieu normalement, mais "
                    "verifiez la provenance de ce fichier : il est execute par "
                    "PyTorch avec vos droits utilisateur." % MODEL_FILENAME)
            if not result['is_ai']:
                messages.append(
                    "Le traitement IA n'a pas abouti : le resultat provient du "
                    "repli OpenCV.\n\nRaison : %s"
                    % (result['detail'] or "inconnue"))

            gpu_warning = gpu_unused_warning(result, force_cpu)
            if gpu_warning:
                messages.append(gpu_warning)

            layer_name = build_layer_name(result, target_model_path)
            if not load_result_layer(image, path_out, layer_name):
                raise RuntimeError(
                    "Le resultat a bien ete calcule mais n'a pas pu etre "
                    "reimporte dans l'image (%s)." % path_out)

            for msg in messages:
                Gimp.message(msg)

            return procedure.new_return_values(
                Gimp.PDBStatusType.SUCCESS, GLib.Error())

        except Exception as e:
            texte = "Deep Erase Pro : %s" % e
            archive = archive_logs(work_dir)
            if archive:
                texte += (
                    "\n\nLes fichiers de diagnostic ont ete copies dans :\n"
                    + archive + "\n\n"
                    "Ce dossier est essentiel pour comprendre la panne : il "
                    "contient le journal du traitement et les parametres "
                    "employes. Joignez-le a tout signalement, sans quoi le "
                    "probleme ne peut pas etre reproduit."
                )
            Gimp.message(texte)
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error())

        finally:
            try:
                if temp_mask_layer is not None and image.is_valid():
                    image.remove_layer(temp_mask_layer)
            except Exception:
                pass
            try:
                # Correctif : la selection de l'utilisateur est restauree avant
                # de supprimer le canal temporaire.
                if saved_sel is not None and image.is_valid():
                    try:
                        selection_load(image, saved_sel)
                    except Exception:
                        pass
                    try:
                        image.remove_channel(saved_sel)
                    except Exception:
                        pass
            except Exception:
                pass
            if work_dir:
                shutil.rmtree(work_dir, ignore_errors=True)
            if pushed:
                try:
                    Gimp.context_pop()
                except Exception:
                    pass
            if undo_started:
                try:
                    image.undo_group_end()
                except Exception:
                    pass
            if progress_started:
                try:
                    Gimp.progress_end()
                except Exception:
                    pass


if __name__ == "__main__":
    Gimp.main(DeepEraseProPlugin.__gtype__, sys.argv)
