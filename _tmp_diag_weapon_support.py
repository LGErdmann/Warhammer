import sistema as S
import uuid, json

S.init_db()

uname = f"test_diagws_{uuid.uuid4().hex[:8]}"
ok, err = S._inc_register_account(uname, "pw12345")
assert ok, err
conn = S.get_conn()
user = conn.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone()
uid = user["id"]
cid = S.char_id_for_user(uid)
conn.close()
ch = S.load_character(cid)
run = S._inc_start_run(ch, origin="Tyranid-Pattern")
for o in list(run["node"]["offers"]):
    run = S._inc_shop_buy(run, ch, o["offer_id"])
run = S._inc_shop_leave(run, ch)

weapon = S._inc_usable_weapons(ch, run)[0]
print("weapon dict:", json.dumps(weapon, indent=2))

# Damage Apex Tyranid so healing is visible
apex_key = None
minions = [dict(m) for m in run["minions"]]
for m in minions:
    if m["name"] == "Apex Tyranid":
        m["wounds_current"] = 1
run = S._inc_persist(run["id"], minions=minions)
run = S._inc_get_run(run["id"])
apex_before = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
print("apex wounds before:", apex_before["wounds_current"], "/", apex_before["wounds_max"])

healed = False
for i in range(30):
    node = S._inc_combat_node("easy", 1)
    tank_enemy = dict(node["enemies"][0])
    tank_enemy["wounds_max"] = 100000; tank_enemy["wounds_current"] = 100000; tank_enemy["resilience"] = 0
    tank_enemy["defence"] = 0  # guarantee hits
    node["enemies"] = [tank_enemy]
    run = S._inc_persist(run["id"], node=node)
    run = S._inc_get_run(run["id"])
    target_uid = run["node"]["enemies"][0]["uid"]
    run = S._inc_combat_attack(run, ch, [target_uid], weapon["key"])
    apex_now = next((m for m in run["minions"] if m["name"] == "Apex Tyranid"), None)
    log_tail = run["node"].get("log", [])
    player_attacks = [e for e in log_tail if e.get("actor") == "player" and e.get("action") == "attack"]
    last = player_attacks[-1] if player_attacks else None
    print(f"attack {i}: hit={last.get('hit') if last else None} apex_wounds={apex_now['wounds_current'] if apex_now else 'N/A'}")
    if apex_now and apex_now["wounds_current"] > 1:
        healed = True
        print(">>> HEALING APPLIED")
        break

print("healed:", healed)

conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()
