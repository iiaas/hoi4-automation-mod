#!/usr/bin/env python3
"""HOI4 玩家单位：无补给/燃油消耗 + 至少“训练有素” —— 纯 Python 运行时补丁，不需要任何 mod 文本。

做法：不再用 Python 循环改数据，而是在游戏进程里给“陆军师每个游戏小时的更新函数”(hoi4.exe+0xC78990，
所有师每次更新都会调用它)装一段很短的机器码。引擎自己调用它时，机器码会判断这个师是否属于玩家国家
或其傀儡国(读国家管理器里的玩家记录 CHuman，不是玩家就什么也不做)，是则：
    - 经验 = 总量/兵力 低于 0.3 就抬到 0.3(补充兵员稀释后也会被立刻抬回，永远不低于训练有素 0.3)
    - 补给低于约 5000 小时就补到 10000 小时
    - 燃油补满
补丁装一次就一直有效(随游戏进程)，安装后 Python 进程立刻退出，没有任何常驻。读档/换国立即生效。

用法：
    Steam 启动项：  pythonw.exe 本脚本 %command%     (启动游戏 + 极短的一次性安装进程)
    手动安装：      pythonw.exe 本脚本 --install      (游戏已在运行时)
    撤销补丁：      pythonw.exe 本脚本 --remove

CArmy(= 一个陆军师，vtable RVA 0x295A2B0) 偏移：
  +0x1D8 所属国家编号  +0x430 经验总量(经验x兵力)  +0x3E0/+0x3EC 兵力数组/个数
  +0x610 当前补给  +0x620 当前燃油  [[+0x138]+0x120] 燃油容量
国家管理器：全局指针 RVA 0x332F260，[mgr+0x310]=国家数组，mgr+0x110 内嵌玩家记录 CHuman(+0x170 当前国家)。
傀儡国：CCountry +0x41C 与 +0x434 都是宗主国编号。
"""
import argparse
import ctypes
import struct
import sys
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent


# ---- 进程/内存辅助(自包含，不依赖其他文件) ----
class _PE32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]


class P:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)

    @staticmethod
    def find_pid(name):
        k = P.k32
        snap = k.CreateToolhelp32Snapshot(0x2, 0)
        pe = _PE32()
        pe.dwSize = ctypes.sizeof(pe)
        pid = None
        ok = k.Process32First(snap, ctypes.byref(pe))
        while ok:
            if pe.szExeFile.decode(errors="ignore").lower() == name:
                pid = pe.th32ProcessID
                break
            ok = k.Process32Next(snap, ctypes.byref(pe))
        k.CloseHandle(snap)
        return pid

    @staticmethod
    def open_process(pid):
        P.k32.OpenProcess.restype = wintypes.HANDLE
        h = P.k32.OpenProcess(0x0400 | 0x0010 | 0x0020 | 0x0008, False, pid)
        if not h:
            sys.exit(f"OpenProcess 失败(错误 {ctypes.get_last_error()})，请以管理员身份运行")
        return h

    @staticmethod
    def module_base(h):
        P.psapi.EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                                 ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
        mods = (wintypes.HMODULE * 1)()
        need = wintypes.DWORD()
        P.psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 3)
        return mods[0]  # 第一个模块就是主 exe

    @staticmethod
    def read_mem(h, addr, size):
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t()
        P.k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got))
        return buf.raw[:got.value]

    @staticmethod
    def write_mem(h, addr, raw):
        done = ctypes.c_size_t()
        return bool(P.k32.WriteProcessMemory(h, ctypes.c_void_p(addr), raw, len(raw), ctypes.byref(done)))


P.k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
P.k32.WriteProcessMemory.argtypes = P.k32.ReadProcessMemory.argtypes

# ---- 逆向得到的偏移(针对当前 hoi4.exe 版本) ----
ARMY_VTABLE_RVA = 0x295A2B0
COUNTRY_VTABLE_RVA = 0x27E7360
COUNTRY_MGR_GLOBAL_RVA = 0x332F260
MGR_COUNTRY_ARRAY = 0x310
MGR_COUNTRY_COUNT = 0x31C
MAX_COUNTRIES = 2048
# 傀儡国：CCountry +0x41C 与 +0x434 都是宗主国编号(玩家可通过“请求远征军”指挥其师)
COUNTRY_OVERLORD = 0x41C
COUNTRY_OVERLORD_CHECK = 0x434

