---
license: apache-2.0
tags:
- image-to-image
- inpainting
- gimp
- lama
---

# 🇬🇧 English

# 🎨 Lama Model (TorchScript) for Deep Erase Pro

This repository hosts the AI model weights used by the **Deep Erase Pro** GIMP plugin.
It is a compiled version of the renowned **LaMa** (Resolution-robust Large Mask Inpainting) model.

## 📋 Prerequisites

Before using the plugin, make sure you have:

- **GIMP 3.0 or later**, with the Deep Erase Pro plugin files installed in your GIMP plugin folder.
- **A system-wide Python 3.9+ installation**, separate from GIMP's own bundled Python. The plugin does not embed an interpreter — it looks for `python3`, `python`, or `py` on your system.
  - On Windows, Python from python.org or the Microsoft Store works.
  - On Linux/Debian/Ubuntu, you also need the `venv` module: `sudo apt install python3-venv`. Without it, the plugin's virtual environment creation will fail.
- **Internet access on first run.** The plugin creates a shared virtual environment and downloads `numpy`, `opencv-python-headless`, and `torch` (this can range from a few hundred MB to a few GB depending on your platform). This only happens once — subsequent runs reuse the same environment.
- **Free disk space**: budget at least 3–5 GB for the shared venv and dependencies, plus the model file itself.
- **The `lama.pt` model file**, placed exactly as described in the Installation section below.

## 🚀 Installation (For GIMP Users)

You do not need to execute this model file yourself — it is loaded by the plugin, not run directly.

