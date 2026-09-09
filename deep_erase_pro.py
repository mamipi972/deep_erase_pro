#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gi
gi.require_version('Gimp', '3.0')
gi.require_version('GimpUi', '3.0')
from gi.repository import Gimp, GimpUi, GLib, Gio, Gegl, GObject

import os
import sys
import subprocess
import tempfile
import time
import glob
import shutil

PROCEDURE_NAME = "deep-erase-pro"
PLUGIN_ID = "deep_erase_pro"
SHARED_DIR_NAME = "ai_suite_shared"
EXPECTED_HASH = "300BE8A5C9A5F060FA35B144921FBF15C2F4D503CAD65AEE192B3365A883AAB4"

REQUIRED_PACKAGES = {
    "numpy>=1.24,<3": "numpy",
    "opencv-python-headless>=4.8,<6": "cv2",
    "torch>=2.0,<3": "torch"
}

PROBE_TIMEOUT = 5
INSTALL_TIMEOUT = 900
INFERENCE_TIMEOUT = 900
SELECTION_COVERAGE_WARN = 0.97
WORKER_MEMORY_LIMIT_BYTES = 4 * 1024 * 1024 * 1024

def get_shared_directories():
    base_shared_path = os.path.join(Gimp.directory(), SHARED_DIR_NAME)
    venv_path = os.path.join(base_shared_path, "venv")
    models_path = os.path.join(base_shared_path, "models")
    os.makedirs(venv_path, exist_ok=True)
    os.makedirs(models_path, exist_ok=True)
    return venv_path, models_path

def get_model_path(model_filename):
    _, models_path = get_shared_directories()
    shared_model = os.path.join(models_path, model_filename)
    if os.path.isfile(shared_model):
        return shared_model
    plugin_dir = os.path.dirname(os.path.realpath(__file__))
    local_model = os.path.join(plugin_dir, model_filename)
    if os.path.isfile(local_model):
        return local_model
    return shared_model

def env_clean():
    clean_env = os.environ.copy()
    clean_env.pop('PYTHONPATH', None)
    clean_env.pop('PYTHONHOME', None)
    if 'PATH' in clean_env:
        paths = clean_env['PATH'].split(os.pathsep)
        clean_env['PATH'] = os.pathsep.join([p for p in paths if 'gimp' not in p.lower()])
    return clean_env

def _popen_kwargs():
    return {'creationflags': 0x08000000} if os.name == 'nt' else {}

def test_python_executable(path, timeout=PROBE_TIMEOUT):
    if not path or not os.path.isfile(path): 
        return False
    gimp_dir = os.path.dirname(sys.executable).lower()
    if gimp_dir in os.path.abspath(path).lower(): 
        return False
    try:
        res = subprocess.run([path, '-c', 'import sys; sys.exit(0)'], env=env_clean(), capture_output=True, timeout=timeout, **_popen_kwargs())
        return res.returncode == 0
    except Exception: 
        return False

def test_python_environment(path, timeout=PROBE_TIMEOUT):
    """Vérifie non seulement que l'interpréteur démarre, mais aussi que les
    paquets requis (numpy, cv2, torch) y sont réellement importables.
    Retourne (bool_ok, message_diagnostic)."""
    if not test_python_executable(path, timeout=timeout):
        return False, "Interpréteur Python introuvable ou non exécutable."
    modules = list(REQUIRED_PACKAGES.values())
    import_stmt = "; ".join(f"import {m}" for m in modules)
    try:
        res = subprocess.run(
            [path, '-c', import_stmt],
            env=env_clean(), capture_output=True, text=True,
            timeout=timeout * 4, **_popen_kwargs()
        )
        if res.returncode != 0:
            detail = (res.stderr or res.stdout or "").strip()
            return False, detail[-800:] if detail else "Échec d'import inconnu."
        return True, ""
    except Exception as e:
        return False, str(e)