# 本地玩家记录 CHuman 内嵌在国家管理器里；其中存着当前玩家的国家编号
MGR_HUMAN = 0x110
HUMAN_VTABLE_RVA = 0x2720DA8
HUMAN_COUNTRY = 0x170          # int32 国家编号
HUMAN_COUNTRY_CHECK = 0x410    # 同一编号的另一份拷贝，用于交叉校验

# 海军：CShip(vtable) +0x728 -> CTaskForce，国家编号同样在 +0x1D8
SHIP_VTABLE_RVA = 0x2957F28
TASKFORCE_VTABLE_RVA = 0x2962F70
OFF_SHIP_TASKFORCE = 0x728
OFF_SHIP_EXP_SUM = 0x708       # 舰船经验 = +0x708 * 100000 / +0x710
OFF_SHIP_EXP_DEN = 0x710

# 空军：CAirWing(vtable) +0x218 经验(直接与 AIR_WING_XP_LEVELS={100,300,700,900} x100000 比较)
AIRWING_VTABLE_RVA = 0x297ADA8
OFF_WING_EXP = 0x218
OFF_WING_COUNTRY = 0x9C4       # int32 国家编号
MIN_AIR_EXP = 300 * 100000     # 训练有素门槛 300(刚好达标，不留余量)

OFF_ARMY_COUNTRY = 0x1D8
OFF_EXP_SUM = 0x430
OFF_MANPOWER_ARR = 0x3E0
OFF_MANPOWER_CNT = 0x3EC
OFF_SUPPLY = 0x610
OFF_FUEL = 0x620
OFF_FUEL_CAP_PTR = 0x138
OFF_FUEL_CAP = 0x120

MIN_EXP = 30000                # 训练有素门槛 0.3(刚好达标，不留余量)
SUPPLY_FILL = 1_000_000_000    # 10000 小时(定点 x100000)
SUPPLY_LOW = 500_000_000       # 低于它就补
TICK_SECONDS = 0.5
QUICK_SCAN_SECONDS = 10   # 只扫已知含师的内存区域
FULL_SCAN_SECONDS = 300   # 全量扫描，发现新区域

# 用于确认 exe 版本没变：这些 RVA 处的字节必须与分析时一致
SIGNATURES = {
    0xC79080: bytes.fromhex("48019110060000"),  # add [rcx+0x610], rdx  (AddSupply)
    0xC6D6C2: bytes.fromhex("48898E10060000"),  # mov [rsi+0x610], rcx  (初始化补给)
}

k32 = P.k32
import os
LOG = Path(os.environ.get("TEMP", str(HERE))) / "hoi4_nologistics.log"  # 日志放在临时目录，不进仓库
_quiet = False


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    if not _quiet:
        print(line, flush=True)
    try:
        if LOG.exists() and LOG.stat().st_size > 512 * 1024:
            LOG.write_text("", encoding="utf-8")
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wintypes.DWORD), ("PartitionId", wintypes.WORD),
                ("RegionSize", ctypes.c_size_t), ("State", wintypes.DWORD),
                ("Protect", wintypes.DWORD), ("Type", wintypes.DWORD)]


k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
MEM_PRIVATE = 0x20000


def rw_regions(h):
    addr, mbi = 0, MBI()
    while k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        base, size = mbi.BaseAddress or 0, mbi.RegionSize
        if (mbi.State == 0x1000 and mbi.Type == MEM_PRIVATE and not mbi.Protect & 0x100
                and mbi.Protect & 0xFF in (0x04, 0x08, 0x40, 0x80)):
            yield base, size
        addr = base + size
        if addr >= 0x7FFFFFFF0000:
            break


def scan_objects(h, vtables, only=None):
    """按 vtable 扫描对象。返回 ({名称: [地址]}, 含对象的内存区域集合)。only 给定时只扫这些区域。"""
    needles = {name: struct.pack("<Q", vt) for name, vt in vtables.items()}
    found = {name: [] for name in vtables}
    hit_regions = set()
    for base, size in rw_regions(h):
        if only is not None and (base, size) not in only:
            continue
        off = 0
        while off < size:
            n = min(64 << 20, size - off)
            data = P.read_mem(h, base + off, min(n + 8, size - off))  # 不能越过区域末尾，否则整块读取失败
            for name, needle in needles.items():
                i = data.find(needle)
                while i != -1:
                    if i < n and (base + off + i) % 8 == 0:
                        found[name].append(base + off + i)
                        hit_regions.add((base, size))
                    i = data.find(needle, i + 1)
            off += n
            time.sleep(0)  # 让出 CPU
    return found, hit_regions


