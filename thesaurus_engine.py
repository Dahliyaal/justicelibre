"""Moteur d'expansion sémantique basé sur thesaurus.db unifié.

Charge en mémoire au démarrage (~20 Mo, <1s) les 19k+ concepts issus de
PCJA + EuroVoc + Judilibre + vie-publique. Expose deux API :

  - expand_term(term, scope) -> set[str]    : synonymes + narrower d'un terme
  - expand_query(q, scope) -> (str, trace)  : réécrit la query FTS5 complète

Le scope filtre par origine : "admin" (PCJA + EuroVoc + vie-publique),
"judiciaire" (Judilibre + EuroVoc), "europeen" (EuroVoc seul), "toutes"
(défaut, tout). Les phrases entre guillemets ne sont JAMAIS étendues
(convention Google/Lucene).
"""
from __future__ import annotations

import os
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from threading import Lock
from typing import Iterable

try:
    from unidecode import unidecode
except ImportError:
    def unidecode(s: str) -> str:
        return s


DEFAULT_DB = Path(os.environ.get("THESAURUS_DB", "/opt/justicelibre/thesaurus/thesaurus.db"))

SCOPE_SOURCES = {
    "admin":      {"pcja", "eurovoc", "vie_publique"},
    "judiciaire": {"judilibre_cass", "judilibre_ca", "judilibre_tj", "eurovoc"},
    "europeen":   {"eurovoc"},
    "lois":       {"vie_publique", "eurovoc", "pcja"},
    "toutes":     {"pcja", "eurovoc", "vie_publique", "judilibre_cass", "judilibre_ca", "judilibre_tj"},
}
DEFAULT_SCOPE = "toutes"


def normalize(s: str) -> str:
    return unidecode(s).upper().strip()