def find_system_python():
    candidates = set()
    env = env_clean()
    kwargs = _popen_kwargs()

    for cmd in ['python3', 'python', 'py']:
        p = shutil.which(cmd, path=env.get('PATH'))
        if p: candidates.add(os.path.abspath(p))

    cmds = ['python3', 'python'] if os.name != 'nt' else ['py', 'python', 'python3']
    for cmd in cmds:
        try:
            res = subprocess.run([cmd, '-c', 'import sys; print(sys.executable)'], env=env, capture_output=True, text=True, timeout=PROBE_TIMEOUT, **kwargs)
            if res.returncode == 0: candidates.add(os.path.abspath(res.stdout.strip()))
        except Exception: pass
    
    if os.name == 'nt':
        try:
            res = subprocess.run(['py', '-0p'], env=env, capture_output=True, text=True, timeout=PROBE_TIMEOUT, **kwargs)
            import re
            for match in re.findall(r"\s+\-\s+\S+\s+(.+)", res.stdout): 
                candidates.add(os.path.abspath(match.strip()))
        except Exception: pass
        
        local_appdata = os.environ.get('LOCALAPPDATA', '')
        if local_appdata:
            for p in glob.glob(os.path.join(local_appdata, 'Programs', 'Python', 'Python*', 'python.exe')):
                candidates.add(os.path.abspath(p))
            winapps = os.path.join(local_appdata, 'Microsoft', 'WindowsApps', 'python.exe')
            if os.path.isfile(winapps): candidates.add(os.path.abspath(winapps))
            
        for pf in [os.environ.get('PROGRAMFILES', ''), os.environ.get('PROGRAMFILES(X86)', '')]:
            if pf:
                for p in glob.glob(os.path.join(pf, 'Python*', 'python.exe')):
                    candidates.add(os.path.abspath(p))
                    
    if os.name != 'nt':
        home = os.path.expanduser("~")
        plugin_dir = os.path.dirname(os.path.realpath(__file__))
        search_dirs = [
            os.path.join(home, '.venvs'),
            os.path.join(home, '.virtualenvs'),
            os.path.join(home, '.venv'),
            os.path.join(home, 'venv'),
            plugin_dir
        ]
        for base_dir in search_dirs:
            if os.path.isdir(base_dir):
                try:
                    for d in os.listdir(base_dir):
                        p = os.path.join(base_dir, d, 'bin', 'python3')
                        if os.path.isfile(p): candidates.add(os.path.abspath(p))
                        p2 = os.path.join(base_dir, 'bin', 'python3')
                        if os.path.isfile(p2): candidates.add(os.path.abspath(p2))
                except Exception: pass

    valid_candidates = []
    for cand in candidates:
        clean_cand = cand.strip('"\'')
        if test_python_executable(clean_cand):
            valid_candidates.append(clean_cand)
            
    if valid_candidates:
        valid_candidates.sort(key=lambda x: 'WindowsApps' in x)
        return valid_candidates[0]
        
    return None