def q(h, addr):
    raw = P.read_mem(h, addr, 8)
    return struct.unpack("<q", raw)[0] if len(raw) == 8 else None


def i32(h, addr):
    raw = P.read_mem(h, addr, 4)
    return struct.unpack("<i", raw)[0] if len(raw) == 4 else None


def player_country_indices(h, base):
    """当前玩家国家编号集合；游戏未就绪返回 None。
    依据国家管理器内嵌的玩家记录 CHuman：+0x170 与 +0x410 是同一个国家编号；
    再加上以该国家为宗主的傀儡国(其师可被玩家指挥)。"""
    mgr = q(h, base + COUNTRY_MGR_GLOBAL_RVA)
    if not mgr:
        return None
    arr = q(h, mgr + MGR_COUNTRY_ARRAY)
    count = i32(h, mgr + MGR_COUNTRY_COUNT)
    if not arr or not count or not 0 < count < MAX_COUNTRIES:
        return None
    raw = P.read_mem(h, arr, 8 * count)
    if len(raw) != 8 * count:
        return None
    vt = base + COUNTRY_VTABLE_RVA
    ptrs = struct.unpack(f"<{count}Q", raw)
    valid = lambda idx: 0 <= idx < count and ptrs[idx] and q(h, ptrs[idx]) == vt
    human = mgr + MGR_HUMAN
    if q(h, human) != base + HUMAN_VTABLE_RVA:
        return None
    idx, check = i32(h, human + HUMAN_COUNTRY), i32(h, human + HUMAN_COUNTRY_CHECK)
    if idx is None or idx != check or not valid(idx):
        return None
    result = {idx}
    if idx == 0:
        return result
    for sub in range(count):  # 玩家国家的傀儡：宗主字段两处一致且等于玩家国家
        if sub != idx and valid(sub):
            ov = i32(h, ptrs[sub] + COUNTRY_OVERLORD)
            if ov == idx and ov == i32(h, ptrs[sub] + COUNTRY_OVERLORD_CHECK):
                result.add(sub)
    return result


def manpower(h, a):
    cnt, arr = i32(h, a + OFF_MANPOWER_CNT), q(h, a + OFF_MANPOWER_ARR)
    if not arr or not cnt or not 0 < cnt < 256:
        return None
    raw = P.read_mem(h, arr, 8 * cnt)
    if len(raw) != 8 * cnt:
        return None
    return sum(struct.unpack_from("<i", raw, 8 * i + 4)[0] for i in range(cnt))


def tick(h, armies, vtable, players):
    touched = 0
    for a in armies:
        if q(h, a) != vtable or i32(h, a + OFF_ARMY_COUNTRY) not in players:
            continue
        men, total = manpower(h, a), q(h, a + OFF_EXP_SUM)
        if men and men > 0 and total is not None and 0 <= total < MIN_EXP * men:
            P.write_mem(h, a + OFF_EXP_SUM, struct.pack("<q", MIN_EXP * men))
            touched += 1
        sup = q(h, a + OFF_SUPPLY)
        if sup is not None and sup < SUPPLY_LOW:
            P.write_mem(h, a + OFF_SUPPLY, struct.pack("<q", SUPPLY_FILL))
            touched += 1
        cap_ptr = q(h, a + OFF_FUEL_CAP_PTR)
        if cap_ptr:
            cap, cur = q(h, cap_ptr + OFF_FUEL_CAP), q(h, a + OFF_FUEL)
            if cap and cur is not None and 0 < cap < 10**15 and cur < cap:
                P.write_mem(h, a + OFF_FUEL, struct.pack("<q", cap))
                touched += 1
    return touched


