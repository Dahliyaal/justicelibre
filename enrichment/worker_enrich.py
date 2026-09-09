#!/usr/bin/env python3
"""Worker batch enrichment Gemini.

- SELECT décisions Cass non encore enrichies, priorité date DESC
- Appelle Gemini CLI, parse JSON, valide, store
- Throttle pour respecter free tier (~30s/req naturel)
- Resume sur restart (skip décisions déjà en DB)
- Log fails dans enrichment_failures
"""
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

CASS_DB = "/opt/justicelibre/dila/cass.db"
ENR_DB = "/opt/justicelibre/dila/enrichment.db"

# Limite par run (free tier Gemini ~1500/jour)
MAX_PER_RUN = 1400

# ─── Nomenclature codes ─────────────────────────────────────────────
CODES_LEGI = {
    "CC": "Code civil", "CPC": "Code de procédure civile", "CPP": "Code de procédure pénale",
    "CPen": "Code pénal", "CT": "Code du travail", "CSS": "Code de la sécurité sociale",
    "CASF": "Code de l'action sociale et des familles", "CSP": "Code de la santé publique",
    "CGI": "Code général des impôts", "CPI": "Code de la propriété intellectuelle",
    "CMF": "Code monétaire et financier", "CGCT": "Code général des collectivités territoriales",
    "CRPM": "Code rural et de la pêche maritime", "CCH": "Code de la construction et de l'habitation",
    "CCom": "Code de commerce", "CCons": "Code de la consommation", "CRoute": "Code de la route",
    "CJA": "Code de justice administrative", "CTour": "Code du tourisme",
    "CEnvi": "Code de l'environnement", "COJ": "Code de l'organisation judiciaire",
    "CASS": "Code des assurances", "CESEDA": "Code de l'entrée et du séjour des étrangers",
    "CPCE": "Code des procédures civiles d'exécution", "CElec": "Code électoral",
    "CTrans": "Code des transports", "CFP": "Code général de la fonction publique",
    "CEdu": "Code de l'éducation", "CDef": "Code de la défense", "CForest": "Code forestier",
    "CCD": "Code des douanes", "CSPort": "Code du sport", "CPatrim": "Code du patrimoine",
    "CEnerg": "Code de l'énergie", "CRecher": "Code de la recherche",
    "CAdmin": "Code des relations entre le public et l'administration",
}
NORMES_INTL = {
    "CEDH": "Convention européenne des droits de l'homme",
    "TFUE": "Traité sur le fonctionnement de l'Union européenne",
    "TUE": "Traité sur l'Union européenne",
    "DDHC": "Déclaration des droits de l'homme et du citoyen 1789",
    "Constitution": "Constitution de la République française",
    "DUDH": "Déclaration universelle des droits de l'homme",
    "PIDCP": "Pacte international relatif aux droits civils et politiques",
}
DOCTRINE = {
    "BOFIP":   "Bulletin officiel des finances publiques (doctrine fiscale, opposable à l'administration art. L.80 A LPF)",
    "CADA":    "Avis Commission d'Accès aux Documents Administratifs",
    "DDD":     "Décision/recommandation du Défenseur des droits",
    "CTN":     "Code du travail numérique (vulgarisation officielle SocialGouv, code.travail.gouv.fr)",
    "CIRC":    "Circulaire ministérielle (circulaires.legifrance.gouv.fr)",
    "RAPCONS": "Rapport / Conclusions du rapporteur public au Conseil d'État (ArianeWeb)",
    "AVAVOC":  "Avis de l'avocat général à la Cour de cassation",
}
CODES_BLOCK = "\n".join(f"  {k:8s} = {v}" for k, v in {**CODES_LEGI, **NORMES_INTL, **DOCTRINE}.items())


