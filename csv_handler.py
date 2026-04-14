"""Gestion import CSV de telephones."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Tuple


MAC_REGEX = re.compile(r"^[0-9A-F]{12}$")


def normalize_mac(value: str) -> str:
    """Normalise MAC en 12 caracteres hexadecimaux (sans separateur)."""
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", value or "").upper()
    return cleaned


def format_mac_display(value: str) -> str:
    """Formate la MAC pour l'affichage utilisateur: AA:BB:CC:DD:EE:FF."""
    normalized = normalize_mac(value)[:12]
    parts = [normalized[i : i + 2] for i in range(0, len(normalized), 2)]
    return ":".join(parts)


def is_valid_mac(value: str) -> bool:
    """Valide le format MAC."""
    return bool(MAC_REGEX.fullmatch(normalize_mac(value)))


def load_phones_from_csv(file_path: str | Path) -> Tuple[List[Dict[str, str]], List[str]]:
    """
    Lit un CSV au format: mac,ext,password.
    Retourne (phones_valides, erreurs).
    """
    phones: List[Dict[str, str]] = []
    errors: List[str] = []

    with Path(file_path).open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        expected = {"mac", "ext", "password"}
        if not reader.fieldnames or not expected.issubset({h.strip().lower() for h in reader.fieldnames}):
            return [], ["Entetes CSV invalides. Colonnes attendues: mac,ext,password"]

        for idx, row in enumerate(reader, start=2):
            lowered_row = {str(k).strip().lower(): (v or "") for k, v in row.items()}
            mac = normalize_mac(str(lowered_row.get("mac", "")).strip())
            ext = str(lowered_row.get("ext", "")).strip()
            password = str(lowered_row.get("password", "")).strip()

            if not MAC_REGEX.fullmatch(mac):
                errors.append(f"Ligne {idx}: MAC invalide ({lowered_row.get('mac', '')}).")
                continue
            if not ext:
                errors.append(f"Ligne {idx}: extension vide.")
                continue
            if not password:
                errors.append(f"Ligne {idx}: mot de passe vide.")
                continue

            phones.append({"mac": mac, "ext": ext, "password": password})

    return phones, errors
