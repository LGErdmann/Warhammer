import sistema as S

cases = [
    ("Ultramarines Astartes", 25, 3), ("Aeldari-Pattern", 25, 3),
    ("Ultramarines Astartes", 20, 2), ("Aeldari-Pattern", 21, 3),
    ("Chaos-Pattern", 0, 0), ("Ork-Pattern", 1, 1), ("Ork-Pattern", 100, 10),
    ("Tyranid-Pattern", 250, 10), ("Human", 250, 10), ("Human", 55, 5), ("Tyranid-Pattern", 5, 0),
]
all_ok = True
for origin, shock, expected in cases:
    got = S._inc_player_shock_bonus(origin, shock)
    ok = got == expected
    if not ok: all_ok = False
    print(f"[{'OK' if ok else 'FAIL'}] {origin} shock={shock}: got={got} expected={expected}")
assert all_ok
print("\nSHOCK-BONUS FORMULA VERIFIED IN ISOLATION FOR ALL CASES")