def setup_venv(system_python):
    venv_dir, _ = get_shared_directories()
    venv_python = os.path.join(venv_dir, 'Scripts', 'python.exe') if os.name == 'nt' else os.path.join(venv_dir, 'bin', 'python3')
    env = env_clean()
    kwargs = _popen_kwargs()

    if not os.path.isfile(venv_python):
        Gimp.progress_set_text("Création de l'environnement virtuel partagé...")
        try:
            process = subprocess.Popen([system_python, '-m', 'venv', venv_dir], env=env, **kwargs)
            while process.poll() is None:
                Gimp.progress_pulse()
                time.sleep(0.2)
            if process.returncode != 0 or not os.path.isfile(venv_python):
                raise RuntimeError("Échec de création du venv.\nSur Linux/Debian : exécutez 'sudo apt install python3-venv'")
        except Exception as e:
            raise RuntimeError(f"Erreur de création venv : {str(e)}")

    def _run_popen_capture(cmd, timeout_s, progress_text):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as log_f:
            log_path = log_f.name
        try:
            with open(log_path, 'w') as log_f:
                Gimp.progress_set_text(progress_text)
                process = subprocess.Popen(cmd, env=env, stdout=log_f, stderr=subprocess.STDOUT, **kwargs)
                start_time = time.time()
                while process.poll() is None:
                    Gimp.progress_pulse()
                    time.sleep(0.2)
                    if time.time() - start_time > timeout_s:
                        process.kill()
                        process.wait()
                        raise RuntimeError(f"Timeout ({timeout_s // 60} min) dépassé.")
            with open(log_path, 'r', errors='replace') as log_f:
                output = log_f.read()
            return process.returncode, output
        finally:
            try: os.remove(log_path)
            except OSError: pass

    try: 
        _run_popen_capture([venv_python, '-m', 'pip', 'install', '--upgrade', 'pip'], 120, "Mise à jour de pip...")
    except Exception: pass

    for package_spec, module_name in REQUIRED_PACKAGES.items():
        try: 
            subprocess.run([venv_python, '-c', f'import {module_name}'], env=env, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            # Sécurité : utilisation de --only-binary=:all:
            install_rc, install_out = _run_popen_capture(
                [venv_python, '-m', 'pip', 'install', '--no-input', '--only-binary=:all:', package_spec],
                INSTALL_TIMEOUT,
                f"Installation de {module_name} (Mutualisation IA)..."
            )
            if install_rc != 0:
                raise RuntimeError(f"Échec critique de l'installation de {module_name} :\n{install_out[-2000:]}")
                
    return venv_python

def _posix_memory_limit_preexec(limit_bytes):
    def _limiter():
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
        except Exception: pass
    return _limiter

def _assign_windows_job_memory_limit(process, limit_bytes):
    if os.name != 'nt': return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        job = kernel32.CreateJobObjectW(None, None)
        if not job: return
        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", ctypes.c_byte * 48),
                        ("IoInfo", ctypes.c_byte * 48),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.ProcessMemoryLimit = limit_bytes
        kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        h_process = kernel32.OpenProcess(0x1F0FFF, False, process.pid)
        if h_process: kernel32.AssignProcessToJobObject(job, h_process)
    except Exception: pass

def execute_worker(python_executable, image_path, mask_path, out_path, pt_model_path):
    worker_code = f"""# -*- coding: utf-8 -*-
import sys
import os
import hashlib

EXPECTED_HASH = "{EXPECTED_HASH}"

try:
    import numpy as np
    import cv2
    import torch
except ImportError as e:
    print(f"[CACHE_INVALIDATION_REQUIRED] Erreur d'import : {{e}}")
    sys.exit(1)

def verify_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        # Optimisation : lecture par blocs de 1 Mo (1024 * 1024)
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    if h.hexdigest().lower() != EXPECTED_HASH.lower():
        print("[PT_ERROR] Alerte de sécurité : Fichier lama.pt falsifié ou hash incorrect.", file=sys.stdout)
        sys.exit(1)

def process_image(img_in, mask_in, img_out, model_path):
    raw = cv2.imread(img_in, cv2.IMREAD_UNCHANGED)
    mask = cv2.imread(mask_in, cv2.IMREAD_GRAYSCALE)

    if raw is None or mask is None: sys.exit(1)

    has_alpha = (raw.ndim == 3 and raw.shape[2] == 4)
    if has_alpha:
        alpha_channel = raw[:, :, 3]
        img = raw[:, :, :3]
    else:
        alpha_channel = None
        img = raw if raw.ndim == 3 else cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)

    if img.shape[:2] != mask.shape[:2]:
        mask = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)

    _, binary_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    if cv2.countNonZero(binary_mask) == 0: sys.exit(1)

    # 1. Optimisation : Recadrage sur la zone sélectionnée (Bounding Box)
    x, y, w_box, h_box = cv2.boundingRect(binary_mask)
    if w_box == 0 or h_box == 0: sys.exit(1)
    
    margin_x, margin_y = max(32, int(w_box * 0.2)), max(32, int(h_box * 0.2))
    img_h, img_w = img.shape[:2]
    
    x1 = max(0, x - margin_x)
    y1 = max(0, y - margin_y)
    x2 = min(img_w, x + w_box + margin_x)
    y2 = min(img_h, y + h_box + margin_y)

    img_crop = img[y1:y2, x1:x2]
    mask_crop = binary_mask[y1:y2, x1:x2]

    try:
        verify_hash(model_path)
        
        # 2. Support étendu : CUDA, Apple MPS et CPU
        if torch.cuda.is_available():
            device = torch.device('cuda')
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            device = torch.device('mps')
        else:
            device = torch.device('cpu')
        
        # 3. Patch local et temporaire pour torche.load
        _original_load = torch.load
        def _patched_load(*args, **kwargs):
            kwargs['weights_only'] = False
            return _original_load(*args, **kwargs)
            
        try:
            torch.load = _patched_load
            model = torch.jit.load(model_path, map_location=device)
        finally:
            # Restauration immédiate
            torch.load = _original_load
            
        model.eval()

        # Préparation des tenseurs sur l'image recadrée (économie mémoire massive)
        crop_h, crop_w = img_crop.shape[:2]
        pad_size = 32
        pad_h_crop = (pad_size - crop_h % pad_size) % pad_size
        pad_w_crop = (pad_size - crop_w % pad_size) % pad_size
        
        work_img = cv2.copyMakeBorder(img_crop, 0, pad_h_crop, 0, pad_w_crop, cv2.BORDER_REFLECT)
        work_mask = cv2.copyMakeBorder(mask_crop, 0, pad_h_crop, 0, pad_w_crop, cv2.BORDER_REFLECT)
        work_img_rgb = cv2.cvtColor(work_img, cv2.COLOR_BGR2RGB)

        img_tensor = torch.from_numpy(work_img_rgb).float().permute(2, 0, 1).unsqueeze(0) / 255.0
        mask_tensor = torch.from_numpy(work_mask).float().unsqueeze(0).unsqueeze(0) / 255.0
        
        img_tensor = img_tensor.to(device)
        mask_tensor = mask_tensor.to(device)

        with torch.no_grad():
            output_tensor = model(img_tensor, mask_tensor)
        
        output_img = output_tensor.squeeze(0).permute(1, 2, 0).cpu().numpy()
        if np.max(output_img) <= 1.0: output_img = output_img * 255.0
        output_img = np.clip(output_img, 0, 255).astype(np.uint8)
        
        result_ai_crop = cv2.cvtColor(output_img, cv2.COLOR_RGB2BGR)
        result_ai_crop = result_ai_crop[:crop_h, :crop_w] if (pad_h_crop > 0 or pad_w_crop > 0) else result_ai_crop

        # Réintégration du résultat dans l'image d'origine
        result = img.copy()
        result[y1:y2, x1:x2] = result_ai_crop

        print("[PT_SUCCESS]")
    except Exception as e:
        result = None
        print(f"[PT_ERROR] {{str(e)}}", file=sys.stdout)

    if result is None:
        result = cv2.inpaint(img, binary_mask, 15, cv2.INPAINT_NS)

    if has_alpha:
        result = cv2.cvtColor(result, cv2.COLOR_BGR2BGRA)
        result[:, :, 3] = alpha_channel

    cv2.imwrite(img_out, result)

if __name__ == "__main__":
    process_image(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
"""
    fd, worker_path = tempfile.mkstemp(prefix=f"{PLUGIN_ID}_worker_", suffix=".py")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f: f.write(worker_code)
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as log_f: log_path = log_f.name
        try:
            popen_kwargs = dict(_popen_kwargs())
            if os.name != 'nt': popen_kwargs['preexec_fn'] = _posix_memory_limit_preexec(WORKER_MEMORY_LIMIT_BYTES)
            
            process = subprocess.Popen([python_executable, worker_path, image_path, mask_path, out_path, pt_model_path], 
                                       env=env_clean(), stdout=open(log_path, 'w'), stderr=subprocess.STDOUT, 
                                       text=True, encoding="utf-8", errors="replace", **popen_kwargs)
            
            _assign_windows_job_memory_limit(process, WORKER_MEMORY_LIMIT_BYTES)
            
            start_time = time.time()
            while process.poll() is None:
                Gimp.progress_pulse()
                time.sleep(0.2)
                if time.time() - start_time > INFERENCE_TIMEOUT:
                    process.kill()
                    process.wait()
                    return False, "Timeout de l'IA dépassé.", False, ""
            
            with open(log_path, 'r', errors='replace') as log_f: output = log_f.read()
        finally:
            try: os.remove(log_path)
            except OSError: pass
    finally:
        if os.path.isfile(worker_path):
            try: os.remove(worker_path)
            except OSError: pass

    if "[CACHE_INVALIDATION_REQUIRED]" in output:
        detail_line = next((l for l in output.splitlines() if "[CACHE_INVALIDATION_REQUIRED]" in l), "").strip()
        return False, f"Cache corrompu (environnement Python incomplet) : {detail_line}", False, ""
    is_ai_success = "[PT_SUCCESS]" in output
    pt_error = next((line.replace("[PT_ERROR]", "").strip() for line in output.splitlines() if line.startswith("[PT_ERROR]")), "")
    return is_ai_success, output, is_ai_success, pt_error

def safe_export(image, drawables, gio_file):
    try: Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, gio_file); return
    except TypeError: pass
    try: Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, drawables, gio_file); return
    except TypeError: pass
    try: Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, gio_file, drawables); return
    except TypeError: pass
    try: Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, drawables[0], gio_file); return
    except TypeError as e: raise RuntimeError(f"Échec d'export: {str(e)}")

