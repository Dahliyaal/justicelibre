#!/usr/bin/env python3
"""Pull tous les services CENTRAUX de api-lannuaire.service-public.fr
qui ont au moins une adresse mail publiée. Ce sont les services absents
du dump DILA téléchargeable (qui ne contient que les services locaux).

Cible : DACS, DGCCRF, cabinets ministériels, sous-directions, bureaux
centraux, etc. Environ 3 400 fiches.

Sortie : api_annuaire.csv, ingéré par build_annuaire.py avec source 'api'.
"""
import csv, json, os, time
from pathlib import Path
import httpx  # noqa

OUT = Path(os.environ.get("ANNUAIRE_SRC", "/home/dahl/annuaire")) / "api_annuaire.csv"
# Endpoint /exports/json : renvoie TOUT le dataset en une requête (~16 MB
# pour 67k fiches en ~5s). Bien plus rapide et fiable que /records paginé
# qui a une limite d'offset à 10 000 sur Opendatasoft.
URL = "https://api-lannuaire.service-public.fr/api/explore/v2.1/catalog/datasets/api-lannuaire-administration/exports/json"
WHERE = "adresse_courriel is not null"
FIELDS = "id,nom,adresse_courriel,telephone,site_internet,type_organisme,hierarchie,mission,sigle,adresse,pivot"

def flat_field(v, sep=" ; "):
    """Normalise un champ API en string lisible. Attention : l'API renvoie
    parfois les champs complexes (téléphone, adresse, site) comme des
    STRINGS JSON pré-sérialisées, pas comme objets Python. On tente donc
    un json.loads si la chaîne commence par [ ou {, puis on aplatit."""
    if v is None or v == "": return ""
    # String qui semble être du JSON serialisé
    if isinstance(v, str):
        s = v.strip()
        if s.startswith(('[', '{')):
            try: v = json.loads(s)
            except Exception: return v
        else:
            return v
    if isinstance(v, dict):
        v = [v]
    if isinstance(v, list):
        parts = []
        for x in v:
            if isinstance(x, str):
                if x.strip(): parts.append(x.strip())
            elif isinstance(x, dict):
                # Cas adresse structurée
                if any(k in x for k in ("numero_voie", "code_postal", "nom_commune", "complement1")):
                    addr = []
                    for k in ("complement1", "complement2", "numero_voie", "service_distribution"):
                        val = (x.get(k) or "").strip()
                        if val: addr.append(val)
                    ville = " ".join(filter(None, [(x.get("code_postal") or "").strip(),
                                                    (x.get("nom_commune") or "").strip()]))
                    if ville: addr.append(ville)
                    if addr: parts.append(", ".join(addr))
                else:
                    # Générique : valeur (téléphone/site) > libelle > nom > adresse_courriel
                    for k in ("valeur", "value", "libelle", "nom", "adresse_courriel"):
                        val = x.get(k)
                        if val and str(val).strip():
                            parts.append(str(val).strip())
                            break
        return sep.join(parts)
    return str(v)

def pivot_kind(p):
    """Extrait le type de service local depuis le champ pivot (list-of-dict
    ou JSON string). Ex : 'mairie', 'police_municipale', 'tribunal_judiciaire'.
    Renvoie 'chapeau' si pivot est vide (fiche autonome, non rattachée)."""
    if not p: return "chapeau"
    if isinstance(p, str):
        try: p = json.loads(p)
        except Exception: return "autre"
    if isinstance(p, list) and p and isinstance(p[0], dict):
        return p[0].get("type_service_local") or "autre"
    return "autre"

def main():
    print(f"[api] fetch /exports/json (67k fiches, ~5s)...")
    t0 = time.time()
    with httpx.Client(timeout=180) as c:
        r = c.get(URL, params={"where": WHERE, "select": FIELDS})
        r.raise_for_status()
    data = r.json()
    print(f"[api] {len(data)} fiches reçues en {time.time()-t0:.1f}s ({len(r.content)/1e6:.1f} MB)")
    rows = []
    for x in data:
        mails = x.get("adresse_courriel") or []
        if isinstance(mails, list): mails = [m for m in mails if m]
        elif isinstance(mails, str): mails = [mails]
        if not mails: continue
        rows.append({
            "id": x.get("id") or "",
            "nom": x.get("nom") or "",
            "sigle": x.get("sigle") or "",
            "mails": " ; ".join(mails),
            "telephone": flat_field(x.get("telephone")),
            "site_internet": flat_field(x.get("site_internet")),
            "type_organisme": x.get("type_organisme") or "",
            "hierarchie": flat_field(x.get("hierarchie"), sep=" > "),
            "adresse": flat_field(x.get("adresse"), sep=" | "),
            "pivot_kind": pivot_kind(x.get("pivot")),
        })
    print(f"[api] écrit {len(rows)} fiches dans {OUT}")
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(rows)

if __name__ == "__main__":
    main()
