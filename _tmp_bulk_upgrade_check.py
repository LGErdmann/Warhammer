import sistema as S
import uuid, random

S.init_db()

def make_player(origin):
    uname = f"test_bulk_{uuid.uuid4().hex[:8]}"
    ok, err = S._inc_register_account(uname, "pw12345")
    assert ok, err
    conn = S.get_conn()
    user = conn.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone()
    uid = user["id"]
    cid = S.char_id_for_user(uid)
    conn.close()
    ch = S.load_character(cid)
    run = S._inc_start_run(ch, origin=origin)
    for o in list(run["node"]["offers"]):
        run = S._inc_shop_buy(run, ch, o["offer_id"])
    run = S._inc_shop_leave(run, ch)
    return uid, cid, ch, run

def cleanup(uid, cid):
    conn = S.get_conn()
    conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
    conn.execute("DELETE FROM characters WHERE id=?", (cid,))
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit(); conn.close()

# --- 1) Tank chance: no minion, no bulk -> not every hit should be tanked ---
random.seed(1)
minion = S._inc_minion_stats("Grunt", "", "Human", "Common", 1)
minion["bulk"] = False
minion["wounds_current"] = minion["wounds_max"]
player_traits = {"Defence": 0, "Resilience": 0}
tanked = 0
player_hit = 0
for _ in range(200):
    m = dict(minion)
    enemy = {"alive": True, "name": "Foe", "attack_pool": 10, "weapon_name": "Claw", "weapon_damage": 3, "weapon_ed": 0,
             "attack_skill": "WS", "tier": 1, "wrath_current": 0, "shock_max": 1, "shock_current": 0}
    log = S._inc_enemy_turn([enemy], player_traits, 0, [m])
    entry = log[0]
    if entry.get("hit"):
        if entry.get("target") == "minion":
            tanked += 1
        else:
            player_hit += 1
print(f"non-bulk minion: tanked={tanked} player_hit={player_hit} (expect both > 0, roughly 50/50)")
assert tanked > 0 and player_hit > 0, "expected a MIX of tanked/player hits without Bulk"
print("NON-BULK MINION HAS A CHANCE (NOT ALWAYS) TO TANK - VERIFIED\n")

# --- 2) Bulk minion always tanks -------------------------------------------
bulk_minion = S._inc_minion_stats("Ogryn Bodyguard", "", "Human", "Legendary", 1, bulk=True)
assert bulk_minion["bulk"] is True
tanked = 0; player_hit = 0
for _ in range(100):
    m = dict(bulk_minion)
    enemy = {"alive": True, "name": "Foe", "attack_pool": 10, "weapon_name": "Claw", "weapon_damage": 3, "weapon_ed": 0,
             "attack_skill": "WS", "tier": 1, "wrath_current": 0, "shock_max": 1, "shock_current": 0}
    log = S._inc_enemy_turn([enemy], player_traits, 0, [m])
    entry = log[0]
    if entry.get("hit"):
        if entry.get("target") == "minion": tanked += 1
        else: player_hit += 1
print(f"bulk minion: tanked={tanked} player_hit={player_hit} (expect player_hit == 0)")
assert player_hit == 0, "Bulk minion must ALWAYS draw the attack while alive"
print("BULK MINION ALWAYS TANKS - VERIFIED\n")

# --- 3) Bulk trait reachable via the actual shop offer path -----------------
found_bulk_offer = False
for _ in range(300):
    offer = S._inc_generate_minion_offer("Human")
    if offer.get("bulk"):
        found_bulk_offer = True
        assert offer["name"] == "Ogryn Bodyguard"
        break
assert found_bulk_offer, "never rolled a Bulk minion offer for Human in 300 tries"
found_bulk_offer_ty = False
for _ in range(400):
    offer = S._inc_generate_minion_offer("Tyranid-Pattern")
    if offer.get("bulk"):
        found_bulk_offer_ty = True
        assert offer["name"] == "Hive Tyrant Guard"
        break
assert found_bulk_offer_ty, "never rolled a Bulk minion offer for Tyranid-Pattern in 400 tries"
print("BULK OFFER GENERATION (HUMAN + TYRANID) - VERIFIED\n")

