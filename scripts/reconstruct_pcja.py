#!/usr/bin/env python3
"""
Reconstruction du Plan de Classement de la Jurisprudence Administrative (PCJA)
à partir des balises ANALYSES présentes dans les sommaires JADE.

Format observé dans `sommaire` :
    CODE LABEL_N1. - LABEL_N2. - LABEL_N3. - ... - LABEL_DEEP - DETAILS [RJ1]. zCODEz <dev>

Le code (e.g. "39-02-005") encode la hiérarchie : "39" / "39-02" / "39-02-005".
Les labels sont concaténés avec ". - ".

Sortie : JSON {code: {label, parent, depth, freq}} + arbre SKOS-RDF/XML.
"""

import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "/opt/justicelibre/dila/jade.db"
OUT_DIR = Path(sys.argv[2] if len(sys.argv) > 2 else "/opt/justicelibre/thesaurus")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Code PCJA : suite de groupes de chiffres séparés par tirets, e.g. "39-02-005" ou "54-07-01-04-01-02"
# Au début d'un sommaire, suivi d'un espace puis d'une chaîne en majuscules
HEADER_RE = re.compile(
    r'^\s*(\d{1,3}(?:-\d{1,3}){0,7})\s+'
    r"([A-ZÉÈÀÂÊÎÔÛÇÆŒÆ0-9][A-ZÉÈÀÂÊÎÔÛÇÆŒÆ0-9\s\'\.\-,()«»\"]{5,}?)"
    r"(?=\s+[a-zéèàâêîôûçæ]|\s+z\d|$)"
)
# Marqueur de fin alternatif : zCODEz (rare)
END_RE = re.compile(r'z(\d{1,3}(?:-\d{1,3}){0,7})z')


def split_labels(raw: str) -> list[str]:
    """Découpe la chaîne hiérarchique en liste de labels."""
    # D'abord ". -" (séparateur principal), puis " -" comme fallback secondaire
    # mais attention : certains labels contiennent des virgules et tirets internes
    # Pattern le plus fiable : "LABEL1. - LABEL2. - LABEL3 - DETAILS_QUI_PEUT_AVOIR_DES_TIRETS"
    # On split sur ". -" qui est plus structurant que " -"
    parts = re.split(r'\s*\.\s+-\s+', raw)
    # La dernière partie peut contenir le détail "casuistique" séparé par " - "
    # On le coupe pour ne garder que le label de plus bas niveau
    if parts:
        # Sur la dernière partie, on coupe au premier " - " (qui sépare label et casuistique)
        last = parts[-1]
        sub = re.split(r'\s+-\s+', last, maxsplit=1)
        if len(sub) >= 1:
            parts[-1] = sub[0]
    out = []
    for p in parts:
        p = p.strip().rstrip('.').strip()
        # Vire les codes RJ et notes parenthésées
        p = re.sub(r'\s*\[RJ\d+\]', '', p)
        # Vire les ouvertures parenthèses non fermées
        p = re.sub(r'\s*\([^)]*$', '', p)
        if p and len(p) >= 3:
            out.append(p)
    return out


def extract_blocks(sommaire: str) -> list[tuple[str, list[str]]]:
    """Extrait le code PCJA + labels hiérarchiques depuis le début du sommaire."""
    if not sommaire:
        return []
    blocks = []
    # 1. Tente le format avec marqueur zCODEz d'abord (plus fiable)
    end_markers = list(END_RE.finditer(sommaire))
    for m in end_markers:
        code_end = m.group(1)
        end_pos = m.start()
        code_pattern = re.compile(rf'(?:^|\s){re.escape(code_end)}\s+')
        starts = [s for s in code_pattern.finditer(sommaire[:end_pos])]
        if not starts:
            continue
        start_pos = starts[-1].end()
        raw_block = sommaire[start_pos:end_pos].strip()
        labels = split_labels(raw_block)
        if labels:
            blocks.append((code_end, labels))

    if blocks:
        return blocks

    # 2. Fallback : header au début du sommaire (cas dominant ~99%)
    m = HEADER_RE.match(sommaire)
    if m:
        code = m.group(1)
        raw = m.group(2).strip()
        labels = split_labels(raw)
        if labels:
            blocks.append((code, labels))
    return blocks


