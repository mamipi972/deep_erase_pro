# Deep Erase Pro for GIMP 3.0 🎨

[Français plus bas]

Deep Erase Pro is an advanced, standalone AI inpainting plugin for GIMP 3.0. It allows you to effortlessly remove unwanted objects, watermarks, or defects from your images using the powerful LaMa (Resolution-robust Large Mask Inpainting) model, directly on your local machine.

**Key Features**
* **Smart Cropping:** Only processes the selected area (bounding box) to drastically reduce RAM/VRAM usage and speed up generation.
* **Security First:** Implements strict SHA-256 hash verification on the AI model before execution to ensure file integrity.
* **OpenCV Fallback:** Automatically switches to standard OpenCV inpainting if the AI environment cannot be loaded.

**Installation**
1. Download `deep_erase_pro.py` and place it in your GIMP 3.0 `plug-ins` directory (make sure the folder is also named `deep_erase_pro`).
2. Download the required AI model (`lama.pt`) from the [mipi77/lama-deep-erase-pro Hugging Face repository](https://huggingface.co/mipi77/lama-deep-erase-pro).
3. Place the `lama.pt` file inside your GIMP configuration folder at `ai_suite_shared/models/`.

## 🛡️ Security Information

AI models in PyTorch format (`.pt`) use Python's `pickle` module, which can trigger false positives on security scanners (like antivirus software or Hugging Face's Protect AI). To ensure absolute safety:
* **Cryptographic Verification:** The plugin automatically calculates the SHA-256 hash of `lama.pt` before loading it. If the file is modified or corrupted, the execution is instantly blocked.
* **Isolated Environment:** The plugin enforces isolated temporary directories (`tempfile.mkdtemp`) with restricted permissions to process your images safely.
* **Safe Dependencies:** Required packages (PyTorch, OpenCV) are installed strictly via pre-compiled binaries (wheels) to avoid running arbitrary setup scripts.

## 🛠️ Troubleshooting

* **The plugin doesn't appear in the GIMP menu:**
  In GIMP 3.0, the Python file name must exactly match its parent folder. Ensure your path looks exactly like this: `.../plug-ins/deep_erase_pro/deep_erase_pro.py`.
* **"Model lama.pt not found" error:**
  Ensure the `lama.pt` file is placed in `ai_suite_shared/models/` inside your GIMP configuration directory, NOT in the plug-ins folder.
* **Virtual Environment (Venv) creation fails:**
  Make sure Python 3 is installed on your system and added to your system's PATH. On Linux, you might need to run `sudo apt install python3-venv`.

**Need visual help?** Check out the step-by-step installation guides and open-source software tutorials on the **Miguel Pineau** YouTube channel.

For full visual instructions and plugin demonstrations, check out the video tutorials on the **Miguel Pineau** YouTube channel.

---

# Deep Erase Pro pour GIMP 3.0 🎨

Deep Erase Pro est un plugin d'inpainting IA avancé et autonome pour GIMP 3.0. Il vous permet de supprimer sans effort les objets indésirables, les filigranes ou les défauts de vos images en utilisant le puissant modèle LaMa, directement sur votre machine locale.

**Fonctionnalités Principales**
* **Recadrage Intelligent :** Ne traite que la zone sélectionnée pour réduire drastiquement l'utilisation de la RAM/VRAM et accélérer le calcul.
* **Sécurité Intégrée :** Vérifie l'empreinte SHA-256 du modèle IA avant chaque exécution pour garantir l'intégrité du fichier.
* **Repli Automatique :** Bascule automatiquement sur l'inpainting classique d'OpenCV si l'environnement IA rencontre une erreur.

**Installation**
1. Téléchargez `deep_erase_pro.py` et placez-le dans le répertoire `plug-ins` de GIMP 3.0 (dans un dossier nommé exactement `deep_erase_pro`).
2. Téléchargez le modèle IA requis (`lama.pt`) depuis le [dépôt Hugging Face mipi77/lama-deep-erase-pro](https://huggingface.co/mipi77/lama-deep-erase-pro).
3. Placez le fichier `lama.pt` dans votre dossier de configuration GIMP, sous `ai_suite_shared/models/`.

## 🛡️ Informations de Sécurité

Les modèles IA au format PyTorch (`.pt`) utilisent le module Python `pickle`, ce qui déclenche souvent de faux positifs sur les scanners de sécurité (comme les antivirus ou Protect AI sur Hugging Face). Pour garantir une sécurité absolue :
* **Vérification Cryptographique :** Le plugin calcule automatiquement le hash SHA-256 de `lama.pt` avant de le charger. Si le fichier est altéré ou corrompu, l'exécution est instantanément bloquée.
* **Environnement Isolé :** Le plugin utilise des dossiers temporaires isolés (`tempfile.mkdtemp`) avec des droits restreints pour traiter vos images en toute sécurité.
* **Dépendances Sécurisées :** Les paquets requis (PyTorch, OpenCV) sont installés strictement via des binaires pré-compilés (wheels) pour éviter l'exécution de scripts d'installation arbitraires.

## 🛠️ Dépannage

* **Le plugin n'apparaît pas dans le menu GIMP :**
  Dans GIMP 3.0, le nom du fichier Python doit correspondre exactement au nom de son dossier parent. Vérifiez que votre chemin est exactement : `.../plug-ins/deep_erase_pro/deep_erase_pro.py`.
* **Erreur "Le fichier modèle lama.pt est introuvable" :**
  Assurez-vous que le fichier `lama.pt` est bien placé dans le dossier `ai_suite_shared/models/` de votre répertoire de configuration GIMP, et NON dans le dossier plug-ins.
* **Échec de la création de l'environnement virtuel (Venv) :**
  Vérifiez que Python 3 est installé sur votre système et ajouté au PATH. Sur Linux, il peut être nécessaire d'exécuter `sudo apt install python3-venv`.

**Besoin d'une aide visuelle ?** Retrouvez les guides d'installation pas-à-pas et d'autres tutoriels sur les logiciels open-source directement sur la chaîne YouTube **Miguel Pineau**.

Pour des instructions visuelles complètes et des démonstrations du plugin, n'hésitez pas à consulter les tutoriels vidéo sur la chaîne YouTube **Miguel Pineau**.
