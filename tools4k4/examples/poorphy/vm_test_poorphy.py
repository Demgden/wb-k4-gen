# -*- coding: utf-8 -*-
"""vm_test_poorphy.py — PoorPhy.bcm4 块图虚拟机行为测试（闭环验证）

把 gen_poorphy_tmpl.js 生成的 PoorPhy.bcm4 用块图解释器真实执行，并与一个
独立的 Python 参考模型（严格镜像积木语义）逐帧对比。

参考模型语义必须与积木【完全一致】，包括：
  * 列表 1 基；lists_replace 越界是静默空操作；lists_get_value 越界 → 抛错（对齐编辑器）
  * math_trig 为角度制
  * controls_if 是 if/else-if（首个命中即返回）
  * 量纲：刚角 = 度（喂 COS/SIN）；刚AV = 弧度/帧（喂 ω×r 与 I=½mr²）
  * SAT：任一轴重叠 ≤ 0 → 分离；只在「穿透轴」上取最小重叠轴
  * 冲量有效质量：法向角耦合用 (r×n)²，切向角耦合用 (r·n)²

覆盖：
  1. 初始化：6 刚体状态/派生质量/顶点/对列表预扩展(按 NB_MAX 容量)/顶点刷新
  2. 自由运行 240 帧：每帧全部物理状态逐项对比（证明 emitter 翻译正确）
  3. 真实碰撞：断言 SAT 至少触发一次、且碰撞确实改变了角速度（无旋转 bug 回归）
  4. 交互脚本：空格暂停(含按住边沿) / S 单步 / 鼠标拖拽抓取 / R 重置
     / E 循环设置新刚体边数(3..8，含按住不连跳与回绕) / G 在鼠标处生成新刚体(含满员拒绝)
  5. 渲染路径：每帧画笔落点集合 == 参考模型顶点集合
  6. 稳定性：全程无 NaN / 无越界 / 能量不爆
  7. 影子覆盖：每个输入连接都有 shadows 条目（铁律 5）
"""
import json, math, re, sys

WORK = sys.argv[1] if len(sys.argv) > 1 else "PoorPhy.bcm4"   # 可传任意 .bcm4 路径；缺省当前目录 PoorPhy.bcm4
w = json.load(open(WORK, encoding="utf8"))
VNAME = {k: v["name"] for k, v in w["variables"].items()}
ACTOR = next(a for a in w["theatre"]["actors"].values() if a["name"] == "物理")

NB, MAXV = 6, 8
NB_MAX = 16          # 刚体容量上限（E 设边数 / G 生成新刚体；列表按它预扩展）
SPAWN_R = 34.0       # 新刚体半径（新增参数只有边数，半径固定）
# x, y, r, 边数, 初始角(度), 初始角速度(度/帧), vx, vy（与 poorphy_content.js BODIES 一致）
BODIES = [
    [-380, 180, 38, 8,   0,  1.5,  1.2,  0.0],
    [-120, 240, 34, 8,   0, -1.2,  0.8,  0.0],
    [ 140, 150, 44, 4,  25,  2.6, -0.6,  0.0],
    [ 380, 220, 40, 5,  10, -2.0, -1.0,  0.0],
    [-260,  60, 36, 6,   0,  1.8,  0.5,  0.5],
    [ 240,  40, 42, 8,   0,  1.1, -0.4,  0.3],
]
DEG2RAD = 0.017453292519943295
RAD2DEG = 57.29577951308232
W_MAX = 0.15          # 角速度上限（弧度/帧）
ITER, GRAV = 3, 0.5
DAMP_V, DAMP_W = 0.999, 0.995
REST_WALL = 0.8          # 墙体法向恢复系数（切向摩擦由墙反弹冲量求解，FLOOR_FRICTION 已废除）
E_REST, MU = 0.1, 0.3
SLOP, BETA = 0.5, 0.4
V_MAX, ROOM_X, ROOM_Y = 40, 600, 300


def div(a, b):
    return a / b if b else 0.0
def rnd(x):
    """kitten4 math_round(OP=ROUND) = JS Math.round = floor(x+0.5)（非 Python 银行家舍入）"""
    return float(math.floor(x + 0.5))
def sind(d):
    return math.sin(math.radians(d))
def cosd(d):
    return math.cos(math.radians(d))