def code_ancestors(code: str) -> list[str]:
    """'39-02-005' -> ['39', '39-02', '39-02-005']"""
    parts = code.split('-')
    return ['-'.join(parts[:i+1]) for i in range(len(parts))]


def main():
    print(f"[pcja] Reading {DB_PATH}", flush=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT sommaire FROM jade_decisions WHERE sommaire IS NOT NULL AND length(sommaire) > 50")

    # code -> {labels_at_depth: Counter, freq: int}
    concept_labels = defaultdict(Counter)
    concept_freq = Counter()
    n_rows = 0
    n_blocks = 0
    for (sommaire,) in cur:
        n_rows += 1
        if n_rows % 50000 == 0:
            print(f"[pcja] processed {n_rows} rows, {len(concept_freq)} concepts, {n_blocks} blocks", flush=True)
        blocks = extract_blocks(sommaire)
        for code, labels in blocks:
            n_blocks += 1
            ancestors = code_ancestors(code)
            # On associe chaque label[i] à l'ancêtre[i] s'il existe
            for i, anc in enumerate(ancestors):
                if i < len(labels):
                    concept_labels[anc][labels[i]] += 1
            concept_freq[code] += 1
    conn.close()
    print(f"[pcja] DONE: {n_rows} rows, {n_blocks} blocks, {len(concept_freq)} unique deep codes", flush=True)

    # Construire le concept canonique : pour chaque code, label = label le plus fréquent à cette profondeur
    concepts = {}
    all_codes = set(concept_freq) | set(concept_labels.keys())
    # On veut aussi tous les ancêtres
    expanded = set()
    for c in all_codes:
        expanded.update(code_ancestors(c))
    for code in sorted(expanded, key=lambda c: (c.count('-'), c)):
        labels = concept_labels.get(code, Counter())
        if not labels:
            # Pas de label observé — c'est un ancêtre intermédiaire jamais utilisé seul
            best_label = f"<inconnu {code}>"
        else:
            best_label = labels.most_common(1)[0][0]
        parts = code.split('-')
        parent = '-'.join(parts[:-1]) if len(parts) > 1 else None
        concepts[code] = {
            "code": code,
            "label": best_label,
            "parent": parent,
            "depth": len(parts),
            "freq_as_leaf": concept_freq.get(code, 0),
            "label_variants": dict(labels.most_common(5)) if labels else {},
        }

    # Compter freq cumulée (somme des descendants)
    children = defaultdict(list)
    for code, c in concepts.items():
        if c["parent"]:
            children[c["parent"]].append(code)

    def cum_freq(code):
        f = concepts[code]["freq_as_leaf"]
        for ch in children[code]:
            f += cum_freq(ch)
        return f
    for code in concepts:
        concepts[code]["freq_cumulative"] = cum_freq(code)

    out_json = OUT_DIR / "pcja_reconstructed.json"
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(concepts, f, ensure_ascii=False, indent=2)
    print(f"[pcja] wrote {out_json} ({len(concepts)} concepts)", flush=True)

    # Stats
    by_depth = Counter(c["depth"] for c in concepts.values())
    print(f"[pcja] depth distribution: {dict(sorted(by_depth.items()))}", flush=True)
    roots = sorted([c for c in concepts.values() if c["depth"] == 1], key=lambda c: -c["freq_cumulative"])
    print("[pcja] top roots by cumulative freq:")
    for r in roots[:20]:
        print(f"  {r['code']:6s} {r['freq_cumulative']:7d}  {r['label']}")


if __name__ == "__main__":
    main()