def tick_ships(h, ships, vtable, tf_vtable, players):
    touched = 0
    for a in ships:
        if q(h, a) != vtable:
            continue
        tf = q(h, a + OFF_SHIP_TASKFORCE)
        if not tf or q(h, tf) != tf_vtable or i32(h, tf + OFF_ARMY_COUNTRY) not in players:
            continue
        total, den = q(h, a + OFF_SHIP_EXP_SUM), q(h, a + OFF_SHIP_EXP_DEN)
        if den and den > 0 and total is not None and 0 <= total * 100000 // den < MIN_EXP:
            need = -(-MIN_EXP * den // 100000)  # 向上取整
            P.write_mem(h, a + OFF_SHIP_EXP_SUM, struct.pack("<q", need))
            touched += 1
    return touched


def tick_wings(h, wings, vtable, players):
    touched = 0
    for a in wings:
        if q(h, a) != vtable or i32(h, a + OFF_WING_COUNTRY) not in players:
            continue
        exp = q(h, a + OFF_WING_EXP)
        if exp is not None and 0 <= exp < MIN_AIR_EXP:
            P.write_mem(h, a + OFF_WING_EXP, struct.pack("<q", MIN_AIR_EXP))
            touched += 1
    return touched



RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "HOI4NoLogistics"


def remove_old_autostart():
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        try:
            winreg.DeleteValue(k, RUN_NAME)
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# 引擎内补丁(陆军)
# ---------------------------------------------------------------------------
HOOK_ENTRY_RVA = 0xC78990                     # 每个师每次更新都会调用
HOOK_ENTRY_ORIG = bytes.fromhex("48895c2410")  # mov [rsp+0x10], rbx  (5 字节)
HOOK_ENTRY_CHECK = bytes.fromhex("48895c241057")  # 再多核对 push rdi，防止版本不符
CAVE_HEX = (
    "000000000000000000000000000000005052415041514152488b05e1ffffff488b004885c00f840b010000488b15d6ff"
    "ffff483990100100000f85f70000008b90800200003b90200500000f85e500000085d20f84dd000000448b81d8010000"
    "4139d07444443b801c0300000f83c40000004c8b88100300004d85c90f84b40000004f8b0cc14d85c90f84a700000041"
    "39911c0400000f859a000000413991340400000f858d0000004881b9100600000065cd1d7d0b48c7811006000000ca9a"
    "3b488b81380100004885c0741c488b80200100004885c07e10483981200600007d07488981200600004c6389ec030000"
    "4d85c97e414983f940773b4c8b91e00300004d85d2742f4531c0496342044901c04983c20849ffc975f04d85c07e174d"
    "69c0307500004c3981300400007d074c898130040000415a415941585a5848895c2410e900000000"
)
CAVE_DATA_MGR, CAVE_DATA_HVT, CAVE_CODE = 0, 8, 16


def _ntdll():
    return ctypes.WinDLL("ntdll")


def full_process(pid):
    h = k32.OpenProcess(0x1F0FFF, False, pid)
    if not h:
        raise OSError(f"OpenProcess 失败(错误 {ctypes.get_last_error()})")
    return h


def alloc_near(h, target, size):
    """在 target 的 ±1.8GB 内分配可执行内存(jmp rel32 够得着)。"""
    k32.VirtualAllocEx.restype = ctypes.c_void_p
    k32.VirtualAllocEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
                                   wintypes.DWORD, wintypes.DWORD]
    a = max((target - 0x70000000) & ~0xFFFF, 0x10000)
    while a < target + 0x70000000:
        p = k32.VirtualAllocEx(h, ctypes.c_void_p(a), size, 0x3000, 0x40)
        if p:
            return p
        a += 0x10000
    return None


SHIP_HOOK_RVA = 0xC32EB0                         # 每个舰船每次更新都会调用(已验证覆盖全部玩家舰船)
SHIP_HOOK_PRO = bytes.fromhex("40574883ec20")    # push rdi; sub rsp,0x20 (6 字节，原样搬进补丁)
SHIP_CAVE_HEX = (
    "0000000000000000000000000000000000000000000000000000000000000000505241504151488b05e3ffffff483901"
    "0f85d1000000488b05c3ffffff488b004885c00f84be000000488b15b8ffffff483990100100000f85aa0000008b9080"
    "0200003b90200500000f859800000085d20f84900000004c8b81280700004d85c00f84800000004c8b0d8affffff4d39"
    "087574458b80d80100004139d07430443b801c030000735f4c8b88100300004d85c974534f8b0cc14d85c9744a413991"
    "1c04000075414139913404000075384c8b81100700004d85c07e2c4c89c04869c03075000048059f86010049c7c1a086"
    "0100489949f7f9483981080700007d0748898108070000415941585a58"
)
SHIP_DATA = (0, 8, 16, 24)  # d_mgr, d_hvt, d_svt, d_tvt
SHIP_CODE = 32