# ============================================================ 参考模型（镜像积木语义）
class Ref:
    def __init__(self):
        self.S = {n: 0.0 for n in
                  ["暂停", "单步", "对数", "抓取", "上鼠标", "上空格", "上S", "上R",
                   "鼠X", "鼠Y", "按下", "帧数",
                   # —— 新增刚体（E/G 键）——
                   "新边数", "体数", "上E", "上G", "新槽"]}
        self.S["新边数"] = 6.0       # 与 bcm4 变量默认值一致
        self.S["体数"] = float(NB)   # 与 bcm4 变量默认值一致（init 也会写 NB）
        self.L = {n: [] for n in
                  ["初X", "初Y", "初VX", "初VY", "初角", "初AV",
                   "刚X", "刚Y", "刚VX", "刚VY", "刚角", "刚AV", "刚R", "边数",
                   "刚质量", "刚反质量", "刚反惯量", "顶X", "顶Y",
                   "对A", "对B", "对NX", "对NY", "对深"]}

    def lg(self, name, i):
        i = int(i)
        lst = self.L[name]
        return float(lst[i - 1]) if 1 <= i <= len(lst) else 0.0

    def ls(self, name, i, v):
        i = int(i)
        if 1 <= i <= len(self.L[name]):
            self.L[name][i - 1] = float(v)

    def s(self, name, v):
        self.S[name] = float(v)

    def v(self, name):
        return self.S[name]

    def nb(self):
        """当前刚体数（G 键生成后动态增长）——所有「按刚体遍历」的循环都用它，不用常量 NB"""
        return int(self.v("体数"))

    # ---- 世界顶点(i) ----
    def world_verts(self, i):
        n = int(self.lg("边数", i))
        for k in range(1, n + 1):
            slot = (int(i) - 1) * MAXV + k
            step = div(360.0 * k, n)
            ang = self.lg("刚角", i) + step
            # ★ 与积木一致：世界顶点写入时 math_round 取整（JS Math.round = floor(x+0.5)）
            self.ls("顶X", slot, rnd(self.lg("刚X", i) + self.lg("刚R", i) * cosd(ang)))
            self.ls("顶Y", slot, rnd(self.lg("刚Y", i) + self.lg("刚R", i) * sind(ang)))

    # ---- 边法线(i,k) → 法线XEDG/法线YEDG ----
    def edge_normal(self, i, k):
        i, k = int(i), int(k)
        slot = (i - 1) * MAXV + k
        slot2 = (i - 1) * MAXV + 1 if k == int(self.lg("边数", i)) else slot + 1
        ex = self.lg("顶X", slot2) - self.lg("顶X", slot)
        ey = self.lg("顶Y", slot2) - self.lg("顶Y", slot)
        ln = math.sqrt(ex * ex + ey * ey)
        if ln > 0.000001:
            self.S["_法线X"], self.S["_法线Y"] = div(-ey, ln), div(ex, ln)
        else:
            self.S["_法线X"], self.S["_法线Y"] = 0.0, 0.0

    # ---- 投影(i, 轴x, 轴y) → 投小PROJ/投大PROJ ----
    def project(self, i, ax, ay):
        lo, hi = 1e9, -1e9
        for k in range(1, int(self.lg("边数", i)) + 1):
            slot = (int(i) - 1) * MAXV + k
            d = self.lg("顶X", slot) * ax + self.lg("顶Y", slot) * ay
            if d < lo:
                lo = d
            if d > hi:
                hi = d
        self.S["_投小"], self.S["_投大"] = lo, hi

    # ---- SAT(i,j) → sat深SAT + 法XSAT/法YSAT ----
    def sat(self, i, j):
        self.S["_sat深"], self.S["_最小深"] = 0.0, 1e9
        self.S["_法X"], self.S["_法Y"], self.S["_分离"] = 0.0, 0.0, 0.0
        for body in (i, j):
            for k in range(1, int(self.lg("边数", body)) + 1):
                self.edge_normal(body, k)
                ax, ay = self.S["_法线X"], self.S["_法线Y"]
                self.project(i, ax, ay)
                loA, hiA = self.S["_投小"], self.S["_投大"]
                self.project(j, ax, ay)
                loB, hiB = self.S["_投小"], self.S["_投大"]
                mn = hiA if hiA < hiB else hiB
                mx = loA if loA > loB else loB
                ov = mn - mx
                if ov <= 0:
                    self.S["_分离"] = 1.0
                if ov > 0 and ov < self.S["_最小深"]:
                    self.S["_最小深"] = ov
                    self.S["_法X"], self.S["_法Y"] = ax, ay
        dx = self.lg("刚X", j) - self.lg("刚X", i)
        dy = self.lg("刚Y", j) - self.lg("刚Y", i)
        if dx * self.S["_法X"] + dy * self.S["_法Y"] < 0:
            self.S["_法X"], self.S["_法Y"] = -self.S["_法X"], -self.S["_法Y"]
        self.S["_sat深"] = 0.0 if self.S["_分离"] == 1.0 else self.S["_最小深"]

    # ---- 支撑点(i, 向x, 向y) → 支点XSUP/支点YSUP（取投影最大者） ----
    def support(self, i, dx, dy):
        best, px, py = -1e9, 0.0, 0.0
        for k in range(1, int(self.lg("边数", i)) + 1):
            slot = (int(i) - 1) * MAXV + k
            d = self.lg("顶X", slot) * dx + self.lg("顶Y", slot) * dy
            if d > best:
                best, px, py = d, self.lg("顶X", slot), self.lg("顶Y", slot)
        self.S["_支点X"], self.S["_支点Y"] = px, py

    # ---- 解算冲量(a,b,nx,ny,pen,mode) ----
    def resolve(self, a, b, nx, ny, pen, mode):
        a, b = int(a), int(b)
        if mode == 1:
            if pen > SLOP:
                corr = div((pen - SLOP) * BETA, self.lg("刚反质量", a) + self.lg("刚反质量", b))
                self.ls("刚X", a, self.lg("刚X", a) - nx * corr * self.lg("刚反质量", a))
                self.ls("刚Y", a, self.lg("刚Y", a) - ny * corr * self.lg("刚反质量", a))
                self.ls("刚X", b, self.lg("刚X", b) + nx * corr * self.lg("刚反质量", b))
                self.ls("刚Y", b, self.lg("刚Y", b) + ny * corr * self.lg("刚反质量", b))
            return
        # 接触点：甲体取 +n 支撑点（朝向 b），乙体取 -n 支撑点（朝向 a）
        self.support(a, nx, ny)
        axp, ayp = self.S["_支点X"], self.S["_支点Y"]
        self.support(b, -nx, -ny)
        bxp, byp = self.S["_支点X"], self.S["_支点Y"]
        cx, cy = (axp + bxp) * 0.5, (ayp + byp) * 0.5
        rax, ray = cx - self.lg("刚X", a), cy - self.lg("刚Y", a)
        rbx, rby = cx - self.lg("刚X", b), cy - self.lg("刚Y", b)
        # 刚AV 是弧度/帧 → ω×r 直接用
        vax = self.lg("刚VX", a) - self.lg("刚AV", a) * ray
        vay = self.lg("刚VY", a) + self.lg("刚AV", a) * rax
        vbx = self.lg("刚VX", b) - self.lg("刚AV", b) * rby
        vby = self.lg("刚VY", b) + self.lg("刚AV", b) * rbx
        rvx, rvy = vbx - vax, vby - vay
        vn = rvx * nx + rvy * ny
        if vn >= 0:
            return
        e = E_REST
        if vn > -0.5:
            e = 0.0
        # 法向角耦合 (r×n)²
        ra_n = rax * ny - ray * nx
        rb_n = rbx * ny - rby * nx
        # ★ 结合顺序必须与积木一致：积木为 (invMa+invMb) + (项A + 项B)，
        #   写成左结合 (((invMa+invMb)+项A)+项B) 会差 1 ULP → 帧188 起分叉。
        denom = ((self.lg("刚反质量", a) + self.lg("刚反质量", b))
                 + ((ra_n * ra_n) * self.lg("刚反惯量", a)
                    + (rb_n * rb_n) * self.lg("刚反惯量", b)))
        jn = div(-(1 + e) * vn, denom)
        if jn < 0:
            jn = 0.0
        tx, ty = -ny, nx
        # 切向角耦合 (r·n)²
        ra_t = rax * nx + ray * ny
        rb_t = rbx * nx + rby * ny
        denom_t = ((self.lg("刚反质量", a) + self.lg("刚反质量", b))
                   + ((ra_t * ra_t) * self.lg("刚反惯量", a)
                      + (rb_t * rb_t) * self.lg("刚反惯量", b)))
        vt = rvx * tx + rvy * ty
        jt = div(-vt, denom_t)
        lim = jn * MU
        if jt > lim:
            jt = lim
        if jt < -lim:
            jt = -lim
        ix, iy = jn * nx + jt * tx, jn * ny + jt * ty
        self.ls("刚VX", a, self.lg("刚VX", a) - ix * self.lg("刚反质量", a))
        self.ls("刚VY", a, self.lg("刚VY", a) - iy * self.lg("刚反质量", a))
        self.ls("刚VX", b, self.lg("刚VX", b) + ix * self.lg("刚反质量", b))
        self.ls("刚VY", b, self.lg("刚VY", b) + iy * self.lg("刚反质量", b))
        self.ls("刚AV", a, self.lg("刚AV", a) - (rax * iy - ray * ix) * self.lg("刚反惯量", a))
        self.ls("刚AV", b, self.lg("刚AV", b) + (rbx * iy - rby * ix) * self.lg("刚反惯量", b))

    # ---- 物理步进 ----
    def step(self):
        nb = self.nb()   # 当前刚体数（含 G 键生成的）
        for i in range(1, nb + 1):
            self.ls("刚VY", i, self.lg("刚VY", i) - GRAV)
        self.s("对数", 0.0)
        for i in range(1, nb + 1):
            for j in range(i + 1, nb + 1):
                # ★ 必须写成显式乘法：Python 的 x**2 走 C pow()，与 x*x 有 0.2% 概率差 1 ULP
                dx_ = self.lg("刚X", j) - self.lg("刚X", i)
                dy_ = self.lg("刚Y", j) - self.lg("刚Y", i)
                d2 = dx_ * dx_ + dy_ * dy_
                rr = self.lg("刚R", i) + self.lg("刚R", j)
                if d2 <= rr * rr:
                    self.sat(i, j)
                    if self.S["_sat深"] > 0:
                        self.s("对数", self.v("对数") + 1)
                        self.ls("对A", self.v("对数"), i)
                        self.ls("对B", self.v("对数"), j)
                        self.ls("对NX", self.v("对数"), self.S["_法X"])
                        self.ls("对NY", self.v("对数"), self.S["_法Y"])
                        self.ls("对深", self.v("对数"), self.S["_sat深"])
        for _p in range(ITER):
            for q in range(1, int(self.v("对数")) + 1):
                self.resolve(self.lg("对A", q), self.lg("对B", q), self.lg("对NX", q),
                             self.lg("对NY", q), self.lg("对深", q), 0)
        for q in range(1, int(self.v("对数")) + 1):
            self.resolve(self.lg("对A", q), self.lg("对B", q), self.lg("对NX", q),
                         self.lg("对NY", q), self.lg("对深", q), 1)
        for i in range(1, nb + 1):
            self.ls("刚VX", i, self.lg("刚VX", i) * DAMP_V)
            self.ls("刚VY", i, self.lg("刚VY", i) * DAMP_V)
            self.ls("刚AV", i, self.lg("刚AV", i) * DAMP_W)
            # ★ 与积木一致：位置积分输出 math_round 取整（速度/角度保持全精度）
            self.ls("刚X", i, rnd(self.lg("刚X", i) + self.lg("刚VX", i)))
            self.ls("刚Y", i, rnd(self.lg("刚Y", i) + self.lg("刚VY", i)))
            # 刚角（度） += 刚AV（弧度/帧）× RAD2DEG
            self.ls("刚角", i, self.lg("刚角", i) + self.lg("刚AV", i) * RAD2DEG)
            # 边缘反弹：包围圆只做粗筛 → 墙反弹(i, nx, ny, 墙距) 冲量求解（含角速度）
            if self.lg("刚X", i) - self.lg("刚R", i) < -ROOM_X:
                self.wall(i, 1.0, 0.0, ROOM_X)
            if self.lg("刚X", i) + self.lg("刚R", i) > ROOM_X:
                self.wall(i, -1.0, 0.0, ROOM_X)
            if self.lg("刚Y", i) - self.lg("刚R", i) < -ROOM_Y:
                self.wall(i, 0.0, 1.0, ROOM_Y)
            if self.lg("刚Y", i) + self.lg("刚R", i) > ROOM_Y:
                self.wall(i, 0.0, -1.0, ROOM_Y)
            # ★ 同上：显式乘法对齐积木（速率钳会写回状态，ULP 差异会累积）
            vx_ = self.lg("刚VX", i); vy_ = self.lg("刚VY", i)
            sp = math.sqrt(vx_ * vx_ + vy_ * vy_)
            if sp > V_MAX:
                self.ls("刚VX", i, div(self.lg("刚VX", i) * V_MAX, sp))
                self.ls("刚VY", i, div(self.lg("刚VY", i) * V_MAX, sp))
            if self.lg("刚AV", i) > W_MAX:
                self.ls("刚AV", i, W_MAX)
            if self.lg("刚AV", i) < -W_MAX:
                self.ls("刚AV", i, -W_MAX)
        for i in range(1, nb + 1):
            self.world_verts(i)

    # ---- 墙反弹(i, 法线x, 法线y, 墙距) —— 镜像积木「墙反弹」过程 ----
    # 墙 = 无限质量静态体；n 指向房间内部；墙距 = 房间半宽/半高。
    # 接触点 = 「接触面中点」：沿 -n 投影最大的一批顶点（深度差 ≤0.5px）取平均
    #   · 单点接触（尖角撞墙）→ 力臂正确 → 撞墙产生自旋
    #   · 面接触（多边形平躺）→ 面中点 → 法向冲量过质心 → 不产生假扭矩
    def wall(self, i, nx, ny, lim):
        i = int(i)
        self.world_verts(i)          # 积木第一句：call 世界顶点(i)（用当前帧最新顶点）
        n = int(self.lg("边数", i))
        best = -1e9
        proj = []
        for k in range(1, n + 1):
            slot = (i - 1) * MAXV + k
            d = -(self.lg("顶X", slot) * nx + self.lg("顶Y", slot) * ny)
            proj.append(d)
            if d > best:
                best = d
        sx = sy = 0.0
        cnt = 0
        for k in range(1, n + 1):
            if proj[k - 1] >= best - 0.5:
                slot = (i - 1) * MAXV + k
                sx += self.lg("顶X", slot)
                sy += self.lg("顶Y", slot)
                cnt += 1
        px, py = div(sx, cnt), div(sy, cnt)
        rx, ry = px - self.lg("刚X", i), py - self.lg("刚Y", i)
        pen = -lim - (px * nx + py * ny)
        if pen > 0:
            # 位置修正：沿 n 推回房间内
            self.ls("刚X", i, self.lg("刚X", i) + nx * pen)
            self.ls("刚Y", i, self.lg("刚Y", i) + ny * pen)
            # 接触点速度 = v + ω×r（刚AV 为弧度/帧）
            vx = self.lg("刚VX", i) - self.lg("刚AV", i) * ry
            vy = self.lg("刚VY", i) + self.lg("刚AV", i) * rx
            vn = vx * nx + vy * ny
            if vn < 0:
                e = REST_WALL
                rn = rx * ny - ry * nx                     # 法向角耦合 r×n
                denom = self.lg("刚反质量", i) + rn * rn * self.lg("刚反惯量", i)
                jn = div(-(1 + e) * vn, denom)
                if jn < 0:
                    jn = 0.0
                tx, ty = -ny, nx
                rt = rx * nx + ry * ny                     # 切向角耦合 r·n
                denom_t = self.lg("刚反质量", i) + rt * rt * self.lg("刚反惯量", i)
                vt = vx * tx + vy * ty
                jt = div(-vt, denom_t)
                limj = jn * MU
                if jt > limj:
                    jt = limj
                if jt < -limj:
                    jt = -limj
                ix, iy = jn * nx + jt * tx, jn * ny + jt * ty
                self.ls("刚VX", i, self.lg("刚VX", i) + ix * self.lg("刚反质量", i))
                self.ls("刚VY", i, self.lg("刚VY", i) + iy * self.lg("刚反质量", i))
                self.ls("刚AV", i, self.lg("刚AV", i)
                        + (rx * iy - ry * ix) * self.lg("刚反惯量", i))

    # ---- 找最近(x,y,tol) ----
    def nearest(self, tx, ty, tol):
        best_d, near = 1e9, 0
        for i in range(1, self.nb() + 1):
            dx_ = self.lg("刚X", i) - tx; dy_ = self.lg("刚Y", i) - ty
            d2 = dx_ * dx_ + dy_ * dy_
            rr = self.lg("刚R", i) + tol
            if d2 < rr * rr and d2 < best_d:
                best_d, near = d2, i
        return near

    # ---- 新刚体（镜像积木「新刚体」过程：G 键在鼠标处追加刚体）----
    def spawn(self):
        if self.v("体数") >= NB_MAX:
            return                      # 满员：整个分支空操作
        self.s("新槽", self.v("体数") + 1.0)
        self.s("体数", self.v("体数") + 1.0)
        g = int(self.v("新槽"))
        self.ls("刚X", g, rnd(self.v("鼠X")))
        self.ls("刚Y", g, rnd(self.v("鼠Y")))
        self.ls("刚VX", g, 0.0)
        self.ls("刚VY", g, 0.0)
        self.ls("刚角", g, 0.0)
        self.ls("刚AV", g, 0.0)
        self.ls("刚R", g, SPAWN_R)
        self.ls("边数", g, self.v("新边数"))
        # ★ 与积木一致：质量 = ((r*r)*0.01)；反惯量 = 1/((0.5*m)*(r*r))（结合顺序逐一对应）
        m = (SPAWN_R * SPAWN_R) * 0.01
        self.ls("刚质量", g, m)
        self.ls("刚反质量", g, div(1.0, m))
        self.ls("刚反惯量", g, div(1.0, (0.5 * m) * (SPAWN_R * SPAWN_R)))
        self.world_verts(g)

    # ---- 输入处理（镜像积木顺序）----
    # ★ 布尔语义（2026-10-23）：mouse_down / check_key 在编辑器中返回 true/false，
    #   且 true ≠ 1 / false ≠ 0 → 边沿检测必须「布尔直用 + not 取反」，不能与数字比较。
    def input_process(self, keys, mouse, md):
        self.s("鼠X", mouse[0])
        self.s("鼠Y", mouse[1])
        self.s("按下", 1.0 if md else 0.0)
        if self.v("按下") and not self.v("上鼠标"):
            self.s("抓取", self.nearest(self.v("鼠X"), self.v("鼠Y"), 25))
        if not self.v("按下"):
            self.s("抓取", 0.0)
        self.s("上鼠标", self.v("按下"))
        if self.v("抓取") > 0:
            g = int(self.v("抓取"))
            # ★ 与积木一致：抓取目标也取整（对齐整数位置网格）
            self.ls("刚X", g, rnd(self.v("鼠X")))
            self.ls("刚Y", g, rnd(self.v("鼠Y")))
            self.ls("刚VX", g, 0.0)
            self.ls("刚VY", g, 0.0)
            self.ls("刚AV", g, self.lg("刚AV", g) * 0.9)
        space = 32 in keys
        if space and not self.v("上空格"):
            self.s("暂停", 1.0 - self.v("暂停"))
        self.s("上空格", 1.0 if space else 0.0)
        skey = 83 in keys
        if skey and not self.v("上S"):
            self.s("单步", 1.0)
        self.s("上S", 1.0 if skey else 0.0)
        rkey = 82 in keys
        if rkey and not self.v("上R"):
            self.reset()
        self.s("上R", 1.0 if rkey else 0.0)
        # E(69)：循环设置「新边数」3→4→…→8→3（边沿检测；值保存直到下次修改）
        ekey = 69 in keys
        if ekey and not self.v("上E"):
            nv = self.v("新边数") + 1.0
            if nv > 8:
                nv = 3.0
            self.s("新边数", nv)
        self.s("上E", 1.0 if ekey else 0.0)
        # G(71)：在鼠标当前位置生成新刚体（边沿检测；满员 NB_MAX 空操作）
        gkey = 71 in keys
        if gkey and not self.v("上G"):
            self.spawn()
        self.s("上G", 1.0 if gkey else 0.0)

    # ---- 初始化 / 重置 / 帧 ----
    def init(self):
        for b in BODIES:
            self.L["初X"].append(b[0]); self.L["初Y"].append(b[1])
            self.L["初VX"].append(b[6]); self.L["初VY"].append(b[7])
            self.L["初角"].append(b[4]); self.L["初AV"].append(b[5])
            self.L["刚R"].append(b[2]); self.L["边数"].append(b[3])
        for L in ("刚X", "刚Y", "刚VX", "刚VY", "刚角", "刚AV", "刚质量", "刚反质量", "刚反惯量"):
            self.L[L] = [0.0] * NB_MAX   # 预扩展：ls 越界静默跳过（与块图 listAdd 扩容对齐；按 NB_MAX 容量）
        # 边数/刚R 只随 BODIES 有 NB 条 → 补足到 NB_MAX（与积木补扩展 listAdd 对齐）
        for L in ("边数", "刚R"):
            self.L[L] = self.L[L] + [0.0] * (NB_MAX - NB)
        for i in range(1, NB + 1):
            self.ls("刚X", i, self.lg("初X", i)); self.ls("刚Y", i, self.lg("初Y", i))
            self.ls("刚VX", i, self.lg("初VX", i)); self.ls("刚VY", i, self.lg("初VY", i))
            self.ls("刚角", i, self.lg("初角", i))
            # 初AV 以「度/帧」存放，载入时换算成「弧度/帧」
            self.ls("刚AV", i, self.lg("初AV", i) * DEG2RAD)
            m = self.lg("刚R", i) * self.lg("刚R", i) * 0.01
            self.ls("刚质量", i, m)
            self.ls("刚反质量", i, div(1.0, m))
            # ★ 必须与积木的乘法结合顺序逐一对应：积木为 1/((0.5*m)*(r*r))，
            #   若写成 (((0.5*m)*r)*r) 会差 1 ULP → 支撑点近平局处比较翻转 → 帧190 起分叉。
            self.ls("刚反惯量", i, div(1.0, (0.5 * m) * (self.lg("刚R", i) * self.lg("刚R", i))))
        self.L["顶X"] = [0.0] * (NB_MAX * MAXV)
        self.L["顶Y"] = [0.0] * (NB_MAX * MAXV)
        self.L["对A"] = [0.0] * (NB_MAX * (NB_MAX - 1) // 2)
        self.L["对B"] = [0.0] * (NB_MAX * (NB_MAX - 1) // 2)
        self.L["对NX"] = [0.0] * (NB_MAX * (NB_MAX - 1) // 2)
        self.L["对NY"] = [0.0] * (NB_MAX * (NB_MAX - 1) // 2)
        self.L["对深"] = [0.0] * (NB_MAX * (NB_MAX - 1) // 2)
        for i in range(1, NB + 1):
            self.world_verts(i)
        self.s("对数", 0.0); self.s("暂停", 0.0); self.s("帧数", 0.0); self.s("体数", float(NB))

    def reset(self):
        for i in range(1, NB + 1):
            self.ls("刚X", i, self.lg("初X", i)); self.ls("刚Y", i, self.lg("初Y", i))
            self.ls("刚VX", i, self.lg("初VX", i)); self.ls("刚VY", i, self.lg("初VY", i))
            self.ls("刚角", i, self.lg("初角", i))
            self.ls("刚AV", i, self.lg("初AV", i) * DEG2RAD)
        for i in range(1, NB + 1):
            self.world_verts(i)
        # 重置回初始 NB 个刚体（G 生成的撤掉）；「新边数」参数保留
        self.s("对数", 0.0); self.s("暂停", 0.0); self.s("帧数", 0.0); self.s("体数", float(NB))

    def frame(self, keys, mouse, md):
        self.input_process(keys, mouse, md)
        if self.v("暂停") == 0 or self.v("单步") == 1:
            self.step()
            self.s("单步", 0.0)
            self.s("帧数", self.v("帧数") + 1.0)

    def expected_pen_targets(self):
        """本帧渲染应有的画笔落点 = 落笔状态下的 moveTo 目的地。
        每条路径以「抬笔 moveTo 到首顶点」开始（不画线）→ 首顶点不计；
        随后落笔画 v2..vn，再闭合回 v1（v1 作为闭合点计一次）。"""
        pts = [(600.0, -300.0), (600.0, 300.0), (-600.0, 300.0), (-600.0, -300.0)]
        for i in range(1, self.nb() + 1):
            n = int(self.lg("边数", i))
            for k in range(2, n + 1):
                slot = (i - 1) * MAXV + k
                # 渲染层不再取整（编辑器坐标自动保留 1 位）；顶点已在物理层 round，
                # 因此这里直接用物理顶点值（它们已是整数）。
                pts.append((self.lg("顶X", slot), self.lg("顶Y", slot)))
            s1 = (i - 1) * MAXV + 1
            pts.append((self.lg("顶X", s1), self.lg("顶Y", s1)))
        return pts


# ============================================================ 块图虚拟机
class ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


class ListIndexError(Exception):
    """对齐编辑器行为：读取不存在的列表项 → 抛错（不是静默返回 0）。"""


class VM:
    def __init__(self):
        self.blocks = ACTOR["block_data_json"]["blocks"]
        self.conns = ACTOR["block_data_json"]["connections"]
        self.vars = {v["name"]: float(v.get("value") or 0) for v in w["variables"].values()}
        self.lists = {v["name"]: list(v["value"]) for v in w["variables"].values()
                      if v.get("type") == "list"}
        self.defs = {}
        for b in self.blocks.values():
            if b["type"] == "procedures_2_defnoreturn":
                self.defs[b["fields"]["NAME"]] = b["id"]
        self.env = []                 # 参数绑定栈
        self.keys = set()
        self.mouse = (0.0, 0.0)
        self.md = False
        self.pen_down = False
        self.pen_targets = []         # 落笔时的 moveTo 落点
        self.clears = 0
        self.ops = 0
        self.OPS_LIMIT = 400000      # 【按帧重置】——旧版跨帧累计，第 75 帧就误报

    def reset_ops(self):
        """运算预算按【帧】重置：单帧内无限循环仍会触发，但正常多帧不会被误杀。"""
        self.ops = 0

    def kids(self, bid):
        nxt, ins = None, {}
        for tgt, meta in (self.conns.get(bid) or {}).items():
            if meta.get("type") == "next":
                nxt = tgt
            else:
                ins[meta.get("input_name")] = tgt
        return nxt, ins

    def lst_name(self, bid):
        b = self.blocks[bid]
        if b["type"] in ("lists_get", "variables_get"):
            return VNAME[b["fields"]["VAR"]]
        raise NotImplementedError("list ref " + b["type"])

    # ---------------- 表达式求值 ----------------
    def ev(self, bid):
        self.ops += 1
        if self.ops > self.OPS_LIMIT:
            raise RuntimeError("op budget exceeded (possible infinite loop)")
        b = self.blocks[bid]
        t = b["type"]; f = b.get("fields") or {}
        _, ins = self.kids(bid)
        if t == "math_number":
            return float(f.get("NUM", 0) or 0)
        if t == "default_value":  # 调用函数数字实参的载体（TEXT 字段，按数值 coercion）
            try:
                return float(f.get("TEXT", 0) or 0)
            except (TypeError, ValueError):
                return 0.0
        if t == "variables_get":
            return float(self.vars.get(VNAME.get(f.get("VAR")), 0))
        if t == "math_arithmetic":
            a, c = self.ev(ins["A"]), self.ev(ins["B"])
            op = f["OP"]
            # 显式分支：绝不用字典推导一次性算所有分支（POWER 会 OverflowError）
            if op == "ADD":
                return a + c
            if op == "MINUS":
                return a - c
            if op == "MULTIPLY":
                return a * c
            if op == "DIVIDE":
                return (a / c if c else 0)
            if op == "POWER":
                try:
                    return a ** c
                except OverflowError:
                    return float("inf") if a > 0 else float("-inf")
            raise NotImplementedError("arith op " + op)
        if t == "logic_compare":
            a, c = self.ev(ins["A"]), self.ev(ins["B"])
            op = f["OP"]
            if op == "EQ":
                return a == c
            if op == "NEQ":
                return a != c
            if op == "GT":
                return a > c
            if op == "LT":
                return a < c
            if op == "LTE":
                return a <= c
            if op == "GTE":
                return a >= c
            raise NotImplementedError("compare op " + op)
        if t == "logic_operation":
            a, c = bool(self.ev(ins["A"])), bool(self.ev(ins["B"]))
            return (a and c) if f["OP"] == "AND" else (a or c)
        if t == "logic_negate":
            return not bool(self.ev(ins["BOOL"]))
        if t == "math_round":
            # kitten4 ROUND = JS Math.round（floor(x+0.5)，非 Python 银行家舍入）
            v = self.ev(ins["NUM"])
            return float(math.floor(v + 0.5))
        if t == "math_single":
            v = self.ev(ins["NUM"])
            op = f["OP"]
            if op == "ABS":
                return abs(v)
            if op == "ROOT":
                return v ** 0.5 if v >= 0 else 0.0
            if op == "NEG":
                return -v
            return v
        if t == "math_trig":  # kitten4 为角度制
            v = self.ev(ins["NUM"])
            op = f["OP"]
            if op == "SIN":
                return math.sin(math.radians(v))
            if op == "COS":
                return math.cos(math.radians(v))
            if op == "TAN":
                return math.tan(math.radians(v))
            if op == "ASIN":
                return math.degrees(math.asin(max(-1.0, min(1.0, v))))
            if op == "ACOS":
                return math.degrees(math.acos(max(-1.0, min(1.0, v))))
            if op == "ATAN":
                return math.degrees(math.atan(v))
            raise NotImplementedError("trig op " + op)
        if t == "random":
            return 0.0  # 本作品无随机
        if t == "get_mouse_info":
            return self.mouse[0] if f.get("position") == "x" else self.mouse[1]
        if t == "mouse_down":
            return self.md          # ★ 编辑器返回布尔 true/false（不是 1/0）
        if t == "check_key":
            return int(f.get("key", "0")) in self.keys   # ★ 同上
        if t == "lists_length":
            return float(len(self.lists[self.lst_name(ins["VAR"])]))
        if t == "lists_get_value":
            lst = self.lists[self.lst_name(ins["VAR"])]
            i = int(self.ev(ins["INDEX"])) - 1
            # ★ 对齐编辑器：越界必须抛错（旧版静默返回 0 → 掩盖了「列表第51项不存在」崩溃）
            if not (0 <= i < len(lst)):
                raise ListIndexError("列表第%d项不存在（列表「%s」长度 %d）"
                                     % (i + 1, self.lst_name(ins["VAR"]), len(lst)))
            return float(lst[i])
        if t == "lists_get":
            return None
        if t == "procedures_2_parameter":
            return float(self.env[-1].get(f.get("param_name"), 0.0))
        if t in ("procedures_2_callreturn", "procedures_2_callnoreturn"):
            return self.call_proc(f["NAME"], ins, want_return=(t == "procedures_2_callreturn"))
        raise NotImplementedError("expr " + t)

    # ---------------- 过程调用 ----------------
    def call_proc(self, name, ins, want_return):
        defid = self.defs[name]
        conns = self.conns.get(defid) or {}
        params = []
        for tgt, meta in conns.items():
            m = re.match(r"PARAMS(\d+)$", meta.get("input_name") or "")
            if m and meta.get("input_type") == "value":
                params.append((int(m.group(1)), self.blocks[tgt]["fields"]["param_name"]))
        params.sort()
        args = [self.ev(ins["ARG" + str(i)]) for i in range(len(params))]
        binding = {pn: args[i] for i, (_, pn) in enumerate(params)}
        self.env.append(binding)
        stack_target = None
        for tgt, meta in conns.items():
            if meta.get("input_name") == "STACK":
                stack_target = tgt
        try:
            if stack_target:
                self.run(stack_target)
            ret = None
        except ReturnSignal as r:
            ret = r.value
        self.env.pop()
        if want_return:
            return ret if ret is not None else 0.0
        return None

    # ---------------- 语句执行 ----------------
    def ex(self, bid):
        self.ops += 1
        if self.ops > self.OPS_LIMIT:
            raise RuntimeError("op budget exceeded (possible infinite loop)")
        b = self.blocks[bid]
        t = b["type"]; f = b.get("fields") or {}
        nxt, ins = self.kids(bid)
        if t == "variables_set":
            self.vars[VNAME[f["VAR"]]] = self.ev(ins["VALUE"])
        elif t == "change_variable":
            vid = f.get("valname") or f.get("VAR")
            d = self.ev(ins["n"])
            self.vars[VNAME[vid]] += d if f.get("method", "increase") == "increase" else -d
        elif t == "controls_if":
            m = re.search(r'elseif="(\d+)"', b.get("mutation") or "")
            has_else = 'else="1"' in (b.get("mutation") or "")
            n = int(m.group(1)) if m else 0
            for i in range(n + 1):
                if self.ev(ins["IF" + str(i)]):
                    self.run(ins.get("DO" + str(i)))
                    return
            if has_else:
                self.run(ins.get("ELSE"))
        elif t == "repeat_n_times":
            for _ in range(int(self.ev(ins["times"]))):
                self.run(ins.get("DO"))
        elif t == "repeat_forever":
            self.run(ins.get("DO"))  # 测试里只跑一帧
        elif t == "self_move_to":
            x, y = self.ev(ins["x"]), self.ev(ins["y"])
            if self.pen_down:
                self.pen_targets.append((x, y))
        elif t in ("self_pen_down",):
            self.pen_down = True
        elif t in ("self_pen_up",):
            self.pen_down = False
        elif t == "clear_drawing":
            self.clears += 1
            self.pen_targets = []
        elif t == "lists_replace":
            lst = self.lists[self.lst_name(ins["VAR"])]
            i = int(self.ev(ins["INDEX"])) - 1
            if 0 <= i < len(lst):     # 越界是静默空操作（kitten4/Scratch 语义）
                lst[i] = self.ev(ins["VALUE"])
        elif t == "lists_append":
            self.lists[self.lst_name(ins["VAR"])].append(self.ev(ins["VALUE"]))
        elif t == "procedures_2_return_value":
            raise ReturnSignal(self.ev(ins["VALUE"]))
        elif t in ("procedures_2_callnoreturn", "procedures_2_callreturn"):
            self.call_proc(f["NAME"], ins, want_return=(t == "procedures_2_callreturn"))
        elif t in ("wait", "set_layer_with_pen", "self_set_pen_color", "self_set_pen_size",
                   "self_gradually_disappear", "self_disappear", "play_audio_2",
                   "stop_audio_2", "self_shake", "image_stamp", "warp"):
            if t == "warp":
                self.run(ins.get("DO"))
        else:
            raise NotImplementedError("stmt " + t)

    def run(self, bid):
        while bid:
            self.ex(bid)
            bid = self.kids(bid)[0]

    def split_main(self):
        hat = next(b for b in self.blocks.values() if b["type"] == "start_on_click")
        init, cur = [], self.kids(hat["id"])[0]
        while cur and self.blocks[cur]["type"] != "repeat_forever":
            init.append(cur)
            cur = self.kids(cur)[0]
        assert cur, "repeat_forever not found"
        return init, self.kids(cur)[1]["DO"]


# ============================================================ 测试
def main():
    errors = []
    TOL = 1e-9

    def close(a, b, tol=TOL):
        return abs(a - b) <= tol * max(1.0, abs(a), abs(b))

    def cmp_state(tag, vm, ref):
        for i in range(1, int(vm.vars["体数"]) + 1):
            for name in ("刚X", "刚Y", "刚VX", "刚VY", "刚角", "刚AV"):
                a = vm.lists[name][i - 1]
                b = ref.lg(name, i)
                if not close(a, b):
                    errors.append("%s: %s[%d] vm=%.10g ref=%.10g" % (tag, name, i, a, b))
        for name in ("对数", "帧数", "暂停", "抓取", "上鼠标", "上空格", "上S", "上R", "体数", "新边数"):
            if not close(vm.vars[name], ref.v(name)):
                errors.append("%s: %s vm=%.10g ref=%.10g" % (tag, name, vm.vars[name], ref.v(name)))

    vm = VM()
    ref = Ref()
    init_stmts, forever_body = vm.split_main()
    for st in init_stmts:
        vm.ex(st)
    ref.init()
    cmp_state("after init", vm, ref)

    # 初始化细节断言
    for i in range(1, NB + 1):
        if not close(vm.lists["刚反质量"][i - 1], ref.lg("刚反质量", i)):
            errors.append("init: 刚反质量[%d] mismatch" % i)
        if not close(vm.lists["刚反惯量"][i - 1], ref.lg("刚反惯量", i)):
            errors.append("init: 刚反惯量[%d] mismatch" % i)
    if len(vm.lists["顶X"]) != NB_MAX * MAXV or len(vm.lists["顶Y"]) != NB_MAX * MAXV:
        errors.append("init: 顶X/顶Y not pre-extended to %d" % (NB_MAX * MAXV))
    if len(vm.lists["对A"]) != NB_MAX * (NB_MAX - 1) // 2:
        errors.append("init: 对A not pre-extended")
    if len(vm.lists["刚X"]) != NB_MAX:
        errors.append("init: 刚X not pre-extended to NB_MAX=%d" % NB_MAX)
    print("init: OK (bodies=%d, pairs list=%d, verts=%d)"
          % (len(vm.lists["刚X"]), len(vm.lists["对A"]), len(vm.lists["顶X"])))

    # ---------------- 输入脚本 ----------------
    def script(frame):
        """返回 (keys, mouse, mouse_down)"""
        keys, mouse, md = set(), (0.0, 0.0), False
        if frame == 10:
            keys.add(32)                       # 空格按下 → 暂停
        elif 11 <= frame <= 12:
            keys.add(32)                       # 按住（边沿检测：不应反复翻转）
        if frame == 16:
            keys.add(83)                       # S 按下 → 单步一步
        if frame == 20:
            mouse = (ref.lg("刚X", 3), ref.lg("刚Y", 3))   # 在 3 号刚体上按下
            md = True
        elif 21 <= frame <= 23:
            mouse = (300.0, 100.0)             # 拖拽到 (300,100)
            md = True
        if frame == 30:
            keys.add(82)                       # R 按下 → 重置
        # E(69)：循环设置边数 6→7（40，含 41 按住不连跳）→8（43）→回绕 3（45）
        if frame in (40, 41, 43, 45):
            keys.add(69)
        # G(71)：帧50 在 (0,260) 生成三角形；帧55 在 (350,260) 再生成一个
        if frame == 50:
            mouse = (0.0, 260.0)
            keys.add(71)
        elif frame == 55:
            mouse = (350.0, 260.0)
            keys.add(71)
        return keys, mouse, md

    # ---------------- 逐帧对比 ----------------
    # 帧数必须够长：真实碰撞发生在 ~101 帧之后（旧版只跑 60 帧 → 从未触发一次 SAT，
    # 于是「全局变量踩踏」「量纲错误」「漏碰撞」三个 bug 全部逃过测试）。
    NFRAMES = 240
    grab_checked = False
    reset_checked = False
    spawn_checked = False
    spawn2_checked = False
    collision_frames = 0          # 发生接触的帧数
    spin_changed_frames = 0       # 碰撞确实改变了角速度的帧数
    max_abs_av = 0.0
    for frame in range(NFRAMES):
        keys, mouse, md = script(frame)
        vm.keys, vm.mouse, vm.md = keys, mouse, md
        vm.pen_targets, vm.clears = [], 0
        vm.reset_ops()
        # 记录碰撞前的角速度（用于验证「碰撞真的产生了自转」）
        av_before = list(vm.lists["刚AV"])
        vm.run(forever_body)
        ref.frame(keys, mouse, md)
        cmp_state("frame %d" % frame, vm, ref)

        # 真实碰撞覆盖：SAT 必须至少触发一次
        if vm.vars["对数"] > 0:
            collision_frames += 1
            # 碰撞必须改变参与者的角速度（排除「只有阻尼在变」）
            for q in range(1, int(vm.vars["对数"]) + 1):
                a = int(vm.lists["对A"][q - 1]); b = int(vm.lists["对B"][q - 1])
                for body in (a, b):
                    damped = av_before[body - 1] * DAMP_W
                    if abs(vm.lists["刚AV"][body - 1] - damped) > 1e-9:
                        spin_changed_frames += 1
                        break
        for i in range(1, int(vm.vars["体数"]) + 1):
            max_abs_av = max(max_abs_av, abs(vm.lists["刚AV"][i - 1]))

        # 渲染路径：落笔落点集合 == 参考顶点集合
        exp = ref.expected_pen_targets()
        got = vm.pen_targets
        if len(got) != len(exp):
            errors.append("frame %d: pen targets %d != expected %d" % (frame, len(got), len(exp)))
        else:
            for (gx, gy), (ex_, ey_) in zip(sorted(got), sorted(exp)):
                if not (close(gx, ex_, 1e-6) and close(gy, ey_, 1e-6)):
                    errors.append("frame %d: pen target (%.4f,%.4f) != (%.4f,%.4f)"
                                  % (frame, gx, gy, ex_, ey_))
                    break
        if vm.clears != 1:
            errors.append("frame %d: clear_drawing called %d times (expected 1)" % (frame, vm.clears))

        # 交互语义断言
        if frame == 12 and vm.vars["帧数"] != ref.v("帧数"):
            errors.append("pause: frame counter diverged while paused")
        if frame == 17 and vm.vars["帧数"] != ref.v("帧数"):
            errors.append("step: single-step frame counter diverged")
        if frame == 23:
            g = int(vm.vars["抓取"])
            if g <= 0:
                errors.append("grab: no body grabbed at frame 23")
            elif not close(vm.lists["刚X"][g - 1], 300.0, 1e-6) or not close(vm.lists["刚Y"][g - 1], 100.0, 1e-6):
                errors.append("grab: body %d not following mouse (%.3f, %.3f)"
                              % (g, vm.lists["刚X"][g - 1], vm.lists["刚Y"][g - 1]))
            else:
                grab_checked = True
        if frame == 31:
            # 重置在帧30输入处理触发，之后还跑了 2 步物理（vm 与 ref 同步，cmp_state 已保证）。
            # 此处只验证「重置确实发生」：位置/速度应回到初值附近（容差容纳 2 步物理漂移）；
            # 若无重置，30 帧物理后刚体早已跌落/漂移数十个单位。
            for i in range(1, NB + 1):
                if abs(vm.lists["刚X"][i - 1] - BODIES[i - 1][0]) > 10 or \
                   abs(vm.lists["刚Y"][i - 1] - BODIES[i - 1][1]) > 10 or \
                   abs(vm.lists["刚VX"][i - 1] - BODIES[i - 1][6]) > 1 or \
                   abs(vm.lists["刚VY"][i - 1] - BODIES[i - 1][7]) > 1:
                    errors.append("reset: body %d not restored" % i)
            reset_checked = True

        # 新增刚体断言（E 设边数参数 / G 生成；积木与参考模型同步由 cmp_state 保证）
        if frame == 40 and not close(vm.vars["新边数"], 7.0):
            errors.append("spawn-param: E did not cycle 新边数 6→7 (got %s)" % vm.vars["新边数"])
        if frame == 41 and not close(vm.vars["新边数"], 7.0):
            errors.append("spawn-param: held E double-cycled 新边数 (got %s)" % vm.vars["新边数"])
        if frame == 43 and not close(vm.vars["新边数"], 8.0):
            errors.append("spawn-param: E did not cycle 新边数 7→8 (got %s)" % vm.vars["新边数"])
        if frame == 45 and not close(vm.vars["新边数"], 3.0):
            errors.append("spawn-param: E did not wrap 新边数 8→3 (got %s)" % vm.vars["新边数"])
        if frame == 50:
            if int(vm.vars["体数"]) != NB + 1:
                errors.append("spawn: G did not increment 体数 (got %d)" % int(vm.vars["体数"]))
            elif not close(vm.lists["边数"][NB], 3.0) or not close(vm.lists["刚R"][NB], SPAWN_R):
                errors.append("spawn: body %d wrong 边数/刚R (%s/%s)"
                              % (NB + 1, vm.lists["边数"][NB], vm.lists["刚R"][NB]))
            elif abs(vm.lists["刚X"][NB]) > 3 or abs(vm.lists["刚Y"][NB] - 260.0) > 3:
                errors.append("spawn: body %d not spawned at mouse (%.3f, %.3f)"
                              % (NB + 1, vm.lists["刚X"][NB], vm.lists["刚Y"][NB]))
            else:
                spawn_checked = True
        if frame == 55:
            if int(vm.vars["体数"]) != NB + 2:
                errors.append("spawn: second G did not increment 体数 (got %d)" % int(vm.vars["体数"]))
            elif abs(vm.lists["刚X"][NB + 1] - 350.0) > 3 or abs(vm.lists["刚Y"][NB + 1] - 260.0) > 3:
                errors.append("spawn: body %d not spawned at mouse (%.3f, %.3f)"
                              % (NB + 2, vm.lists["刚X"][NB + 1], vm.lists["刚Y"][NB + 1]))
            else:
                spawn2_checked = True

        # 稳定性
        for i in range(1, int(vm.vars["体数"]) + 1):
            for name in ("刚X", "刚Y", "刚VX", "刚VY", "刚角", "刚AV"):
                val = vm.lists[name][i - 1]
                if not math.isfinite(val):
                    errors.append("frame %d: NaN/Inf in %s[%d]" % (frame, name, i))
            if abs(vm.lists["刚X"][i - 1]) > 605 or abs(vm.lists["刚Y"][i - 1]) > 305:
                errors.append("frame %d: body %d out of bounds (%.1f, %.1f)"
                              % (frame, i, vm.lists["刚X"][i - 1], vm.lists["刚Y"][i - 1]))

    # ---------------- 满员上限（NB_MAX）测试 ----------------
    # 把 NB_MAX 号槽补成合法刚体（拷 1 号状态），体数拉到 NB_MAX，再按 G → 应被拒绝（空操作）
    for L in ("刚X", "刚Y", "刚VX", "刚VY", "刚角", "刚AV", "刚R", "边数", "刚质量", "刚反质量", "刚反惯量"):
        vm.lists[L][NB_MAX - 1] = vm.lists[L][0]
        ref.ls(L, NB_MAX, ref.lg(L, 1))
    vm.vars["体数"] = float(NB_MAX); ref.s("体数", float(NB_MAX))
    cap_keys, cap_mouse, cap_md = {71}, (0.0, 0.0), False
    vm.keys, vm.mouse, vm.md = cap_keys, cap_mouse, cap_md
    vm.pen_targets, vm.clears = [], 0
    vm.reset_ops()
    vm.run(forever_body)
    ref.frame(cap_keys, cap_mouse, cap_md)
    cmp_state("cap frame", vm, ref)
    if int(vm.vars["体数"]) != NB_MAX:
        errors.append("spawn-cap: G at full capacity changed 体数 to %d" % int(vm.vars["体数"]))
    if not close(vm.lists["边数"][NB_MAX - 1], vm.lists["边数"][0]):
        errors.append("spawn-cap: body %d was overwritten at full capacity" % NB_MAX)
    exp = ref.expected_pen_targets()
    if len(vm.pen_targets) != len(exp):
        errors.append("cap frame: pen targets %d != expected %d" % (len(vm.pen_targets), len(exp)))
    else:
        for (gx, gy), (ex_, ey_) in zip(sorted(vm.pen_targets), sorted(exp)):
            if not (close(gx, ex_, 1e-6) and close(gy, ey_, 1e-6)):
                errors.append("cap frame: pen target mismatch (%.4f,%.4f) != (%.4f,%.4f)" % (gx, gy, ex_, ey_))
                break
    print("spawn cap: 体数 stayed %d at NB_MAX (G rejected, body %d untouched)"
          % (int(vm.vars["体数"]), NB_MAX))

    print("frames: %d compared (grab=%s reset=%s spawn=%s/%s)"
          % (NFRAMES, grab_checked, reset_checked, spawn_checked, spawn2_checked))

    # ---------------- 缺陷回归断言 ----------------
    if collision_frames == 0:
        errors.append("regression: SAT never produced a contact in %d frames "
                      "(碰撞路径未被覆盖 → 缺陷无法被发现)" % NFRAMES)
    if spin_changed_frames == 0:
        errors.append("regression: no contact ever changed angular velocity "
                      "(→ 「没有观察到物体旋转」缺陷复现)")
    if not spawn_checked or not spawn2_checked:
        errors.append("regression: spawn feature not covered (E 设边数 / G 生成)")
    print("collision coverage: %d frames with contacts, %d with contact-driven spin change, "
          "max|刚AV|=%.6f rad/frame" % (collision_frames, spin_changed_frames, max_abs_av))
    if max_abs_av <= 1e-9:
        errors.append("regression: angular velocity stayed 0 → 刚体从不自转")

    # ---------------- 影子覆盖（铁律 5） ----------------
    missing = 0
    for bid, blk in vm.blocks.items():
        for tgt, meta in (vm.conns.get(bid) or {}).items():
            if meta.get("type") == "input" and meta["input_name"] not in (blk.get("shadows") or {}):
                missing += 1
    print("shadow coverage: %s" % ("OK" if missing == 0 else str(missing) + " missing"))
    if missing:
        errors.append("%d input connections without shadows" % missing)

    # ---------------- 调用 mutation 完整性 ----------------
    bad_mut = 0
    for bid, blk in vm.blocks.items():
        if blk["type"] in ("procedures_2_callnoreturn", "procedures_2_callreturn"):
            mut = blk.get("mutation") or ""
            if 'def_id="' not in mut or blk["fields"]["NAME"] not in vm.defs:
                bad_mut += 1
    print("call mutations: %s" % ("OK" if bad_mut == 0 else str(bad_mut) + " bad"))
    if bad_mut:
        errors.append("%d call blocks with broken mutation" % bad_mut)

    if errors:
        print("FAIL (%d):" % len(errors))
        for e in errors[:30]:
            print("  -", e)
        sys.exit(1)
    print("PASS: PoorPhy.bcm4 block-graph VM matches reference model on all %d frames "
          "(physics, collisions+spin, input scripting, render path, shadows)" % NFRAMES)


if __name__ == "__main__":
    main()