# --- 4) More Tyranid wargear/talent variety ---------------------------------
total_weapons = sum(len(v) for v in S.INC_TYRANID_WARGEAR.values())
total_armour = sum(len(v) for v in S.INC_TYRANID_ARMOUR.values())
total_talents = len(S.INC_MINION_TALENTS["Tyranid-Pattern"])
print(f"tyranid wargear count={total_weapons} armour count={total_armour} talents count={total_talents}")
assert total_weapons >= 15
assert total_armour >= 10
assert total_talents >= 10
print("EXPANDED TYRANID CATALOG SIZE - VERIFIED\n")

# --- 5) Tyranid weapon upgrade-on-repeat-purchase, replace-on-different -----
uid, cid, ch, run = make_player("Tyranid-Pattern")
starting_weapon_name = next(w["name"] for w in (run.get("starting_wargear") or []) + (run.get("extra_wargear") or []) if S._inc_is_weapon_item(w))
print("starting weapon:", starting_weapon_name)
same_offer = None
for rarity, lst in S.INC_TYRANID_WARGEAR.items():
    for w in lst:
        if w["name"] == starting_weapon_name:
            same_offer = {"type": "tyranid_wargear", "rarity": rarity, "name": w["name"], "icon": w["icon"],
                          "melee": w["melee"], "damage": w["damage"], "ed": w["ed"], "ap": w["ap"],
                          "effect": w["effect"], "minion_support": w["minion_support"], "support_value": w["support_value"],
                          "cost": 0, "label": w["name"], "detail": "", "offer_id": 0}
            break
assert same_offer, "could not find offer dict for the starting weapon"
run = S._inc_persist(run["id"], node={"type": "shop", "offers": [same_offer]})
run = S._inc_get_run(run["id"])
run = S._inc_shop_buy(run, ch, 0)
weapons_after = [w for w in (run.get("starting_wargear") or []) + (run.get("extra_wargear") or []) if S._inc_is_weapon_item(w)]
print("weapons after buying the SAME one again:", [(w["name"], S._gear_details_dict(w.get('details', {})).get('incursion_level')) for w in weapons_after])
assert len(weapons_after) == 1, "should still be exactly 1 weapon (upgraded, not duplicated)"
leveled = weapons_after[0]
d = S._gear_details_dict(leveled.get("details", {}))
assert int(d.get("incursion_level", 1)) == 2, f"expected incursion_level 2 after upgrading, got {d.get('incursion_level')}"
print("TYRANID SAME-WEAPON REPURCHASE UPGRADES IT - VERIFIED\n")

# now buy a DIFFERENT one - should replace, not stack, and reset to level 1
diff_offer = None
for rarity, lst in S.INC_TYRANID_WARGEAR.items():
    for w in lst:
        if w["name"] != starting_weapon_name:
            diff_offer = {"type": "tyranid_wargear", "rarity": rarity, "name": w["name"], "icon": w["icon"],
                          "melee": w["melee"], "damage": w["damage"], "ed": w["ed"], "ap": w["ap"],
                          "effect": w["effect"], "minion_support": w["minion_support"], "support_value": w["support_value"],
                          "cost": 0, "label": w["name"], "detail": "", "offer_id": 0}
            break
    if diff_offer: break
run = S._inc_persist(run["id"], node={"type": "shop", "offers": [diff_offer]})
run = S._inc_get_run(run["id"])
run = S._inc_shop_buy(run, ch, 0)
weapons_after2 = [w for w in (run.get("starting_wargear") or []) + (run.get("extra_wargear") or []) if S._inc_is_weapon_item(w)]
print("weapons after buying a DIFFERENT one:", [w["name"] for w in weapons_after2])
assert len(weapons_after2) == 1 and weapons_after2[0]["name"] == diff_offer["name"]
print("TYRANID DIFFERENT-WEAPON PURCHASE REPLACES (NOT STACKS) - VERIFIED\n")

cleanup(uid, cid)
print("ALL CHECKS PASSED")