def build_prompt(juri, formation, date, numero, solution, texte):
    return f"""Tu es un assistant juridique français. Analyse cette décision et retourne UNIQUEMENT un JSON strict (pas de markdown, pas de texte avant/après).

NOMENCLATURE :
{CODES_BLOCK}

Si tu ne reconnais pas le code, mets "code": "?". Si "le présent code" / "ce code" : déduis du contexte global (matière civile/pénale/etc.).

JSON :
{{
  "articles_cites": [
    {{
      "match_exact": "TEXTE EXACT mot-pour-mot copié de la décision. RÈGLE STRICTE : doit OBLIGATOIREMENT contenir littéralement le numéro `num` que tu déclares dans cette entrée. Si pas de snippet contenant la ref complète, mets `match_exact: null` + confidence: 'low'. Pour articles groupés (ex: 'articles X et Y'), 1 entrée par article avec MÊME match_exact mais chaque entrée DOIT avoir son `num` mentionné.",
      "paragraph_snippet": "phrase complète contenant la ref (50-200 chars), copiée EXACTEMENT.",
      "code": "ABRÉVIATION (selon nomenclature ci-dessus)",
      "num": "numéro article SANS alinéa (ex: 700, R4127-4, L1152-1, préliminaire)",
      "alinea": "optionnel, ex: '3'. null sinon.",
      "confidence": "high|medium|low"
    }}
  ],
  "chunks": {{
    "faits": "résumé des faits matériels",
    "procedure": "historique procédural",
    "moyens": "demandes et arguments des parties",
    "question_juridique": "question de droit posée",
    "motivation": "raisonnement de la cour avec visa des textes",
    "solution": "dispositif (rejet/cassation/annulation/etc.)",
    "motif_specifique": "LE pourquoi précis qui a tranché (ratio decidendi)",
    "vulgarisation": "Style journaliste juridique (Le Monde, Mediapart) en 4-7 phrases. RÈGLES : (1) PRÉCIS sur le contexte (qui, quoi, où, comment), (2) ÉVITE les raccourcis comiques (ex: 'racket sur un marché' fait penser à attaque au couteau, préfère 'extorsion par les régisseurs des emplacements'), (3) Pas de jargon (subornation→pression témoin, JLD→juge des libertés et de la détention), (4) Pas de latin, (5) Pas d'abréviations sauf TFUE/CEDH, (6) Précis ET accessible, ni langage de bistrot ('le mec'), ni jargon avocat, (7) Toujours nommer juridiction, décision, motif. INTERDICTION ABSOLUE de nommer une personne physique (dire 'un couple', 'un salarié', jamais un nom).",
    "matiere": "LE domaine juridique en 1-3 mots simples (ex: 'droit du travail', 'bail commercial', 'responsabilité voisinage', 'droit pénal', 'sécurité sociale', 'droit de la famille').",
    "parties_type": "Nature GÉNÉRIQUE des parties, sans aucun nom propre (ex: 'salarié c/ employeur', 'locataire c/ bailleur', 'particulier c/ administration', 'consommateur c/ société', 'assuré c/ assureur').",
    "sens_demandeur": "Qui a formé le pourvoi et l'issue POUR LUI, en clair. Valeurs : 'demandeur gagne' | 'demandeur perd' | 'partiel' | 'na'. Le 'demandeur' = celui qui a saisi la Cour de cassation. Ex: un salarié se pourvoit et obtient la cassation → 'demandeur gagne' ; un employeur se pourvoit et voit son pourvoi rejeté → 'demandeur perd'.",
    "qui_gagne": "En une courte phrase concrète : quel TYPE de partie l'emporte au final (ex: 'le salarié licencié obtient réparation', 'le bailleur conserve son loyer', 'aucun, renvoi en appel'). Sans nom propre.",
    "enjeu_financier": "Montant en euros en jeu s'il est mentionné (ex: '1765', '45000'). null si aucun montant chiffré."
  }}
}}

DÉCISION (Cour de cassation, {formation}, {date}, n° {numero}, {solution}) :
---
{texte}
---

JUSTE le JSON, rien d'autre."""


def parse_json_response(raw):
    raw = raw.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    return json.loads(raw.strip())


def locate(text, paragraph, match_exact, num=None):
    if paragraph and match_exact:
        p = text.find(paragraph)
        if p != -1:
            zone = text[p: p + max(len(paragraph), 300)]
            r = zone.find(match_exact)
            if r != -1:
                return p + r
    if match_exact:
        p = text.find(match_exact)
        if p != -1:
            return p
    if num:
        num_norm = "".join(c for c in num if c.isalnum())
        if num_norm:
            pat = r"[.\s\-‑–]*".join([re.escape(c) for c in num_norm])
            m = re.search(pat, text)
            if m:
                return m.start()
    return None