def hook_status(h, base):
    """'orig' 未装 / 'hooked' 已装 / None 无法识别(版本不符或还没加载)。"""
    cur = P.read_mem(h, base + HOOK_ENTRY_RVA, 6)
    if cur == HOOK_ENTRY_CHECK:
        return "orig"
    if len(cur) == 6 and cur[0] == 0xE9:
        return "hooked"
    return None


def ship_hook_status(h, base):
    cur = P.read_mem(h, base + SHIP_HOOK_RVA, 6)
    if cur == SHIP_HOOK_PRO:
        return "orig"
    if len(cur) == 6 and cur[0] == 0xE9:
        return "hooked"
    return None


def _write_patch(h, entry, patch):
    nt = _ntdll()
    nt.NtSuspendProcess(h)       # 暂停全部线程再改指令，避免改到一半被执行
    try:
        return P.write_mem(h, entry, patch)
    finally:
        nt.NtResumeProcess(h)


def install_hook(h, base):
    st = hook_status(h, base)
    if st == "hooked":
        return "already"
    if st != "orig":
        return None
    entry = base + HOOK_ENTRY_RVA
    code = bytearray(bytes.fromhex(CAVE_HEX))
    cave = alloc_near(h, entry, 0x1000)
    if not cave:
        return None
    struct.pack_into("<Q", code, CAVE_DATA_MGR, base + COUNTRY_MGR_GLOBAL_RVA)
    struct.pack_into("<Q", code, CAVE_DATA_HVT, base + HUMAN_VTABLE_RVA)
    back = entry + 5
    jmp_at = len(code) - 4
    struct.pack_into("<i", code, jmp_at, back - (cave + jmp_at + 4))
    if not P.write_mem(h, cave, bytes(code)):
        return None
    patch = b"\xE9" + struct.pack("<i", (cave + CAVE_CODE) - (entry + 5))
    return "installed" if _write_patch(h, entry, patch) else None


def install_ship_hook(h, base):
    st = ship_hook_status(h, base)
    if st == "hooked":
        return "already"
    if st != "orig":
        return None
    entry = base + SHIP_HOOK_RVA
    code = bytearray(bytes.fromhex(SHIP_CAVE_HEX))
    cave = alloc_near(h, entry, 0x1000)
    if not cave:
        return None
    for off, val in zip(SHIP_DATA, (base + COUNTRY_MGR_GLOBAL_RVA, base + HUMAN_VTABLE_RVA,
                                    base + SHIP_VTABLE_RVA, base + TASKFORCE_VTABLE_RVA)):
        struct.pack_into("<Q", code, off, val)
    code += SHIP_HOOK_PRO                        # 被覆盖的原指令
    jmp_at = len(code)
    code += b"\xE9" + struct.pack("<i", (entry + len(SHIP_HOOK_PRO)) - (cave + jmp_at + 5))
    if not P.write_mem(h, cave, bytes(code)):
        return None
    patch = b"\xE9" + struct.pack("<i", (cave + SHIP_CODE) - (entry + 5)) + b"\x90"  # 6 bytes
    return "installed" if _write_patch(h, entry, patch) else None


WING_HOOK_RVA = 0xF68220                         # 每个空军联队每次更新都会调用(已验证覆盖全部联队)
WING_HOOK_PRO = bytes.fromhex("41554883ec60")    # push r13; sub rsp,0x60
WING_CAVE_HEX = (
    "000000000000000000000000000000000000000000000000505241504151488b05ebffffff4839010f8585000000488b"
    "05cbffffff488b004885c07476488b15c4ffffff4839901001000075668b90800200003b9020050000755885d2745444"
    "8b81c40900004139d07430443b801c030000733f4c8b88100300004d85c974334f8b0cc14d85c9742a4139911c040000"
    "75214139913404000075184881b91802000080c3c9017d0b48c7811802000080c3c901415941585a58"
)
WING_DATA = (0, 8, 16)  # d_mgr, d_hvt, d_wvt
WING_CODE = 24


