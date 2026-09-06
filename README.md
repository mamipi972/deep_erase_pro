# Deep Erase Pro (GIMP Plugin)

*[Français ci-dessous](#-français)*

**Deep Erase Pro** is a GIMP 3.0 plugin that removes unwanted objects from an image using AI-powered inpainting (the **LaMa** model), with an automatic fallback to classic OpenCV inpainting if the AI step fails.

- 🎯 Select an object, run one filter, it's erased and reconstructed from context.
- 🧠 Uses a TorchScript-compiled version of [advimman/lama](https://github.com/advimman/lama) for AI inpainting.
- 🛡️ Verifies the model file's SHA-256 fingerprint before every run.
- 🔁 Falls back to OpenCV's `cv2.inpaint` if the AI step is unavailable or fails, so you always get a result.
- ⚙️ Sets up its own isolated Python environment automatically — no manual `pip install`.

## 📋 Requirements

- **GIMP 3.0 or later.**
- **A system-wide Python 3.9+ installation**, separate from GIMP's own bundled Python. The plugin does not embed an interpreter — it looks for `python3`, `python`, or `py` on your system.
  - On Windows, Python from python.org or the Microsoft Store works.
  - On Linux/Debian/Ubuntu, you also need the `venv` module: `sudo apt install python3-venv`.
- **Internet access on first run.** The plugin creates a shared virtual environment and downloads `numpy`, `opencv-python-headless`, and `torch` (a few hundred MB to a few GB depending on your platform). This happens once; later runs reuse the same environment.
- **Free disk space**: at least 3–5 GB for the shared environment and dependencies, plus the model file.
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

On this same first run, the plugin also sets up a dedicated Python virtual environment under `ai_suite_shared/venv/` and installs its required packages. This environment is shared with other plugins in the same AI suite.

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

**"Security alert: lama.pt file tampered or hash mismatch"**
The plugin refused to load the model because its computed SHA-256 hash doesn't match the expected value. Re-download `lama.pt` from the [Hugging Face repository](https://huggingface.co/mipi77/lama-deep-erase-pro/tree/main) — don't use a copy from an untrusted source, and don't disable this check.

**The result looks like a basic blur/smear instead of AI inpainting**
The AI step failed and the plugin fell back to OpenCV's classic inpainting so you still get a result. The plugin shows the underlying error — common causes are a missing/corrupted model file, insufficient memory, or a dependency import failure.

**Processing takes a long time or seems stuck**
Package installation and AI inference are each capped at 15 minutes; beyond that the plugin times out and reports it. Large selections and CPU-only inference are the most common causes of long runtimes.

**"Cache corrompu" / corrupted cache**
The plugin caches the path to its Python environment for speed. If that environment becomes invalid, the plugin detects it, clears the cache, and rebuilds the environment on the next run.

**Memory-related failures on large images**
The inference worker is capped at 4 GB of memory. Reduce the selection size or use a machine with more resources.

## 🔒 Security notes

- The model file lives on a separate Hugging Face repository and is verified against a fixed SHA-256 hash before every run — see that repository's README for full details on what this check does and doesn't guarantee.
- To load the TorchScript model, the plugin's worker process temporarily forces `torch.load` to run with `weights_only=False` before calling `torch.jit.load()`. This is required for this model format, but it does disable PyTorch's built-in guard against unsafe pickle deserialization for that call — which is exactly why the hash check exists and why only the model from the linked Hugging Face repository should be used.
- The worker process runs with a capped memory limit and a timeout, and all temporary files are created in a dedicated temp folder and cleaned up after each run.

## 📄 License

Apache-2.0.

---

# 🇫🇷 Français

# Deep Erase Pro (Plugin GIMP)

**Deep Erase Pro** est un plugin GIMP 3.0 qui supprime les éléments indésirables d'une image grâce à un inpainting par IA (le modèle **LaMa**), avec un repli automatique sur l'inpainting classique d'OpenCV si l'étape IA échoue.

- 🎯 Sélectionnez un objet, lancez un filtre, il est effacé et reconstruit à partir du contexte.
- 🧠 Utilise une version compilée en TorchScript de [advimman/lama](https://github.com/advimman/lama) pour l'inpainting IA.
- 🛡️ Vérifie l'empreinte SHA-256 du fichier modèle avant chaque exécution.
- 🔁 Repli sur `cv2.inpaint` d'OpenCV si l'étape IA est indisponible ou échoue, pour toujours obtenir un résultat.
- ⚙️ Met en place automatiquement son propre environnement Python isolé — aucun `pip install` manuel.

## 📋 Prérequis

- **GIMP 3.0 ou supérieur.**
- **Une installation Python 3.9+ au niveau système**, distincte du Python embarqué par GIMP. Le plugin n'embarque pas d'interpréteur : il recherche `python3`, `python` ou `py` sur votre système.
  - Sous Windows, le Python de python.org ou du Microsoft Store convient.
  - Sous Linux/Debian/Ubuntu, il faut aussi le module `venv` : `sudo apt install python3-venv`.
- **Un accès internet lors du premier lancement.** Le plugin crée un environnement virtuel partagé et télécharge `numpy`, `opencv-python-headless` et `torch` (de quelques centaines de Mo à quelques Go selon la plateforme). Cela n'arrive qu'une seule fois.
- **De l'espace disque libre** : au moins 3 à 5 Go pour l'environnement partagé et ses dépendances, en plus du fichier modèle.
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

Lors de ce même premier lancement, le plugin met aussi en place un environnement virtuel Python dédié dans `ai_suite_shared/venv/` et y installe les paquets nécessaires. Cet environnement est partagé avec les autres plugins de la même suite IA.

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

**« Alerte de sécurité : fichier falsifié ou hash incorrect »**
Le plugin a refusé de charger le modèle car son empreinte SHA-256 calculée ne correspond pas à la valeur attendue. Retéléchargez `lama.pt` depuis le [dépôt Hugging Face](https://huggingface.co/mipi77/lama-deep-erase-pro/tree/main) — n'utilisez pas une copie provenant d'une source non fiable, et ne désactivez pas cette vérification.

**Le résultat ressemble à un simple flou/lissage plutôt qu'à un inpainting IA**
L'étape IA a échoué et le plugin est retombé sur l'inpainting classique d'OpenCV pour vous fournir tout de même un résultat. Le plugin affiche l'erreur sous-jacente — les causes courantes sont un fichier modèle manquant/corrompu, une mémoire insuffisante, ou un échec d'import de dépendance.

**Le traitement est long ou semble bloqué**
L'installation des paquets et l'inférence IA sont chacune limitées à 15 minutes ; au-delà, le plugin s'arrête et signale un dépassement de délai. Une sélection très large ou une inférence sur CPU seul sont les causes les plus fréquentes.

**« Cache corrompu »**
Le plugin met en cache le chemin de son environnement Python. Si cet environnement devient invalide, le plugin le détecte, vide le cache, puis reconstruit l'environnement au lancement suivant.

**Échecs liés à la mémoire sur de grandes images**
Le processus d'inférence est limité à 4 Go de mémoire. Réduisez la zone traitée ou utilisez une machine disposant de plus de ressources.

## 🔒 Remarques de sécurité

- Le fichier modèle réside sur un dépôt Hugging Face séparé et est vérifié par rapport à un hash SHA-256 fixe avant chaque exécution — voir le README de ce dépôt pour le détail de ce que cette vérification garantit ou non.
- Pour charger le modèle TorchScript, le processus worker du plugin force temporairement `torch.load` à s'exécuter avec `weights_only=False` avant d'appeler `torch.jit.load()`. Cela est nécessaire pour ce format de modèle, mais cela désactive bien le garde-fou intégré de PyTorch contre la désérialisation pickle non sécurisée pour cet appel — c'est précisément pour cela que la vérification par hash existe, et pourquoi seul le modèle du dépôt Hugging Face lié doit être utilisé.
- Le processus worker s'exécute avec une limite de mémoire et un délai maximal, et tous les fichiers temporaires sont créés dans un dossier dédié puis nettoyés après chaque exécution.

## 📄 Licence

Apache-2.0.