def get_pending_decisions(cass_conn, enr_conn, limit):
    """Top N décisions Cass NON encore enrichies, priorité date DESC."""
    enriched_ids = {row[0] for row in enr_conn.execute(
        "SELECT decision_id FROM enrichment"
    ).fetchall()}
    failed_ids = {row[0] for row in enr_conn.execute(
        "SELECT decision_id FROM enrichment_failures"
    ).fetchall()}
    skip_ids = enriched_ids | failed_ids
    print(f"[init] {len(enriched_ids)} déjà enrichies, {len(failed_ids)} fails, skip {len(skip_ids)}")

    # On va chercher 2x plus large pour éviter les retry inutiles
    fetched = 0
    found = []
    offset = 0
    while len(found) < limit and fetched < limit * 5:
        rows = cass_conn.execute(
            "SELECT id, juridiction, formation, date, numero, solution, texte "
            "FROM cass_decisions WHERE length(texte) > 1000 "
            "ORDER BY date DESC LIMIT ? OFFSET ?",
            (1000, offset)
        ).fetchall()
        if not rows:
            break
        for r in rows:
            if r[0] not in skip_ids:
                found.append(r)
                if len(found) >= limit:
                    break
        offset += 1000
        fetched += 1000
    return found


# Markers stricts pour éviter faux positifs sur contenu juridique
# (ex: "quota" tout court matche les décisions sur quota d'embauche, quota-part)
# On cherche uniquement dans STDERR et on exige des phrases spécifiques erreur.
RATE_LIMIT_MARKERS_STRICT = [
    "RESOURCE_EXHAUSTED",         # code Google API
    "PERMISSION_DENIED",          # code Google API
    "429 Too Many Requests",      # HTTP standard
    "Quota exceeded",             # phrase exacte Google
    "rate limit exceeded",        # phrase exacte
    "rateLimitExceeded",          # camelCase Google
    "Daily quota exceeded",       # quota journalier
    "free tier",                  # mention free tier épuisé
    "billing required",           # facturation requise
]


class RateLimitHit(Exception):
    """Quota Gemini atteint, faut stop."""