def wing_hook_status(h, base):
    cur = P.read_mem(h, base + WING_HOOK_RVA, 6)
    if cur == WING_HOOK_PRO:
        return "orig"
    if len(cur) == 6 and cur[0] == 0xE9:
        return "hooked"
    return None


def install_wing_hook(h, base):
    st = wing_hook_status(h, base)
    if st == "hooked":
        return "already"
    if st != "orig":
        return None
    entry = base + WING_HOOK_RVA
    code = bytearray(bytes.fromhex(WING_CAVE_HEX))
    cave = alloc_near(h, entry, 0x1000)
    if not cave:
        return None
    for off, val in zip(WING_DATA, (base + COUNTRY_MGR_GLOBAL_RVA, base + HUMAN_VTABLE_RVA,
                                    base + AIRWING_VTABLE_RVA)):
        struct.pack_into("<Q", code, off, val)
    code += WING_HOOK_PRO
    jmp_at = len(code)
    code += b"\xE9" + struct.pack("<i", (entry + len(WING_HOOK_PRO)) - (cave + jmp_at + 5))
    if not P.write_mem(h, cave, bytes(code)):
        return None
    patch = b"\xE9" + struct.pack("<i", (cave + WING_CODE) - (entry + 5)) + b"\x90"
    return "installed" if _write_patch(h, entry, patch) else None


# 登陆无视制海权：0xEA1250(rcx=国家海军状态对象，+0x10 是国家编号；rdx=海区)判断“我方是否控制该海区”，
# 登陆路线校验与“Insufficient Naval Dominance”提示都靠它。玩家/傀儡国直接返回 1。
INV_HOOK_RVA = 0xEA1250
INV_HOOK_PRO = bytes.fromhex("4883ec28488bc2")   # sub rsp,0x28; mov rax,rdx (7 字节)
INV_OBJ_VTABLE_RVA = 0x2973260                    # 该对象的 vtable，用来确认 rcx 类型
INV_CAVE_HEX = (
    "000000000000000000000000000000000000000000000000505241504151488b05ebffffff4839017576488b05cfffff"
    "ff488b004885c07467488b15c8ffffff4839901001000075578b90800200003b9020050000754985d27445448b411041"
    "39d07430443b801c03000073334c8b88100300004d85c974274f8b0cc14d85c9741e4139911c04000075154139913404"
    "0000750c415941585a58b801000000c3415941585a58"
)
INV_DATA = (0, 8, 16)  # d_mgr, d_hvt, d_xvt
INV_CODE = 24


def inv_hook_status(h, base):
    cur = P.read_mem(h, base + INV_HOOK_RVA, 7)
    if cur == INV_HOOK_PRO:
        return "orig"
    if len(cur) == 7 and cur[0] == 0xE9:
        return "hooked"
    return None


def install_inv_hook(h, base):
    st = inv_hook_status(h, base)
    if st == "hooked":
        return "already"
    if st != "orig":
        return None
    entry = base + INV_HOOK_RVA
    code = bytearray(bytes.fromhex(INV_CAVE_HEX))
    cave = alloc_near(h, entry, 0x1000)
    if not cave:
        return None
    for off, val in zip(INV_DATA, (base + COUNTRY_MGR_GLOBAL_RVA, base + HUMAN_VTABLE_RVA,
                                   base + INV_OBJ_VTABLE_RVA)):
        struct.pack_into("<Q", code, off, val)
    code += INV_HOOK_PRO
    jmp_at = len(code)
    code += b"\xE9" + struct.pack("<i", (entry + len(INV_HOOK_PRO)) - (cave + jmp_at + 5))
    if not P.write_mem(h, cave, bytes(code)):
        return None
    patch = b"\xE9" + struct.pack("<i", (cave + INV_CODE) - (entry + 5)) + b"\x90\x90"
    return "installed" if _write_patch(h, entry, patch) else None


