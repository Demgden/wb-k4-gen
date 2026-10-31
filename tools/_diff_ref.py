# -*- coding: utf-8 -*-
"""和"参考.bcm4"（用户在 4.11.20 编辑器里保存的小样）逐层 diff 键集合。"""
import json, sys

ref = json.load(open(r"G:\celeste\workbuddy\K4xAI\scratch\参考.bcm4", encoding="utf-8"))
our = json.load(open(sys.argv[1], encoding="utf-8"))


def keys(o):
    return set(o.keys()) if isinstance(o, dict) else set()


def rk(o):
    return list(o.keys()) if isinstance(o, dict) else []


def diff(tag, a, b):
    if keys(a) != keys(b):
        print(f"{tag}: ref={sorted(keys(a))}")
        print(f"{' ' * len(tag)}  our={sorted(keys(b))}")
        print(f"{' ' * len(tag)}  only-ref={sorted(keys(a) - keys(b))} only-our={sorted(keys(b) - keys(a))}")


diff("top", ref, our)
ra = list(ref["theatre"]["actors"].values())[0]
oa = list(our["theatre"]["actors"].values())[0]
diff("actor", ra, oa)
diff("block_data_json", ra["block_data_json"], oa["block_data_json"])
rs = list(ref["theatre"]["styles"].values())[0]
os_ = list(our["theatre"]["styles"].values())[0]
diff("style", rs, os_)
rg = list(ref["theatre"]["groups"].values())[0]
og = list(our["theatre"]["groups"].values())[0]
diff("group", rg, og)
rs2 = list(ref["theatre"]["scenes"].values())[0]
os2 = list(our["theatre"]["scenes"].values())[0]
diff("scene", rs2, os2)
rb = list(ref["theatre"]["actors"].values())[0]["block_data_json"]["blocks"]
ob = list(our["theatre"]["actors"].values())[0]["block_data_json"]["blocks"]
diff("block", next(iter(rb.values())), next(iter(ob.values())))
diff("audio", list(ref["audio"].values())[0], list(our["audio"].values())[0])
print("\nref scene.actors:", rs2.get("actors"), "| our:", os2.get("actors"))
print("ref broadcasts:", json.dumps(ref["broadcasts"], ensure_ascii=False)[:120])
print("our broadcasts keys:", list(our["broadcasts"])[:4])