def process_one(decision_row, enr_conn):
    did, juri, formation, date, numero, solution, texte = decision_row
    prompt = build_prompt(juri, formation, date, numero, solution, texte)
    t0 = time.time()
    try:
        # gemini-2.5-flash : modèle stable, capacité garantie (vs preview = rate-limit fréquent)
        result = subprocess.run(
            ["gemini", "-m", "gemini-2.5-flash", "-p", prompt],
            capture_output=True, text=True, timeout=240,
        )
    except subprocess.TimeoutExpired:
        enr_conn.execute(
            "INSERT INTO enrichment_failures (decision_id, error_type, error_message) VALUES (?,?,?)",
            (did, "timeout", ">180s")
        )
        enr_conn.commit()
        return False
    duration = time.time() - t0

    # PRIORITÉ : si JSON parsable → on stocke, on continue. Tout va bien.
    # Un vrai rate-limit Gemini ne renverrait JAMAIS un JSON valide.
    # → Le check markers ne se fait QUE si parse échoue.
    raw = result.stdout
    try:
        data = parse_json_response(raw)
        # ✅ JSON OK : pas de check markers, c'est du contenu légitime même si "quota" apparaît
    except json.JSONDecodeError as e:
        # Parse a échoué : c'est peut-être un rate-limit OU une erreur ponctuelle
        # On regarde stderr pour distinguer
        stderr_lower = result.stderr.lower()
        for marker in RATE_LIMIT_MARKERS_STRICT:
            if marker.lower() in stderr_lower:
                raise RateLimitHit(
                    f"Marker '{marker}' dans stderr (et JSON invalide) : {result.stderr[:500]}"
                )
        # Pas de marker rate-limit → erreur ponctuelle, on log et on skip cette décision
        enr_conn.execute(
            "INSERT INTO enrichment_failures (decision_id, error_type, error_message, raw_response) VALUES (?,?,?,?)",
            (did, "json_error", str(e)[:500], raw[:5000])
        )
        enr_conn.commit()
        return False

    chunks = data.get("chunks", {}) or {}
    refs = data.get("articles_cites", []) or []
    status = "success"
    if not chunks.get("faits") or not chunks.get("vulgarisation"):
        status = "partial"

    enr_conn.execute(
        """INSERT OR REPLACE INTO enrichment
        (decision_id, source, duration_s, status, gen, faits, procedure, moyens,
         question_juridique, motivation, solution, motif_specifique,
         vulgarisation, matiere, parties_type, sens_demandeur, qui_gagne,
         enjeu_financier, raw_response)
        VALUES (?,'cass',?,?,2,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (did, duration, status,
         chunks.get("faits"), chunks.get("procedure"), chunks.get("moyens"),
         chunks.get("question_juridique"), chunks.get("motivation"),
         chunks.get("solution"), chunks.get("motif_specifique"),
         chunks.get("vulgarisation"),
         chunks.get("matiere"), chunks.get("parties_type"),
         chunks.get("sens_demandeur"), chunks.get("qui_gagne"),
         chunks.get("enjeu_financier"), raw[:10000])
    )

    n_loc = 0
    for ref in refs:
        pos = locate(texte, ref.get("paragraph_snippet", ""),
                     ref.get("match_exact", ""), ref.get("num"))
        if pos is not None:
            n_loc += 1
        try:
            enr_conn.execute(
                """INSERT OR REPLACE INTO enrichment_articles
                (decision_id, code, num, alinea, match_exact, paragraph_snippet,
                 abs_position, confidence)
                VALUES (?,?,?,?,?,?,?,?)""",
                (did, ref.get("code") or "?", ref.get("num") or "",
                 ref.get("alinea") or "",
                 ref.get("match_exact"), ref.get("paragraph_snippet"),
                 pos, ref.get("confidence"))
            )
        except Exception as e:
            pass  # doublon ou autre, on ignore
    enr_conn.commit()
    return True, len(refs), n_loc, duration


def main():
    cass_conn = sqlite3.connect(CASS_DB)
    enr_conn = sqlite3.connect(ENR_DB, timeout=120)
    enr_conn.execute("PRAGMA journal_mode=WAL")

    decisions = get_pending_decisions(cass_conn, enr_conn, MAX_PER_RUN)
    print(f"[start] {len(decisions)} décisions à traiter (limit {MAX_PER_RUN})")

    # ─── Circuit breakers ──────────────────────────────────────────
    MAX_CONSECUTIVE_FAILS = 8    # stop si 8 fails d'affilée (vrai signal de panne)
    MAX_TOTAL_FAILS = 500        # tolère ~10% de fails sur 5000 traités
    MIN_DURATION_S = 2.0         # une réponse <2s est suspecte (probablement erreur)
    SUSPICIOUSLY_FAST_LIMIT = 10 # stop si 10 réponses suspectement rapides

    n_ok = 0
    n_fail = 0
    n_consec_fail = 0
    n_fast = 0
    t_start = time.time()

    try:
        for i, dec in enumerate(decisions, 1):
            did = dec[0]
            try:
                res = process_one(dec, enr_conn)
                if res is False:
                    n_fail += 1
                    n_consec_fail += 1
                    print(f"  [{i}/{len(decisions)}] {did} ❌ (fail logged) — consec={n_consec_fail}")
                else:
                    _, n_refs, n_loc, dur = res
                    n_ok += 1
                    n_consec_fail = 0  # reset
                    if dur < MIN_DURATION_S:
                        n_fast += 1
                        print(f"  ⚠️ Réponse suspectement rapide ({dur:.1f}s) — fast count={n_fast}")
                    else:
                        n_fast = 0  # reset si normale
                    if i % 10 == 0:
                        elapsed = time.time() - t_start
                        eta = elapsed / i * (len(decisions) - i) / 3600
                        print(f"  [{i}/{len(decisions)}] {did} ✅ {n_loc}/{n_refs} refs, {dur:.1f}s | ETA {eta:.1f}h")
            except RateLimitHit as e:
                print(f"\n🛑 RATE LIMIT DÉTECTÉ : {e}")
                print(f"  STOP immédiat. {n_ok} ok / {n_fail} fails avant stop.")
                sys.exit(3)
            except Exception as e:
                n_fail += 1
                n_consec_fail += 1
                print(f"  [{i}/{len(decisions)}] {did} 💥 {e}")

            # Circuit breakers
            if n_consec_fail >= MAX_CONSECUTIVE_FAILS:
                print(f"\n🛑 {MAX_CONSECUTIVE_FAILS} fails consécutifs → STOP")
                break
            if n_fail >= MAX_TOTAL_FAILS:
                print(f"\n🛑 {MAX_TOTAL_FAILS} fails total → STOP")
                break
            if n_fast >= SUSPICIOUSLY_FAST_LIMIT:
                print(f"\n🛑 {SUSPICIOUSLY_FAST_LIMIT} réponses suspectement rapides → STOP (probable rate-limit silencieux)")
                break

            # Sleep minimum entre 2 appels (sécurité anti-spam)
            time.sleep(1.5)
    finally:
        cass_conn.close()
        enr_conn.close()
        print(f"\n[done] {n_ok} OK, {n_fail} fails, total {time.time()-t_start:.0f}s")


if __name__ == "__main__":
    main()
