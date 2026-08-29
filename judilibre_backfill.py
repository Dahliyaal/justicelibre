"""Rattrapage Judilibre par plage de dates, via l'endpoint /export.

POURQUOI CE SCRIPT (29 août 2026)
─────────────────────────────────
`judilibre_sync.py --history` suit le journal des transactions : il ne sait
rattraper que ce qui a bougé récemment. Il a été installé le 13 juin 2026.
Tout ce qui a été publié AVANT n'a jamais été collecté, et le journal
transactionnel ne permet pas de remonter si loin.

Mesuré le 29 août 2026, en comparant nos comptes au `total` annoncé par
Judilibre, puis vérifié au niveau des identifiants sur échantillon :

    mois      Judilibre   chez nous   couverture
    2026-01      52 245       6 070        11,6 %
    2026-02      47 485       5 013        10,6 %
    2026-03      58 847      24 931        42,4 %
    2026-04      50 352       2 104         4,2 %
    2026-05      53 580       3 864         7,2 %
    2026-06      58 178      30 567        52,5 %
    2026-07      43 865      44 228          100 %
    2026-08       8 647       8 172         94,5 %

Échantillon d'identifiants réels (100 ids tirés de Judilibre, présence en
base) : avril 13 %, juin 59 %, juillet 100 %. Les comptes ne mentaient pas.

POURQUOI /export ET PAS /decision
─────────────────────────────────
`/export` renvoie les décisions COMPLÈTES (texte compris) par lots, filtrées
par date et par juridiction. Rattraper 248 000 décisions coûte ~1 000 appels
au lieu de 248 000 : le quota PISTE de l'utilisatrice est une ressource
limitée, on ne la brûle pas par confort d'implémentation.

Vérifié avant d'écrire une ligne en base : le format de `/export` est
identique à celui de `/decision` pour tous les champs que `map_to_row`
utilise — `location` compris, qui porte la VILLE de la juridiction (sans
lui on écrirait des dizaines de milliers de « Cour d'appel » sans ville).
Seul `publication` manque, et seulement là où il n'a pas de sens (ca, tj,
tcom n'ont pas de Bulletin).

GARDE-FOUS
──────────
- `--dry-run` par défaut : rien n'est écrit tant qu'on n'a pas passé
  `--apply`.
- Reprise : chaque couple (jour, juridiction) terminé est inscrit dans un
  fichier d'état. Une interruption ne fait pas tout recommencer.
- Anti-doublon : on cherche une ligne existante par id, PUIS par ECLI. La
  base porte déjà 99 336 ECLI de cassation en double (198 940 lignes) : on
  n'en rajoute pas.
- Le jeton PISTE expire en ~1 h. `judilibre_sync.piste_get` le renouvelle
  tout seul sur 401 (correctif du 1er août 2026) — c'est exactement ce qui
  avait tué le rattrapage du 28 juin.

Usage :
    python3 judilibre_backfill.py --date-start 2026-04-01 --date-end 2026-05-01
    python3 judilibre_backfill.py --date-start 2026-01-01 --date-end 2026-07-01 --apply
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import judilibre_sync as J  # noqa: E402  (réutilise get_token/piste_get/map_to_row/upsert)

sys.stdout.reconfigure(line_buffering=True)

JURIDICTIONS = ("cc", "ca", "tj", "tcom")
BATCH_SIZE = 1000
ETAT_DEFAUT = "/opt/justicelibre/.judilibre_backfill_state.json"


def charger_etat(chemin: str) -> set[str]:
    try:
        with open(chemin, encoding="utf-8") as f:
            return set(json.load(f).get("faits", []))
    except (OSError, ValueError):
        return set()


def enregistrer_etat(chemin: str, faits: set[str]) -> None:
    tmp = f"{chemin}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"faits": sorted(faits)}, f)
    os.replace(tmp, chemin)


def assurer_index_ecli(conn: sqlite3.Connection) -> None:
    """Crée l'index sur `ecli` s'il manque. Idempotent.

    Sans lui, `SELECT id FROM decisions WHERE ecli = ?` fait un SCAN complet
    de 1 327 753 lignes sur 23 Go — mesuré le 29 août 2026, un simple
    `count(*)` mettait plus de deux minutes. Une recherche anti-doublon à ce
    prix est inutilisable : c'est probablement pour ça qu'elle n'a jamais été
    faite, et que la base porte 99 336 ECLI de cassation en double.

    L'index sert aussi au site : toute recherche par ECLI en profite.
    """
    deja = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_decisions_ecli'"
    ).fetchone()
    if deja:
        return
    print("[backfill] création de l'index idx_decisions_ecli (peut prendre quelques minutes)…")
    t = time.time()
    conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_ecli ON decisions(ecli)")
    conn.commit()
    print(f"[backfill] index créé en {time.time()-t:.0f}s")


def id_existant(conn: sqlite3.Connection, d: dict) -> str | None:
    """Retrouve la ligne déjà en base : par id, puis par ECLI.

    L'ECLI identifie une décision de façon unique. S'y raccrocher évite de
    réinsérer sous l'id hex Judilibre une décision déjà présente sous un id
    JURITEXT historique — c'est ainsi que se fabriquent les doublons.
    """
    did = d.get("id")
    if did:
        r = conn.execute("SELECT id FROM decisions WHERE id = ?", (did,)).fetchone()
        if r:
            return r[0]
    ecli = (d.get("ecli") or "").strip()
    if ecli:
        r = conn.execute("SELECT id FROM decisions WHERE ecli = ? LIMIT 1", (ecli,)).fetchone()
        if r:
            return r[0]
    return None


def lots_du_jour(client: httpx.Client, jour: str, juri: str):
    """Itère les lots d'un (jour, juridiction). Yield la liste de décisions.

    ⚠️ `date_end` est INCLUSIVE côté Judilibre. Vérifié le 29 août 2026 sur
    la juridiction cc : (13→13) = 0, (13→14) = 42, (14→14) = 42 — les mêmes
    42 décisions, toutes datées du 14. Passer `jour+1` comme borne haute
    faisait donc traiter chaque journée DEUX fois : deux fois les appels,
    deux fois le temps, et un décompte de « nouvelles » gonflé du double en
    simulation. On borne au même jour.
    """
    batch = 0
    while True:
        d = J.piste_get(
            client, "/export",
            date_start=jour, date_end=jour, jurisdiction=juri,
            batch=batch, batch_size=BATCH_SIZE,
        )
        res = d.get("results") or []
        if not res:
            return
        yield res
        if d.get("next_batch") is None:
            return
        batch += 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date-start", required=True, help="AAAA-MM-JJ inclus")
    p.add_argument("--date-end", required=True, help="AAAA-MM-JJ exclu")
    p.add_argument("--juridictions", default=",".join(JURIDICTIONS))
    p.add_argument("--apply", action="store_true",
                   help="écrit réellement en base (sans ce drapeau : simulation)")
    p.add_argument("--state-file", default=ETAT_DEFAUT)
    p.add_argument("--db", default=J.DB)
    args = p.parse_args()

    d0 = datetime.strptime(args.date_start, "%Y-%m-%d").date()
    d1 = datetime.strptime(args.date_end, "%Y-%m-%d").date()
    if d1 <= d0:
        p.error("--date-end doit être postérieure à --date-start")
    juris = [j.strip() for j in args.juridictions.split(",") if j.strip()]

    # Nuance importante : même en simulation, l'index sur `ecli` est créé —
    # c'est une structure, pas une donnée, et sans lui la simulation elle-même
    # est trop lente pour aboutir. Aucune DÉCISION n'est écrite.
    mode = "ÉCRITURE" if args.apply else "SIMULATION (aucune décision ne sera écrite)"
    print(f"[backfill] {args.date_start} → {args.date_end} | juridictions={','.join(juris)} | {mode}")

    conn = sqlite3.connect(args.db, timeout=300)
    conn.execute("PRAGMA journal_mode=WAL")
    # INSERT/DELETE doivent déclencher les triggers du FTS5, sinon l'index
    # dérive silencieusement de la table.
    conn.execute("PRAGMA recursive_triggers=ON")
    conn.execute("PRAGMA busy_timeout=300000")

    assurer_index_ecli(conn)

    faits = charger_etat(args.state_file)
    if faits:
        print(f"[backfill] reprise : {len(faits)} couples (jour, juridiction) déjà traités")

    client = httpx.Client(headers={"Authorization": f"Bearer {J.get_token()}"})
    n_vus = n_ins = n_maj = n_err = 0
    t0 = time.time()

    jour = d0
    while jour < d1:
        lendemain = jour + timedelta(days=1)
        for juri in juris:
            cle = f"{jour.isoformat()}|{juri}"
            if cle in faits:
                continue
            try:
                for lot in lots_du_jour(client, jour.isoformat(), juri):
                    for d in lot:
                        n_vus += 1
                        try:
                            ancien = id_existant(conn, d)
                            _, row = J.map_to_row(d, conn, force_id=ancien)
                            if args.apply:
                                action = J.upsert(conn, row)
                            else:
                                action = "updated" if ancien else "inserted"
                            if action == "inserted":
                                n_ins += 1
                            else:
                                n_maj += 1
                        except Exception as e:
                            n_err += 1
                            print(f"  [err {d.get('id')}] {type(e).__name__}: {str(e)[:120]}")
            except Exception as e:
                n_err += 1
                print(f"[err {cle}] {type(e).__name__}: {str(e)[:160]} — jour non validé, sera repris")
                continue
            faits.add(cle)
            if args.apply:
                enregistrer_etat(args.state_file, faits)
        ecoule = time.time() - t0
        print(f"[backfill] {jour} | vus={n_vus} nouveaux={n_ins} maj={n_maj} err={n_err} "
              f"| {ecoule/60:.0f} min")
        jour = lendemain

    print(f"\n[backfill] TERMINÉ en {(time.time()-t0)/60:.0f} min")
    print(f"  décisions vues     : {n_vus}")
    print(f"  nouvelles          : {n_ins}")
    print(f"  déjà connues (maj) : {n_maj}")
    print(f"  erreurs            : {n_err}")
    if not args.apply:
        print("\n  ⚠️  SIMULATION — rien n'a été écrit. Relancer avec --apply.")
    conn.close()
    return 1 if n_err and not n_ins else 0


if __name__ == "__main__":
    sys.exit(main())