# ---- 登陆其他限制(国家级获取函数，rcx = CCountry*；玩家国家及其傀儡国生效) ----
CTY_CONST_HEX = (
    "0000000000000000000000000000000000000000000000000000000000000000505241504151488b05e3ffffff483901"
    "756d488b05c7ffffff488b004885c0745e488b15c0ffffff48399010010000754e8b90800200003b9020050000754085"
    "d2743c3b901c03000073344c8b88100300004d85c974284189d04f8b0cc14939c9741039911c04000075143991340400"
    "00750c415941585a58b863000000c3415941585a58"
)
CTY_SKIPCAP_HEX = (
    "0000000000000000000000000000000000000000000000000000000000000000505241504151488b05e3ffffff483945"
    "00756d488b05c6ffffff488b004885c0745e488b15bfffffff48399010010000754e8b90800200003b90200500007540"
    "85d2743c3b901c03000073344c8b88100300004d85c974284189d04f8b0cc14939e9741039951c040000751439953404"
    "0000750c415941585a58ff2578ffffff415941585a58"
)
CTY_AGAINST_HEX = (
    "0000000000000000000000000000000000000000000000000000000000000000505241504151488b05e3ffffff483901"
    "757e4183f81a74064183f80e7572488b05bbffffff488b004885c07463488b15b4ffffff4839901001000075538b9080"
    "0200003b9020050000754585d274413b901c03000073394c8b88100300004d85c9742d4189d04f8b0cc14939c9741039"
    "911c04000075193991340400007511415941585a5848c702487dfeff4889d0c3415941585a58"
)
CTY_DATA = (0, 8, 16, 24)  # d_mgr, d_hvt, d_cvt, d_yes
CTY_CODE = 32
GETTER_PRO = bytes.fromhex("4883ec284881c1b8050000")   # sub rsp,0x28; add rcx,0x5b8
AGAINST_PRO = bytes.fromhex("48895c2410")              # mov [rsp+0x10], rbx
SKIP_PRO = bytes.fromhex("488d8db8050000")             # lea rcx,[rbp+0x5b8] (函数中段，rbp = 国家)
# (名称, 入口 RVA, 被覆盖的原指令, 机器码, “允许”分支 RVA 或 0)
CTY_HOOKS = (
    ("海军每次登陆师数上限", 0x6F2FF0, GETTER_PRO, CTY_CONST_HEX, 0),    # 返回 99
    ("海军登陆计划数量上限", 0x6F3040, GETTER_PRO, CTY_CONST_HEX, 0),    # 返回 99
    ("空降计划数量上限", 0x6EB530, GETTER_PRO, CTY_CONST_HEX, 0),        # 返回 99
    ("登陆/空降准备时间", 0x6F9B40, AGAINST_PRO, CTY_AGAINST_HEX, 0),    # 修正 id 0x1A/0xE 取 -0.99
    ("空降每次师数上限", 0x102D8D4, SKIP_PRO, CTY_SKIPCAP_HEX, 0x102D917),  # 玩家直接跳到“允许”(mov al,1; ret)
)


def generic_status(h, base, rva, pro):
    cur = P.read_mem(h, base + rva, len(pro))
    if cur == pro:
        return "orig"
    if len(cur) == len(pro) and cur[0] == 0xE9:
        return "hooked"
    return None


def generic_install(h, base, rva, pro, cave_hex, data_vals, data_offs, code_off):
    st = generic_status(h, base, rva, pro)
    if st == "hooked":
        return "already"
    if st != "orig":
        return None
    entry = base + rva
    code = bytearray(bytes.fromhex(cave_hex))
    cave = alloc_near(h, entry, 0x1000)
    if not cave:
        return None
    for off, val in zip(data_offs, data_vals):
        struct.pack_into("<Q", code, off, val)
    code += pro
    jmp_at = len(code)
    code += bytes([0xE9]) + struct.pack("<i", (entry + len(pro)) - (cave + jmp_at + 5))
    if not P.write_mem(h, cave, bytes(code)):
        return None
    patch = bytes([0xE9]) + struct.pack("<i", (cave + code_off) - (entry + 5)) + bytes([0x90]) * (len(pro) - 5)
    return "installed" if _write_patch(h, entry, patch) else None


def install_cty_hooks(h, base):
    res = []
    for name, rva, pro, hexs, yes in CTY_HOOKS:
        r = generic_install(h, base, rva, pro, hexs,
                            (base + COUNTRY_MGR_GLOBAL_RVA, base + HUMAN_VTABLE_RVA, base + COUNTRY_VTABLE_RVA,
                             base + yes if yes else 0),
                            CTY_DATA, CTY_CODE)
        res.append(f"{name}:{r}")
    return "，".join(res)