1. Place the `deep_erase_pro.py` file in your GIMP 3.0 plug-ins directory, inside a subfolder named exactly `deep_erase_pro`.
2. Launch GIMP and run the filter (`Filters > Enhance > Deep Erase Pro...`). A dialog will appear showing the exact path of the shared folder that was just created automatically (`ai_suite_shared`), typically:
   * **Windows:** `C:\Users\YOUR_NAME\AppData\Roaming\GIMP\3.2\ai_suite_shared\models\`
   * **Linux/Mac:** `~/.config/GIMP/3.2/ai_suite_shared/models/`
3. Download the `lama.pt` model from this repository and place it in the folder GIMP just indicated.
4. Re-run the filter — it's ready to use!

On this same first run, the plugin also sets up a dedicated Python virtual environment under `ai_suite_shared/venv/` and installs its required packages. This environment is shared with other plugins in the same AI suite, so this setup step only happens once.

## 🛠️ Troubleshooting / FAQ

**"No system Python found"**
The plugin couldn't locate a usable Python interpreter outside of GIMP's own. Install Python 3.9+ from [python.org](https://www.python.org) (Windows/macOS) or your package manager (Linux), then relaunch GIMP.

**Virtual environment creation fails on Linux**
Install the venv module: `sudo apt install python3-venv` (Debian/Ubuntu) or the equivalent for your distribution, then try again.

**"Model file lama.pt not found"**
Double-check the file is placed in the exact shared folder path shown in the plugin's error message, and that it's named `lama.pt`.

**"Security alert: lama.pt file tampered or hash mismatch"**
The plugin refused to load the model because its computed SHA-256 hash doesn't match the expected value. Re-download `lama.pt` from this repository — do not use a copy from an untrusted source, and don't disable this check.

**The result looks like a basic blur/smear instead of AI inpainting**
This means the AI step failed and the plugin silently fell back to OpenCV's classic inpainting (`cv2.inpaint`) so you still get a result rather than a hard failure. The plugin shows a message with the underlying error when this happens — common causes are a missing/corrupted model file, insufficient memory, or a dependency import failure.

**Processing takes a long time or seems stuck**
Package installation is capped at 15 minutes and AI inference at 15 minutes; if either is exceeded, the plugin times out and reports it rather than hanging indefinitely. Large selections and CPU-only inference are the most common causes of long runtimes.

**"Cache corrompu" / corrupted cache**
The plugin caches the path to its Python environment for speed. If that environment becomes invalid (e.g. a package was removed), the plugin detects the failure, clears the cache automatically, and rebuilds the environment on the next run.

**Memory-related failures on large images**
The inference worker process is capped at 4 GB of memory. Very large selections may need to be reduced, or processed on a machine with more resources.

## 🔒 Security

### About the "Suspicious" (Pickle) Security Alert

Hugging Face displays a security warning on the `lama.pt` file. **This is expected and not itself evidence of a problem.**

The Deep Erase Pro plugin requires a TorchScript (`.pt`) model because it embeds both the AI weights and the complete neural network architecture, letting the plugin run standalone without a complex environment setup. The `.pt` format natively relies on Python's `pickle` module for serialization, so scanners like Protect AI or Picklescan flag this format as a precaution, regardless of the file's actual contents.

### What the integrity check does — and doesn't — protect against

Before every use, the plugin recomputes the SHA-256 fingerprint of `lama.pt` and refuses to run if it doesn't match the value published here:

```
300BE8A5C9A5F060FA35B144921FBF15C2F4D503CAD65AEE192B3365A883AAB4
```

This protects you against **corruption or tampering of the file after it left this repository** — a bad download, a compromised mirror, or a modified copy circulating elsewhere. It is a strong guarantee that the bytes you're running are exactly the ones published here.

It is **not** a guarantee about the trustworthiness of the model architecture or weights themselves — that trust is rooted in this file being compiled directly from the official [advimman/lama](https://github.com/advimman/lama) source, as described below. If you obtain a `lama.pt` from anywhere else, this hash will (correctly) reject it, and you should not add its hash to bypass the check.

### A technical detail worth knowing

To load this TorchScript file, the plugin's worker process calls `torch.jit.load()` after temporarily forcing PyTorch's `torch.load` to run with `weights_only=False`. This is required to load this model format, but it's worth stating plainly: it locally disables PyTorch's built-in guard against unsafe pickle deserialization for that call. This is why the SHA-256 verification above is not optional — it's the mechanism that substitutes for the guard being disabled, and it's why using the file from this repository (rather than a third-party copy) matters.

### Provenance and Integrity

This model is not a random file found online. It was generated and compiled locally into the TorchScript format directly from the official research project's source code.

*   **Official source repository:** [advimman/lama](https://github.com/advimman/lama)
*   **Expected SHA-256 Hash:** `300BE8A5C9A5F060FA35B144921FBF15C2F4D503CAD65AEE192B3365A883AAB4`

---

# 🇫🇷 Français

# 🎨 Modèle Lama (TorchScript) pour Deep Erase Pro

Ce dépôt héberge les poids du modèle d'intelligence artificielle utilisé par le plugin GIMP **Deep Erase Pro**.
Il s'agit d'une version compilée du célèbre modèle d'inpainting **LaMa** (Resolution-robust Large Mask Inpainting).

## 📋 Prérequis

Avant d'utiliser le plugin, assurez-vous de disposer de :

- **GIMP 3.0 ou supérieur**, avec les fichiers du plugin Deep Erase Pro installés dans votre dossier de plugins GIMP.
- **Une installation Python 3.9+ au niveau système**, distincte du Python embarqué par GIMP. Le plugin n'embarque pas d'interpréteur : il recherche `python3`, `python` ou `py` sur votre système.
  - Sous Windows, le Python de python.org ou du Microsoft Store convient.
  - Sous Linux/Debian/Ubuntu, il faut aussi le module `venv` : `sudo apt install python3-venv`. Sans lui, la création de l'environnement virtuel échouera.
- **Un accès internet lors du premier lancement.** Le plugin crée un environnement virtuel partagé et télécharge `numpy`, `opencv-python-headless` et `torch` (de quelques centaines de Mo à quelques Go selon la plateforme). Cela n'arrive qu'une seule fois ; les lancements suivants réutilisent le même environnement.
- **De l'espace disque libre** : prévoyez au moins 3 à 5 Go pour le venv partagé et ses dépendances, en plus du fichier modèle lui-même.
- **Le fichier modèle `lama.pt`**, placé exactement comme décrit dans la section Installation ci-dessous.

## 🚀 Installation (Pour les utilisateurs de GIMP)

Vous n'avez pas besoin d'exécuter ce fichier modèle vous-même — il est chargé par le plugin, pas exécuté directement.

1. Placez le fichier `deep_erase_pro.py` dans le répertoire plug-ins de GIMP 3.0, dans un sous-dossier nommé exactement `deep_erase_pro`.
2. Lancez GIMP et exécutez le filtre (`Filtres > Amélioration > Deep Erase Pro...`). Une fenêtre apparaîtra pour vous indiquer le chemin exact du dossier partagé qui vient d'être créé automatiquement (`ai_suite_shared`), généralement :
   * **Windows :** `C:\Users\VOTRE_NOM\AppData\Roaming\GIMP\3.2\ai_suite_shared\models\`
   * **Linux/Mac :** `~/.config/GIMP/3.2/ai_suite_shared/models/`
3. Téléchargez le modèle `lama.pt` depuis ce dépôt et déposez-le dans le dossier indiqué par GIMP.
4. Relancez le filtre, il est prêt à fonctionner !

Lors de ce même premier lancement, le plugin met aussi en place un environnement virtuel Python dédié dans `ai_suite_shared/venv/` et y installe les paquets nécessaires. Cet environnement est partagé avec les autres plugins de la même suite IA : cette étape ne se produit donc qu'une seule fois.

## 🛠️ Dépannage / FAQ

**« Aucun Python système trouvé »**
Le plugin n'a trouvé aucun interpréteur Python utilisable en dehors de celui de GIMP. Installez Python 3.9+ depuis [python.org](https://www.python.org) (Windows/macOS) ou votre gestionnaire de paquets (Linux), puis relancez GIMP.

**La création de l'environnement virtuel échoue sous Linux**
Installez le module venv : `sudo apt install python3-venv` (Debian/Ubuntu) ou l'équivalent pour votre distribution, puis réessayez.

**« Le fichier modèle lama.pt est introuvable »**
Vérifiez que le fichier est bien placé dans le dossier partagé exact indiqué par le message d'erreur du plugin, et qu'il se nomme bien `lama.pt`.

**« Alerte de sécurité : fichier falsifié ou hash incorrect »**
Le plugin a refusé de charger le modèle car son empreinte SHA-256 calculée ne correspond pas à la valeur attendue. Retéléchargez `lama.pt` depuis ce dépôt — n'utilisez pas une copie provenant d'une source non fiable, et ne désactivez pas cette vérification.

**Le résultat ressemble à un simple flou/lissage plutôt qu'à un inpainting IA**
Cela signifie que l'étape IA a échoué et que le plugin est automatiquement retombé sur l'inpainting classique d'OpenCV (`cv2.inpaint`), afin de vous fournir tout de même un résultat plutôt qu'un échec brutal. Le plugin affiche un message avec l'erreur sous-jacente dans ce cas — les causes courantes sont un fichier modèle manquant/corrompu, une mémoire insuffisante, ou un échec d'import de dépendance.

**Le traitement est long ou semble bloqué**
L'installation des paquets est limitée à 15 minutes et l'inférence IA à 15 minutes également ; au-delà, le plugin s'arrête et signale un dépassement de délai plutôt que de rester bloqué indéfiniment. Une sélection très large ou une inférence sur CPU seul sont les causes les plus fréquentes de lenteur.

**« Cache corrompu »**
Le plugin met en cache le chemin de son environnement Python pour gagner du temps. Si cet environnement devient invalide (par exemple un paquet supprimé), le plugin détecte l'échec, vide automatiquement le cache, puis reconstruit l'environnement au lancement suivant.

**Échecs liés à la mémoire sur de grandes images**
Le processus d'inférence est limité à 4 Go de mémoire. Pour de très grandes sélections, réduisez la zone traitée ou utilisez une machine disposant de plus de ressources.

## 🔒 Sécurité

### À propos de l'alerte de sécurité « Suspicious » (Pickle)

Hugging Face affiche un avertissement de sécurité sur le fichier `lama.pt`. **C'est attendu et ce n'est pas en soi la preuve d'un problème.**

Le plugin Deep Erase Pro nécessite un modèle au format TorchScript (`.pt`) car celui-ci intègre à la fois les poids de l'IA et l'architecture complète du réseau de neurones, ce qui permet au plugin de fonctionner de manière autonome sans installation complexe. Ce format s'appuie nativement sur le module Python `pickle` pour la sérialisation, ce qui pousse des scanners comme Protect AI ou Picklescan à le signaler par précaution, indépendamment du contenu réel du fichier.

### Ce que la vérification d'intégrité protège — et ce qu'elle ne protège pas

Avant chaque utilisation, le plugin recalcule l'empreinte SHA-256 de `lama.pt` et refuse de l'exécuter si elle ne correspond pas à la valeur publiée ici :

```
300BE8A5C9A5F060FA35B144921FBF15C2F4D503CAD65AEE192B3365A883AAB4
```

Cela vous protège contre **une corruption ou une altération du fichier survenue après sa publication sur ce dépôt** — un téléchargement défectueux, un miroir compromis, ou une copie modifiée circulant ailleurs. C'est une garantie solide que les octets que vous exécutez sont exactement ceux publiés ici.

Ce n'est en revanche **pas** une garantie sur la fiabilité de l'architecture ou des poids du modèle en eux-mêmes — cette confiance repose sur le fait que ce fichier a été compilé directement à partir du code source officiel [advimman/lama](https://github.com/advimman/lama), comme détaillé ci-dessous. Si vous obtenez un `lama.pt` provenant d'ailleurs, ce hash le rejettera (à juste titre), et il ne faut pas ajouter son empreinte pour contourner la vérification.

### Un détail technique à connaître

Pour charger ce fichier TorchScript, le processus worker du plugin appelle `torch.jit.load()` après avoir temporairement forcé `torch.load` de PyTorch à s'exécuter avec `weights_only=False`. Cela est nécessaire pour charger ce format de modèle, mais il est important de le dire clairement : cela désactive localement le garde-fou intégré de PyTorch contre la désérialisation pickle non sécurisée, pour cet appel précis. C'est pourquoi la vérification SHA-256 ci-dessus n'est pas optionnelle — c'est elle qui compense la désactivation de ce garde-fou — et c'est pourquoi il est important d'utiliser le fichier de ce dépôt plutôt qu'une copie tierce.

### Provenance et Intégrité

Ce modèle n'est pas un fichier aléatoire trouvé sur internet. Il a été généré et compilé localement au format TorchScript directement à partir du code source officiel du projet de recherche.

*   **Dépôt officiel d'origine :** [advimman/lama](https://github.com/advimman/lama)
*   **Hash SHA-256 attendu par le plugin :** `300BE8A5C9A5F060FA35B144921FBF15C2F4D503CAD65AEE192B3365A883AAB4`
