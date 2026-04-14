Cisco Provisioning Tool - Edition USB Portable
==============================================

Cette application est totalement portable :
- Aucune installation requise
- Fonctionne depuis une clé USB sur Windows et Linux
- Stocke les fichiers runtime à côté de l'exécutable

Comportement runtime portable
-----------------------------
- L'application utilise toujours des chemins dynamiques basés sur l'emplacement de lancement.
- Au démarrage, elle crée automatiquement :
  - data/
  - logs/
- Les logs sont écrits dans :
  - logs/app.log
- Si la configuration runtime est absente, l'application crée :
  - data/settings.json

Exécution en développement (Python)
-----------------------------------
- Windows/Linux :
  - python src/main.py
- Options facultatives :
  - --portable
  - --debug

Compilation exécutable - Windows
--------------------------------
1) Ouvrir un terminal à la racine du projet
2) Exécuter :
   scripts\build.bat
3) Sortie :
   dist\Provisioner.exe

Exécution côté client Windows
-----------------------------
1) Copier `Provisioner.exe` dans n'importe quel dossier (ou clé USB)
2) Double-cliquer sur `Provisioner.exe`
3) L'application créera automatiquement `data/` et `logs/`

Compilation exécutable - Linux
------------------------------
1) Ouvrir un terminal à la racine du projet
2) Exécuter :
   chmod +x scripts/build.sh
   ./scripts/build.sh
3) Sortie :
   dist/provisioner

Exécution côté client Linux
---------------------------
1) Copier `provisioner` dans n'importe quel dossier (ou clé USB)
2) Exécuter :
   chmod +x provisioner
   ./provisioner
3) L'application créera automatiquement `data/` et `logs/`

Créer les packages de release
-----------------------------
Dossier release Windows + zip :
- scripts\make_release.bat
- Sortie :
  - release\Windows\
  - release\Provisioner-Windows.zip

Dossier release Linux + tar.gz :
- chmod +x scripts/make_release.sh
- ./scripts/make_release.sh
- Sortie :
  - release/Linux/
  - release/provisioner-linux.tar.gz

Notes importantes
-----------------
- Aucun chemin absolu n'est utilisé pour le stockage runtime.
- Aucun privilège administrateur n'est requis pour l'exécution normale.
- Compiler chaque OS sur le même OS :
  - build Windows sur Windows
  - build Linux sur Linux


Cisco Provisioning Tool - Portable USB Edition
==============================================

This application is fully portable:
- No installation required
- Runs from a USB drive on Windows and Linux
- Stores runtime files next to the executable

Portable runtime behavior
-------------------------
- The app always uses dynamic runtime paths based on its launch location.
- On startup it auto-creates:
  - data/
  - logs/
- Logs are written to:
  - logs/app.log
- If runtime config is missing, the app creates:
  - data/settings.json

Run in development (Python)
---------------------------
- Windows/Linux:
  - python src/main.py
- Optional flags:
  - --portable
  - --debug

Build executable - Windows
--------------------------
1) Open terminal in project root
2) Run:
   scripts\build.bat
3) Output:
   dist\Provisioner.exe

Run on Windows client
---------------------
1) Copy `Provisioner.exe` to any folder (or USB)
2) Double-click `Provisioner.exe`
3) The app will create `data/` and `logs/` automatically

Build executable - Linux
------------------------
1) Open terminal in project root
2) Run:
   chmod +x scripts/build.sh
   ./scripts/build.sh
3) Output:
   dist/provisioner

Run on Linux client
-------------------
1) Copy `provisioner` to any folder (or USB)
2) Run:
   chmod +x provisioner
   ./provisioner
3) The app will create `data/` and `logs/` automatically

Create release packages
-----------------------
Windows release folder + zip:
- scripts\make_release.bat
- Output:
  - release\Windows\
  - release\Provisioner-Windows.zip

Linux release folder + tar.gz:
- chmod +x scripts/make_release.sh
- ./scripts/make_release.sh
- Output:
  - release/Linux/
  - release/provisioner-linux.tar.gz

Important notes
---------------
- No absolute paths are used for runtime storage.
- No admin privileges are required for normal app execution.
- Build for each target OS on that same OS:
  - Windows build on Windows
  - Linux build on Linux

