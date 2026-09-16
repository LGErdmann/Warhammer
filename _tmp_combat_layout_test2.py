import sistema as S
import uuid

S.init_db()
uname = f"test_layout2_{uuid.uuid4().hex[:8]}"
ok, err = S._inc_register_account(uname, "pw12345", "Human")
assert ok, err

conn = S.get_conn()
user = conn.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone()
uid = user["id"]
cid = S.char_id_for_user(uid)
conn.close()

ch = S.load_character(cid)
run = S._inc_start_run(ch)
for o in list(run["node"]["offers"]):
    run = S._inc_shop_buy(run, ch, o["offer_id"])
run = S._inc_shop_leave(run, ch)
node = run["node"]
print("enemy count:", len(node["enemies"]))

import streamlit as st
class FakeCol:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __getattr__(self, name):
        def _stub(*a, **k): return None
        return _stub
def fake_columns(spec):
    n = spec if isinstance(spec, int) else len(spec)
    return [FakeCol() for _ in range(n)]

st.markdown = lambda *a, **k: None
st.columns = fake_columns
st.button = lambda *a, **k: False
st.radio = lambda *a, **k: "ATTACK"
st.selectbox = lambda *a, **k: None
class FakeContainer:
    def __enter__(self): return self
    def __exit__(self, *a): return False
st.container = lambda *a, **k: FakeContainer()
st.error = lambda *a, **k: None
st.caption = lambda *a, **k: None
st.session_state = {}

# Test with 1 enemy (typical), then artificially pad to 5 enemies to check
# the chunked-row wrap logic doesn't crash.
S._inc_render_combat(run, ch, node)
print("1-enemy render OK")

node5 = dict(node)
node5["enemies"] = (node["enemies"] * 3)[:5]
for idx, e in enumerate(node5["enemies"]):
    e["uid"] = f"{e['uid']}-{idx}"
S._inc_render_combat(run, ch, node5)
print("5-enemy render OK")

conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()
print("cleaned up")