def remove_hook(h, base):
    ok = False
    if hook_status(h, base) == "hooked":
        ok = _write_patch(h, base + HOOK_ENTRY_RVA, HOOK_ENTRY_ORIG)
    if ship_hook_status(h, base) == "hooked":
        ok = _write_patch(h, base + SHIP_HOOK_RVA, SHIP_HOOK_PRO) or ok
    if wing_hook_status(h, base) == "hooked":
        ok = _write_patch(h, base + WING_HOOK_RVA, WING_HOOK_PRO) or ok
    if inv_hook_status(h, base) == "hooked":
        ok = _write_patch(h, base + INV_HOOK_RVA, INV_HOOK_PRO) or ok
    for _name, rva, pro, _hex, _yes in CTY_HOOKS:
        if generic_status(h, base, rva, pro) == "hooked":
            ok = _write_patch(h, base + rva, pro) or ok
    return ok


def wait_and_install(wait_seconds):
    """等 hoi4.exe 出现且代码段可读，立刻装补丁，然后返回。通常只需要几秒。"""
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        pid = P.find_pid("hoi4.exe")
        if pid:
            try:
                h = full_process(pid)
                base = P.module_base(h)
                st = hook_status(h, base)
            except OSError:
                st = None
            if st:
                r = install_hook(h, base)
                r2 = install_ship_hook(h, base)
                r3 = install_wing_hook(h, base)
                r4 = install_inv_hook(h, base)
                r5 = install_cty_hooks(h, base)
                log(f"陆军补丁: {r}，舰船补丁: {r2}，空军补丁: {r3}，登陆制海权补丁: {r4}，登陆其他限制: {r5} (pid {pid})")
                return r is not None
        time.sleep(0.3)
    log("等待 hoi4.exe 超时")
    return False


def apply_air(wait_ready):
    """空军联队：没有找到安全的引擎钩子点，所以等战役加载好后一次性写入(联队经验 >= 300)，写完退出。"""
    deadline = time.time() + wait_ready
    while time.time() < deadline:
        pid = P.find_pid("hoi4.exe")
        if pid:
            try:
                h = full_process(pid)
                base = P.module_base(h)
                players = player_country_indices(h, base)
            except OSError:
                players = None
            if players:
                found, _ = scan_objects(h, {"wing": base + AIRWING_VTABLE_RVA})
                mine = [a for a in found["wing"] if i32(h, a + OFF_WING_COUNTRY) in players]
                if mine:
                    n = tick_wings(h, mine, base + AIRWING_VTABLE_RVA, players)
                    log(f"空军联队: 玩家国家 {sorted(players)}，联队 {len(mine)}，修改 {n} 项；进程退出")
                    return True
        time.sleep(2)
    log("空军联队: 等待战役超时")
    return False


def main():
    global _quiet
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="给运行中的游戏装补丁后退出")
    ap.add_argument("--remove", action="store_true", help="撤销补丁")
    ap.add_argument("--air", action="store_true", help="等战役就绪后一次性写入空军联队经验")
    ap.add_argument("--uninstall", action="store_true", help="清理旧版开机启动项")
    ap.add_argument("--wait-game", type=int, default=300)
    args, game_cmd = ap.parse_known_args()
    _quiet = sys.stdout is None or Path(sys.executable).name.lower() == "pythonw.exe"
    if args.uninstall:
        remove_old_autostart()
        return
    if args.remove:
        pid = P.find_pid("hoi4.exe")
        if pid:
            h = full_process(pid)
            log("补丁已撤销" if remove_hook(h, P.module_base(h)) else "没有可撤销的补丁")
        return
    if args.air:
        sys.exit(0 if apply_air(3600) else 1)
    if game_cmd:  # Steam 启动：先拉起游戏，再起一个只活几秒的安装进程
        import subprocess
        try:
            subprocess.Popen(game_cmd, cwd=str(Path(game_cmd[0]).parent), creationflags=0x00000008)
        except OSError as e:  # 启动项写错(例如多了引号)时在日志里留下原因
            log(f"启动游戏失败: {e!r}；收到的参数: {game_cmd!r}")
            return
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--install"],
                         creationflags=0x00000008 | 0x08000000, close_fds=True)
        log(f"已启动游戏: {game_cmd[0]}")
        return
    sys.exit(0 if wait_and_install(args.wait_game) else 1)


if __name__ == "__main__":
    main()