class ThesaurusEngine:
    """Charge thesaurus.db en mémoire et expose l'expansion."""

    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        # normalized_label -> list of (source, code) pour ce label
        self._index: dict[str, list[tuple[str, str]]] = defaultdict(list)
        # (source, code) -> {"pref": str, "alts": [str], "scope": str, "parent": str|None}
        self._concepts: dict[tuple[str, str], dict] = {}
        # (source, parent_code) -> [child_code, ...]
        self._children: dict[tuple[str, str], list[str]] = defaultdict(list)
        self._loaded = False
        self._lock = Lock()

    def load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            if not self.db_path.exists():
                self._loaded = True
                return
            # immutable=1 : true readonly sans tentative de créer -wal/-shm
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro&immutable=1", uri=True)
            conn.row_factory = sqlite3.Row
            for r in conn.execute("SELECT source, code, label, parent_code, scope FROM thesaurus_concepts"):
                key = (r["source"], r["code"])
                self._concepts[key] = {
                    "pref": r["label"],
                    "alts": [],
                    "scope": r["scope"],
                    "parent": r["parent_code"],
                }
                if r["parent_code"]:
                    self._children[(r["source"], r["parent_code"])].append(r["code"])
            for r in conn.execute("SELECT source, code, label, label_normalized, label_type FROM thesaurus_labels"):
                key = (r["source"], r["code"])
                if key in self._concepts:
                    self._index[r["label_normalized"]].append(key)
                    if r["label_type"] == "alt":
                        self._concepts[key]["alts"].append(r["label"])
            conn.close()
            self._loaded = True

    def _sources_for_scope(self, scope: str) -> set[str]:
        return SCOPE_SOURCES.get(scope, SCOPE_SOURCES[DEFAULT_SCOPE])

    def expand_term(self, term: str, scope: str = DEFAULT_SCOPE, max_per_term: int = 8) -> set[str]:
        """Retourne synonymes + narrower-direct pour `term`, dans le scope donné.

        Garantit ne jamais retourner le terme original. Limité à max_per_term
        pour éviter les requêtes BM25 explosives.
        """
        if not self._loaded:
            self.load()
        norm = normalize(term)
        if not norm:
            return set()
        out: set[str] = set()
        allowed = self._sources_for_scope(scope)
        for source, code in self._index.get(norm, []):
            if source not in allowed:
                continue
            c = self._concepts.get((source, code))
            if not c:
                continue
            # synonymes (alts)
            for alt in c["alts"]:
                if normalize(alt) != norm:
                    out.add(alt)
            # pref label si différent du terme cherché
            if normalize(c["pref"]) != norm:
                out.add(c["pref"])
            # narrower direct (1 niveau)
            for child_code in self._children.get((source, code), []):
                child = self._concepts.get((source, child_code))
                if child and normalize(child["pref"]) != norm:
                    out.add(child["pref"])
        # tri & limite
        return set(sorted(out)[:max_per_term])

    # ─── Parsing de query : préserve les phrases entre guillemets ─────

    _QUOTED = re.compile(r'"([^"]+)"')
    _NEG = re.compile(r'(?:^|\s)-\S+', re.UNICODE)

    def _split_protected(self, q: str) -> list[tuple[str, str]]:
        """Sépare la query en segments [(type, text), ...].

        type ∈ {"phrase", "neg", "term", "ws"}.
        """
        segments: list[tuple[str, str]] = []
        i = 0
        n = len(q)
        while i < n:
            ch = q[i]
            if ch == '"':
                # phrase
                j = q.find('"', i + 1)
                if j < 0:
                    segments.append(("term", q[i:]))
                    break
                segments.append(("phrase", q[i + 1:j]))
                i = j + 1
            elif ch == '-' and (i == 0 or q[i - 1].isspace()):
                # mot négatif : -mot ou -"phrase"
                if i + 1 < n and q[i + 1] == '"':
                    j = q.find('"', i + 2)
                    if j < 0:
                        j = n - 1
                    segments.append(("neg", q[i + 2:j]))
                    i = j + 1
                else:
                    j = i + 1
                    while j < n and not q[j].isspace():
                        j += 1
                    segments.append(("neg", q[i + 1:j]))
                    i = j
            elif ch.isspace():
                segments.append(("ws", ch))
                i += 1
            else:
                # terme libre (peut être multi-char)
                j = i
                while j < n and not q[j].isspace() and q[j] != '"':
                    j += 1
                segments.append(("term", q[i:j]))
                i = j
        return segments

    def expand_query(
        self, q: str, scope: str = DEFAULT_SCOPE, also_phrase_combos: bool = True
    ) -> tuple[str, list[dict]]:
        """Réécrit la query FTS5 avec expansion synonyme + retourne la trace.

        Retourne (expanded_query, trace) où trace est une liste de dicts
        [{"original": str, "synonyms": [str, ...], "scope": str}].

        Phrases entre guillemets : NON étendues (respectées telles quelles).
        Termes négatifs (-mot) : NON étendus.

        Si also_phrase_combos=True (défaut), tente aussi de matcher des
        bigrammes/trigrammes du flux libre (utile pour "harcèlement moral").
        """
        if not q.strip():
            return q, []
        if not self._loaded:
            self.load()
        segments = self._split_protected(q)
        trace: list[dict] = []

        # Étape 1 : tente match multi-mots dans la séquence des terms libres
        # (consécutifs, ignorant ws). Plus efficace pour "harcèlement moral".
        # On collecte les positions de chaque term pour pouvoir les remplacer.
        term_positions = [(i, seg[1]) for i, seg in enumerate(segments) if seg[0] == "term"]
        i = 0
        replacements: dict[int, str] = {}  # idx in segments -> remplacement
        consumed: set[int] = set()
        while i < len(term_positions):
            # Tente trigramme, bigramme, unigramme dans cet ordre
            matched = False
            for span in (3, 2, 1):
                if i + span > len(term_positions):
                    continue
                idxs = [term_positions[i + k][0] for k in range(span)]
                if any(idx in consumed for idx in idxs):
                    continue
                term_text = " ".join(term_positions[i + k][1] for k in range(span))
                syns = self.expand_term(term_text, scope=scope)
                if syns:
                    # build remplacement FTS5 OR
                    quoted = [f'"{s}"' if " " in s else s for s in syns]
                    if " " in term_text:
                        original_for_or = f'"{term_text}"'
                    else:
                        original_for_or = term_text
                    rep = "(" + original_for_or + " OR " + " OR ".join(quoted) + ")"
                    replacements[idxs[0]] = rep
                    for k in range(1, span):
                        replacements[idxs[k]] = ""
                    for idx in idxs:
                        consumed.add(idx)
                    trace.append({"original": term_text, "synonyms": sorted(syns), "scope": scope})
                    i += span
                    matched = True
                    break
            if not matched:
                i += 1

        # Étape 2 : reconstruction
        out_parts: list[str] = []
        i = 0
        skip_next_ws = False
        while i < len(segments):
            kind, txt = segments[i]
            if kind == "phrase":
                out_parts.append(f'"{txt}"')
            elif kind == "neg":
                if " " in txt:
                    out_parts.append(f'-"{txt}"')
                else:
                    out_parts.append(f"-{txt}")
            elif kind == "term":
                if i in replacements:
                    rep = replacements[i]
                    if rep:
                        out_parts.append(rep)
                    else:
                        # consommé par un n-gramme, skip + skip whitespace suivant
                        skip_next_ws = True
                else:
                    out_parts.append(txt)
            elif kind == "ws":
                if skip_next_ws:
                    skip_next_ws = False
                else:
                    out_parts.append(txt)
            i += 1
        expanded = "".join(out_parts).strip()
        # collapse multiple spaces
        expanded = re.sub(r"\s+", " ", expanded)
        return expanded, trace


# Singleton global
_engine: ThesaurusEngine | None = None
_engine_lock = Lock()


def get_engine(db_path: Path | str | None = None) -> ThesaurusEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = ThesaurusEngine(db_path or DEFAULT_DB)
            _engine.load()
        return _engine


def expand_query(q: str, scope: str = DEFAULT_SCOPE) -> tuple[str, list[dict]]:
    """API publique : (expanded_q, trace)."""
    return get_engine().expand_query(q, scope=scope)
