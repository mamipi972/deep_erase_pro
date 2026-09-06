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

Pour des instructions visuelles complètes et des démonstrations du plugin, n'hésitez pas à consulter les tutoriels vidéo sur la chaîne YouTube **Miguel Pineau**.
