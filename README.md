# Deep Erase Pro (GIMP Plugin)

*[Français ci-dessous](#-français)*

**Deep Erase Pro** is a GIMP 3.0 plugin that removes unwanted objects from an image using AI-powered inpainting (the **LaMa** model), with an automatic fallback to classic OpenCV inpainting if the AI step fails.

- 🎯 Select an object, run one filter, it's erased and reconstructed from context.
- 🧠 Uses a TorchScript-compiled version of [advimman/lama](https://github.com/advimman/lama) for AI inpainting.
- 🛡️ Checks the model file's size, then its SHA-256 fingerprint, and warns you if the file changed since the previous run.
- 🔁 Falls back to OpenCV's `cv2.inpaint` if the AI step is unavailable or fails, so you always get a result.
- ⚙️ Sets up its own isolated Python environment automatically — no manual `pip install`.

## 📋 Requirements

- **GIMP 3.0 or later.**
- **A system-wide Python 3.10 or later**, separate from GIMP's own bundled Python. The plugin does not embed an interpreter.
  - On Windows, install it from python.org. The plugin finds it through the registry, the `py` launcher, or the standard install locations — adding it to `PATH` is convenient but not required.
  - **A Python bundled inside another application does not qualify.** Blender, Krita, FreeCAD and similar tools ship their own interpreter; an environment built on one of them stops working the moment that application is updated or uninstalled. The plugin now prefers interpreters declared to the system and records which channel it used.
  - On Linux/Debian/Ubuntu, you also need the `venv` module: `sudo apt install python3-venv`.
- **Internet access on first run.** The plugin creates a shared virtual environment and downloads `numpy`, `opencv-python-headless`, and `torch` (a few hundred MB to a few GB depending on your platform). This happens once; later runs reuse the same environment.
- **Free disk space**: the plugin now refuses to start an installation without **3 GB** free for the CPU engine, or **10 GB** for the CUDA variant, and tells you how much is missing. Add the model file on top of that.
- **The `lama.pt` model file**, downloaded separately (see Installation below) — it is *not* included in this repository because of its size and because model weights are versioned independently on Hugging Face.

## 🚀 Installation

1. Place `deep_erase_pro.py` in your GIMP plug-ins directory, inside a subfolder named exactly `deep_erase_pro`.
   - **Windows:** `%APPDATA%\GIMP\3.2\plug-ins\deep_erase_pro\deep_erase_pro.py`
   - **Linux/Mac:** `~/.config/GIMP/3.2/plug-ins/deep_erase_pro/deep_erase_pro.py`
2. Launch GIMP and run the filter (`Filters > Enhance > Deep Erase Pro...`). A dialog will show the exact path of the shared folder (`ai_suite_shared`) that was just created automatically, typically:
   - **Windows:** `...\AppData\Roaming\GIMP\3.2\ai_suite_shared\models\`
   - **Linux/Mac:** `~/.config/GIMP/3.2/ai_suite_shared/models/`
3. Download the `lama.pt` model from **[mipi77/lama-deep-erase-pro on Hugging Face](https://huggingface.co/mipi77/lama-deep-erase-pro/tree/main)** and place it in the folder GIMP just indicated.
4. Re-run the filter — it's ready to use!

On this same first run, the plugin also sets up a dedicated Python virtual environment under `ai_suite_shared/venv-torch/` and installs its required packages. This environment is shared with other plugins in the same AI suite.

## 🖌️ Usage

1. Open an image in GIMP.
2. Make a selection around the object you want to remove (the selection tools — lasso, rectangle, etc. — all work).
3. Run `Filters > Enhance > Deep Erase Pro...`.
4. The plugin exports the selection and a mask, runs inpainting, and inserts the result as a new layer.

If your selection covers almost the entire image, the plugin will warn you that the result will be mostly AI-generated rather than reconstructed from local context.

## 🛠️ Troubleshooting / FAQ

**"No system Python found"**
Install Python 3.9+ from [python.org](https://www.python.org) (Windows/macOS) or your package manager (Linux), then relaunch GIMP.

**Virtual environment creation fails on Linux**
Install the venv module: `sudo apt install python3-venv` (Debian/Ubuntu) or the equivalent for your distribution.

**"Model file lama.pt not found"**
Check the file is placed in the exact shared folder path shown in the plugin's message, and that it's named `lama.pt`.

**"The model file has changed since the last run"**
This is a warning, not a refusal: processing continues. The plugin memorises the model's fingerprint on first use and compares it afterwards, so it can tell you when the file is no longer the one you started with. If you replaced it deliberately, ignore the message. If you didn't, re-download `lama.pt` from the [Hugging Face repository](https://huggingface.co/mipi77/lama-deep-erase-pro/tree/main).

**Where do I find the logs after a failure?**
The plugin copies them, before deleting its working directory, into a timestamped folder under `ai_suite_shared/logs/`. The error message shows the exact path. **Attach that folder to any bug report** — without it, a failure is just "it doesn't work", which cannot be reproduced. The ten most recent incidents are kept.

**The result looks like a basic blur/smear instead of AI inpainting**
The AI step failed and the plugin fell back to OpenCV's classic inpainting so you still get a result. The plugin shows the underlying error — common causes are a missing/corrupted model file, insufficient memory, or a dependency import failure.

**Processing takes a long time or seems stuck**
The first run installs PyTorch and takes **about 5 minutes** on a normal connection (measured on a Ryzen 5 5500 / RTX 3050). After that, a typical erase takes seconds. Package installation is capped at 30 minutes, AI inference at 15, and the OpenCV fallback at 10. Beyond that the plugin stops and says so rather than hanging. Large selections and CPU-only inference are the usual causes.

**"Cache corrompu" / corrupted cache**
The plugin caches the path to its Python environment for speed. If that environment becomes invalid, the plugin detects it, clears the cache, and rebuilds the environment on the next run.

**Memory-related failures on large images**
When no GPU is usable, the worker is capped at 75 % of physical RAM — not a fixed 4 GB. No cap is applied when a GPU is in use, because initialising CUDA reserves a large virtual address space that a cap would wrongly reject. Reduce the selection or the context margin.

## 🔒 Security notes

**Read this before trusting the integrity check.** Earlier versions of this
README claimed the plugin refuses to run when the model's SHA-256 doesn't match
a published value. **It does not, and it never did in the shipped code.** The
list of reference fingerprints (`KNOWN_GOOD_HASHES`) is empty, so what actually
runs is trust-on-first-use: the fingerprint is memorised the first time the
model loads successfully, compared on later runs, and a mismatch produces a
**warning** while processing continues.

What that gives you, honestly stated:

- **It detects change, not malice.** A model that was already malicious the
  first time you used it becomes the trusted reference. The check tells you
  "this file is no longer the one you started with" — nothing more.
- **The size check comes first** and is the more useful of the two in practice:
  anything outside 8 MB – 2 GB is rejected before being read, which catches
  interrupted downloads that would otherwise load and produce silently wrong
  output.
- **A fixed hash in the plugin would not be a security boundary anyway.** The
  reference value would sit in the same `.py` file that anyone able to replace
  the model can also edit.
- **The real protection is provenance.** Download `lama.pt` from the linked
  Hugging Face repository and compare its published SHA-256 yourself if it
  matters to you.

To load the TorchScript model, the worker temporarily forces `torch.load` to run
with `weights_only=False` before calling `torch.jit.load()`. This is required by
the format, and it does disable PyTorch's guard against unsafe pickle
deserialization for that call. **Nothing in the plugin compensates for that.**
The model file is executed with your user rights — use weights whose origin you
trust.

The worker also runs with a timeout, and with a memory cap when no GPU is in
use; all temporary files live in a per-run folder that is deleted afterwards,
including on failure.

## 📄 License

Apache-2.0.

---

# 🇫🇷 Français

# Deep Erase Pro (Plugin GIMP)

**Deep Erase Pro** est un plugin GIMP 3.0 qui supprime les éléments indésirables d'une image grâce à un inpainting par IA (le modèle **LaMa**), avec un repli automatique sur l'inpainting classique d'OpenCV si l'étape IA échoue.

- 🎯 Sélectionnez un objet, lancez un filtre, il est effacé et reconstruit à partir du contexte.
- 🧠 Utilise une version compilée en TorchScript de [advimman/lama](https://github.com/advimman/lama) pour l'inpainting IA.
- 🛡️ Contrôle la taille du fichier modèle, puis son empreinte SHA-256, et vous avertit s'il a changé depuis l'exécution précédente.
- 🔁 Repli sur `cv2.inpaint` d'OpenCV si l'étape IA est indisponible ou échoue, pour toujours obtenir un résultat.
- ⚙️ Met en place automatiquement son propre environnement Python isolé — aucun `pip install` manuel.

## 📋 Prérequis

- **GIMP 3.0 ou supérieur.**
- **Une installation Python 3.10 ou plus récente au niveau système**, distincte du Python embarqué par GIMP. Le plugin n'embarque pas d'interpréteur.
  - Sous Windows, installez-le depuis python.org. Le greffon le trouve via le registre, le lanceur `py` ou les emplacements d'installation standards — l'ajouter au `PATH` est pratique mais pas nécessaire.
  - **Un Python embarqué dans une autre application ne convient pas.** Blender, Krita, FreeCAD et consorts livrent leur propre interpréteur ; un environnement bâti dessus cesse de fonctionner dès que cette application est mise à jour ou désinstallée. Le greffon privilégie désormais les interpréteurs déclarés au système et consigne le canal qu'il a utilisé.
  - Sous Linux/Debian/Ubuntu, il faut aussi le module `venv` : `sudo apt install python3-venv`.
- **Un accès internet lors du premier lancement.** Le plugin crée un environnement virtuel partagé et télécharge `numpy`, `opencv-python-headless` et `torch` (de quelques centaines de Mo à quelques Go selon la plateforme). Cela n'arrive qu'une seule fois.
- **De l'espace disque libre** : le greffon refuse désormais d'engager une installation sans **3 Go** libres pour le moteur processeur, ou **10 Go** pour la variante CUDA, et indique ce qui manque. Ajoutez le fichier modèle par-dessus.
- **Le fichier modèle `lama.pt`**, téléchargé séparément (voir Installation ci-dessous) — il n'est *pas* inclus dans ce dépôt en raison de sa taille et parce que les poids du modèle sont versionnés indépendamment sur Hugging Face.

## 🚀 Installation

1. Placez `deep_erase_pro.py` dans votre répertoire plug-ins de GIMP, dans un sous-dossier nommé exactement `deep_erase_pro`.
   - **Windows :** `%APPDATA%\GIMP\3.2\plug-ins\deep_erase_pro\deep_erase_pro.py`
   - **Linux/Mac :** `~/.config/GIMP/3.2/plug-ins/deep_erase_pro/deep_erase_pro.py`
2. Lancez GIMP et exécutez le filtre (`Filtres > Amélioration > Deep Erase Pro...`). Une fenêtre affichera le chemin exact du dossier partagé (`ai_suite_shared`) qui vient d'être créé automatiquement, généralement :
   - **Windows :** `...\AppData\Roaming\GIMP\3.2\ai_suite_shared\models\`
   - **Linux/Mac :** `~/.config/GIMP/3.2/ai_suite_shared/models/`
3. Téléchargez le modèle `lama.pt` depuis **[mipi77/lama-deep-erase-pro sur Hugging Face](https://huggingface.co/mipi77/lama-deep-erase-pro/tree/main)** et déposez-le dans le dossier indiqué par GIMP.
4. Relancez le filtre, il est prêt à fonctionner !

Lors de ce même premier lancement, le plugin met aussi en place un environnement virtuel Python dédié dans `ai_suite_shared/venv-torch/` et y installe les paquets nécessaires. Cet environnement est partagé avec les autres plugins de la même suite IA.

## 🖌️ Utilisation

1. Ouvrez une image dans GIMP.
2. Faites une sélection autour de l'objet à supprimer (tous les outils de sélection fonctionnent — lasso, rectangle, etc.).
3. Lancez `Filtres > Amélioration > Deep Erase Pro...`.
4. Le plugin exporte la sélection et un masque, effectue l'inpainting, et insère le résultat comme nouveau calque.

Si votre sélection couvre presque toute l'image, le plugin vous avertira que le résultat sera en grande partie généré par l'IA plutôt que reconstruit à partir du contexte local.

## 🛠️ Dépannage / FAQ

**« Aucun Python système trouvé »**
Installez Python 3.9+ depuis [python.org](https://www.python.org) (Windows/macOS) ou votre gestionnaire de paquets (Linux), puis relancez GIMP.

**La création de l'environnement virtuel échoue sous Linux**
Installez le module venv : `sudo apt install python3-venv` (Debian/Ubuntu) ou l'équivalent pour votre distribution.

**« Le fichier modèle lama.pt est introuvable »**
Vérifiez que le fichier est placé dans le dossier partagé exact indiqué par le message du plugin, et qu'il se nomme bien `lama.pt`.

**« Le fichier modèle a changé depuis la dernière exécution »**
C'est un avertissement, pas un refus : le traitement se poursuit. Le greffon mémorise l'empreinte du modèle à la première utilisation puis la compare ensuite, afin de vous signaler que le fichier n'est plus celui du départ. Si vous l'avez remplacé volontairement, ignorez le message. Sinon, retéléchargez `lama.pt` depuis le [dépôt Hugging Face](https://huggingface.co/mipi77/lama-deep-erase-pro/tree/main).

**Où trouver les journaux après un échec ?**
Le greffon les copie, avant de supprimer son dossier de travail, dans un dossier horodaté sous `ai_suite_shared/logs/`. Le message d'erreur affiche le chemin exact. **Joignez ce dossier à tout signalement** — sans lui, une panne se résume à « ça ne marche pas » et ne peut être reproduite. Les dix incidents les plus récents sont conservés.

**Le résultat ressemble à un simple flou/lissage plutôt qu'à un inpainting IA**
L'étape IA a échoué et le plugin est retombé sur l'inpainting classique d'OpenCV pour vous fournir tout de même un résultat. Le plugin affiche l'erreur sous-jacente — les causes courantes sont un fichier modèle manquant/corrompu, une mémoire insuffisante, ou un échec d'import de dépendance.

**Le traitement est long ou semble bloqué**
Le premier lancement installe PyTorch et prend **environ 5 minutes** sur une connexion normale (mesuré sur Ryzen 5 5500 / RTX 3050). Ensuite, un effacement courant prend quelques secondes. L'installation des paquets est limitée à 30 minutes, l'inférence IA à 15, et le repli OpenCV à 10. Au-delà, le greffon s'arrête et le dit plutôt que de rester bloqué. Une sélection très large ou un calcul sur processeur seul sont les causes habituelles.

**« Cache corrompu »**
Le plugin met en cache le chemin de son environnement Python. Si cet environnement devient invalide, le plugin le détecte, vide le cache, puis reconstruit l'environnement au lancement suivant.

**Échecs liés à la mémoire sur de grandes images**
Quand aucun GPU n'est utilisable, le worker est limité à 75 % de la mémoire physique — et non à 4 Go fixes. Aucune limite n'est posée lorsqu'un GPU sert, l'initialisation de CUDA réservant un espace d'adressage virtuel considérable qu'une limite rejetterait à tort. Réduisez la sélection ou la marge de contexte.

## 🔒 Remarques de sécurité

**À lire avant de faire confiance au contrôle d'intégrité.** Les versions
précédentes de ce README affirmaient que le greffon refuse de s'exécuter si
l'empreinte SHA-256 du modèle ne correspond pas à une valeur publiée. **C'est
faux, et ça l'a toujours été dans le code livré.** La liste d'empreintes de
référence (`KNOWN_GOOD_HASHES`) est vide : ce qui s'applique réellement est une
confiance à la première utilisation. L'empreinte est mémorisée au premier
chargement réussi, comparée aux exécutions suivantes, et un écart produit un
**avertissement** sans interrompre le traitement.

Ce que cela apporte, dit franchement :

- **Cela détecte un changement, pas une malveillance.** Un modèle déjà piégé
  lors de la première utilisation devient la référence de confiance. Le contrôle
  dit « ce fichier n'est plus celui du départ », rien de plus.
- **Le contrôle de taille passe en premier** et s'avère le plus utile des deux
  en pratique : tout fichier hors de la plage 8 Mo – 2 Go est rejeté avant
  d'être lu, ce qui attrape les téléchargements interrompus qui, sinon, se
  chargent et produisent un résultat silencieusement faux.
- **Un hash figé dans le greffon ne serait de toute façon pas une frontière de
  sécurité.** La valeur de référence résiderait dans le même fichier `.py` que
  peut éditer quiconque est déjà capable de remplacer le modèle.
- **La vraie protection est la provenance.** Téléchargez `lama.pt` depuis le
  dépôt Hugging Face lié et comparez vous-même l'empreinte publiée si le sujet
  vous importe.

Pour charger le modèle TorchScript, le worker force temporairement `torch.load`
à s'exécuter avec `weights_only=False` avant d'appeler `torch.jit.load()`. Le
format l'exige, et cela désactive bien le garde-fou de PyTorch contre la
désérialisation pickle non sécurisée pour cet appel. **Rien dans le greffon ne
compense cette désactivation.** Le fichier de poids est exécuté avec vos droits
utilisateur — n'utilisez que des modèles dont vous connaissez l'origine.

Le worker s'exécute par ailleurs avec un délai maximal, et avec une limite
mémoire quand aucun GPU ne sert ; tous les fichiers temporaires vivent dans un
dossier propre à chaque exécution, supprimé ensuite, y compris en cas d'échec.

## 📄 Licence

Apache-2.0.