class DeepEraseProPlugin(Gimp.PlugIn):
    def do_query_procedures(self): 
        return [PROCEDURE_NAME]
        
    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, self.run, None)
        procedure.set_image_types("RGB*, GRAY*")
        procedure.set_menu_label("Deep Erase Pro...")
        procedure.add_menu_path("<Image>/Filters/Enhance")
        return procedure

    def run(self, procedure, run_mode, image, drawables, config, run_data):
        temp_files = []
        try:
            if len(drawables) != 1:
                Gimp.message("Veuillez sélectionner un seul calque actif.")
                return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, GLib.Error())

            try: is_empty = Gimp.Selection.is_empty(image)
            except AttributeError: is_empty = image.get_selection().is_empty()
            if is_empty:
                Gimp.message("Aucune sélection détectée. Veuillez utiliser l'outil de sélection autour de l'élément à effacer.")
                return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, GLib.Error())

            GimpUi.init(PLUGIN_ID)
            if run_mode == Gimp.RunMode.INTERACTIVE:
                dialog = GimpUi.ProcedureDialog.new(procedure, config)
                dialog.fill(None)
                if not dialog.run():
                    dialog.destroy()
                    return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())
                dialog.destroy()

            target_model_path = get_model_path("lama.pt")
            if not os.path.isfile(target_model_path):
                _, shared_models_dir = get_shared_directories()
                Gimp.message(
                    f"Le fichier modèle 'lama.pt' est introuvable.\n\n"
                    f"Pour économiser l'espace disque, les modèles IA sont mutualisés. "
                    f"Veuillez déposer le fichier 'lama.pt' exactement dans ce dossier :\n\n"
                    f"{shared_models_dir}"
                )
                return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

            Gimp.progress_init("Deep Erase Pro Initialisation...")
            image.undo_group_start()
            Gimp.context_push()
            saved_sel = None
            temp_mask_layer = None
            
            base_shared_path = os.path.join(Gimp.directory(), SHARED_DIR_NAME)
            cache_path = os.path.join(base_shared_path, "ai_suite_python_cache.txt")
            valid_python = None

            try:
                try: bounds_result = Gimp.Selection.bounds(image)
                except AttributeError: bounds_result = image.get_selection().bounds(image)
                bounds_result = tuple(bounds_result)
                if len(bounds_result) == 6: _, non_empty, x1, y1, x2, y2 = bounds_result
                elif len(bounds_result) == 5: non_empty, x1, y1, x2, y2 = bounds_result
                w, h = max(0, x2 - x1), max(0, y2 - y1)
                img_area = image.get_width() * image.get_height()
                if img_area > 0 and (w * h / img_area) >= SELECTION_COVERAGE_WARN:
                    Gimp.message("Attention : la sélection couvre la quasi-totalité de l'image. Le résultat sera en grande partie généré par l'IA plutôt que reconstruit à partir du contexte local.")

                venv_dir, _ = get_shared_directories()
                shared_venv_python = os.path.join(venv_dir, 'Scripts', 'python.exe') if os.name == 'nt' else os.path.join(venv_dir, 'bin', 'python3')
                env_ok, env_diag = test_python_environment(shared_venv_python)
                if env_ok:
                    valid_python = shared_venv_python
                    with open(cache_path, 'w') as f: f.write(valid_python)

                if not valid_python and os.path.isfile(cache_path):
                    with open(cache_path, 'r') as f:
                        cached_env = f.read().strip()
                        env_ok, env_diag = test_python_environment(cached_env)
                        if env_ok: valid_python = cached_env

                if not valid_python:
                    # L'environnement partagé existe peut-être déjà mais avec des paquets
                    # manquants/corrompus (env_diag contient le détail) : setup_venv()
                    # réutilise ce même dossier et (ré)installe ce qui manque, au lieu
                    # de se contenter de vérifier que l'exécutable démarre.
                    sys_python = find_system_python()
                    if not sys_python: raise RuntimeError("Aucun Python système trouvé.")
                    valid_python = setup_venv(sys_python)
                    with open(cache_path, 'w') as f: f.write(valid_python)

                # Sécurité : Création d'un dossier temporaire dédié au lieu d'utiliser directement le root du tmp
                work_dir = tempfile.mkdtemp(prefix=f"{PLUGIN_ID}_")
                temp_files.append(work_dir)
                
                path_in = os.path.join(work_dir, "in.png")
                path_mask = os.path.join(work_dir, "mask.png")
                path_out = os.path.join(work_dir, "out.png")

                file_in, file_mask, file_out = Gio.File.new_for_path(path_in), Gio.File.new_for_path(path_mask), Gio.File.new_for_path(path_out)

                try: saved_sel = Gimp.Selection.save(image)
                except AttributeError: saved_sel = image.selection_save()
                try: Gimp.Selection.none(image)
                except AttributeError: image.select_none()
                safe_export(image, drawables, file_in)

                layer_type = Gimp.ImageType.RGBA_IMAGE if image.get_base_type() == Gimp.ImageBaseType.RGB else Gimp.ImageType.GRAYA_IMAGE
                temp_mask_layer = Gimp.Layer.new(image, "temp_mask", image.get_width(), image.get_height(), layer_type, 100.0, Gimp.LayerMode.NORMAL)
                try: image.insert_layer(temp_mask_layer, None, 0)
                except AttributeError: image.add_layer(temp_mask_layer, 0)

                Gimp.context_set_background(Gegl.Color.new("black"))
                temp_mask_layer.edit_fill(Gimp.FillType.BACKGROUND)
                try: Gimp.Selection.load(saved_sel)
                except AttributeError: image.select_item(Gimp.ChannelOps.REPLACE, saved_sel)
                Gimp.context_set_background(Gegl.Color.new("white"))
                temp_mask_layer.edit_fill(Gimp.FillType.BACKGROUND)
                try: Gimp.Selection.none(image)
                except AttributeError: image.select_none()
                safe_export(image, [temp_mask_layer], file_mask)
            finally:
                if temp_mask_layer and image.is_valid(): image.remove_layer(temp_mask_layer)
                if saved_sel and image.is_valid():
                    try: image.remove_channel(saved_sel)
                    except Exception: pass
            
            Gimp.progress_set_text("Inpainting en cours...")
            success, err, is_ai, pt_error = execute_worker(valid_python, path_in, path_mask, path_out, target_model_path)

            if not success:
                if "Cache corrompu" in err and os.path.isfile(cache_path): os.remove(cache_path)
                raise RuntimeError(err)

            if not is_ai:
                Gimp.message(f"Le traitement IA a échoué. Repli sur OpenCV déclenché.\n\nErreur IA : {pt_error}")

            if os.path.isfile(path_out):
                try:
                    if hasattr(Gimp, 'file_load_layers'):
                        new_layers = Gimp.file_load_layers(Gimp.RunMode.NONINTERACTIVE, image, file_out)
                        for layer in new_layers:
                            if hasattr(image, 'insert_layer'): image.insert_layer(layer, None, 0)
                            else: image.add_layer(layer, 0)
                            layer.set_name("Deep Erase Pro (PyTorch)" if is_ai else "Resultat (OpenCV)")
                except Exception as e: raise RuntimeError(f"Échec rechargement : {str(e)}")

            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

        except Exception as e:
            Gimp.message(f"Erreur Globale Deep Erase : {str(e)}")
            return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error())

        finally:
            # Sécurité : Suppression propre du dossier de travail et de son contenu
            for p in temp_files:
                if p and os.path.exists(p):
                    try:
                        if os.path.isdir(p):
                            shutil.rmtree(p, ignore_errors=True)
                        else:
                            os.remove(p)
                    except OSError: pass
            try:
                Gimp.context_pop()
                image.undo_group_end()
                Gimp.progress_end()
            except Exception:
                pass

if __name__ == "__main__":
    Gimp.main(DeepEraseProPlugin.__gtype__, sys.argv)
