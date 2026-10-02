"""3 oct. 2026 : un article de loi modificative (dates DILA 2999-01-01, sans
état) s'affichait « en vigueur depuis le 1er janvier 2999 »."""
import importlib.util, os, sqlite3, sys, tempfile
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
_k = tempfile.NamedTemporaryFile(delete=False, suffix=".key", mode="w"); _k.write("a" * 64); _k.close()
os.chmod(_k.name, 0o600); os.environ["JL_WAREHOUSE_KEY_FILE"] = _k.name
_spec = importlib.util.spec_from_file_location("warehouse_server", os.path.join(os.path.dirname(_HERE), "warehouse", "warehouse_server.py"))
ws = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ws)
import ssr


def _row():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("create table t(legiarti,num,titre_text,etat,date_debut,date_fin,texte,nota,jorftext,hierarchie)")
    c.execute("insert into t values('LEGIARTI000054052052','1','LOI n°2026-350 du 9 mai 2026','','2999-01-01','2999-01-01',"
              "'A modifié les dispositions suivantes : - Code de procédure pénale','', 'JORFTEXT000054049780','')")
    return c.execute("select * from t").fetchone()


def test_dict_article_modificateur():
    d = ws._law_row_to_dict(_row(), "JORFTEXT000054049780", "JORFTEXT000054049780")
    assert d["article_modificateur"] is True
    assert d["date_debut"] is None and d["date_fin"] is None
    assert "modificative" in d["note"]
    assert d["source_url"] == "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000054049780"


def test_page_sans_2999():
    d = ws._law_row_to_dict(_row(), "JORFTEXT000054049780", "JORFTEXT000054049780")
    h = ssr.render_law("JORFTEXT000054049780", "1", d)
    assert "2999" not in h and "en vigueur depuis" not in h.lower()
    assert "non consolidé" in h


if __name__ == "__main__":
    test_dict_article_modificateur(); test_page_sans_2999(); print("All 2 tests passed.")
