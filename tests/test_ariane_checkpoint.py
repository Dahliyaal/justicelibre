"""scrape_ariane : le point de reprise ne dépasse jamais le dernier id vivant.

Audit du 2 oct. 2026, F2 : à la « fin du corpus » le checkpoint enregistrait
l'identifiant ATTEINT (dernier vivant + 5 000), load_checkpoint prenait le plus
grand du fichier et de la base, et la moisson sautait 5 000 ids par jour
(325793 -> 430775) en écrivant « +0 » puis « ArianeWeb OK ».

Hors ligne : base SQLite temporaire, fetch_one simulé, aucune requête réseau.
"""
import io
import os
import sqlite3
import sys
import tempfile
from contextlib import redirect_stdout

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import scrape_ariane as sa  # noqa: E402

B = 200_000   # au-dessus de START_ID (95 000), comme sur la prod (325 793)


def _setup(vivants_en_base, nouveaux_vivants, ckpt=None, age_jours=30):
    d = tempfile.mkdtemp()
    sa.DB_PATH = os.path.join(d, "j.db")
    sa.CHECKPOINT_FILE = os.path.join(d, "ckpt")
    sa.MAX_CONSECUTIVE_404 = 5
    sa.SONDES = (2, 5)
    sa.SLEEP_BETWEEN_REQUESTS = 0
    sa.time.sleep = lambda *_: None
    conn = sqlite3.connect(sa.DB_PATH)
    sa.ensure_schema(conn)
    for n in vivants_en_base:
        conn.execute("INSERT INTO ariane_decisions VALUES (?,?,?,datetime('now', ?))",
                     (f"/Ariane_Web/AW_DCE/|{n}", n, "x" * 300, f"-{age_jours} days"))
    conn.commit()
    conn.close()
    if ckpt is not None:
        open(sa.CHECKPOINT_FILE, "w").write(str(ckpt))
    sa.fetch_one = lambda client, num: ("y" * 300) if num in nouveaux_vivants else None
    os.environ.pop("ARIANE_DEPUIS", None)
    os.environ.pop("ARIANE_JUSQUA", None)


def _run():
    buf = io.StringIO()
    rc = None
    with redirect_stdout(buf):
        try:
            rc = sa.main()
        except SystemExit as e:
            rc = e.code
    return rc, buf.getvalue(), int(open(sa.CHECKPOINT_FILE).read())


def test_fin_du_corpus_ne_saute_pas():
    """Rien de neuf : le checkpoint reste au dernier vivant (100), pas à 105."""
    _setup([B+98, B+99, B+100], set())
    rc, out, ck = _run()
    assert ck == B+100, f"checkpoint={ck} (doit rester au dernier vivant 100)\n{out}"


def test_checkpoint_au_dela_de_la_base_ignore():
    """Fichier à 5 100 (état de la prod) : on repart de la base, pas du fichier."""
    _setup([B+98, B+99, B+100], set(), ckpt=B+5100)
    conn = sqlite3.connect(sa.DB_PATH)
    assert sa.load_checkpoint(conn) == B+100
    conn.close()


def test_rattrape_les_nouvelles_apres_un_checkpoint_mensonger():
    _setup([B+98, B+99, B+100], {B+101, B+103}, ckpt=B+5100)
    rc, out, ck = _run()
    conn = sqlite3.connect(sa.DB_PATH)
    nums = {r[0] for r in conn.execute("SELECT ariane_num FROM ariane_decisions")}
    assert {B+101, B+103} <= nums, f"décisions 101/103 non récupérées : {sorted(nums)}\n{out}"
    assert ck == B+103, f"checkpoint={ck}, attendu 103 (dernier récupéré)"
    assert rc in (0, None)


def test_zero_dit_franchement_et_code_non_nul():
    _setup([B+98, B+99, B+100], set(), age_jours=30)
    rc, out, ck = _run()
    assert "0 nouvelle décision" in out, out
    assert rc == 3, f"code de sortie {rc!r}, attendu 3 (moisson morte depuis 30 j)"


def test_zero_recent_reste_ok():
    _setup([B+98, B+99, B+100], set(), age_jours=0)
    rc, out, ck = _run()
    assert "0 nouvelle décision" in out, out
    assert rc in (0, None), rc


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except Exception as e:
                fails += 1
                print(f"  FAIL {name}: {type(e).__name__}: {e}")
    if fails:
        sys.exit(1)
    print("All ariane checkpoint tests passed.")
