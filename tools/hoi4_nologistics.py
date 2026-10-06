#!/usr/bin/env python3
"""HOI4 引擎内补丁工具(纯 Python，不需要任何 mod 文本，装完 Python 立即退出，不常驻)。

原理
----
在 hoi4.exe 进程里给若干引擎函数装一小段机器码(“补丁”)。补丁由引擎自己调用，先判断当前调用方是不是
“玩家国家或其傀儡国”(读国家管理器里的玩家记录 CHuman；傀儡国 = CCountry +0x41C 与 +0x434 都等于玩家国家编号)，
不是就原样执行原函数，所以 AI 国家完全不受影响。补丁随游戏进程存在，读档/换国立即生效；游戏重启后需要重装
(Steam 启动项会自动装)。

当前功能(全部只对玩家国家及其傀儡国生效，除非特别说明)
------------------------------------------------
1. 无补给/燃油消耗 + 至少“训练有素”
   - 陆军师(每次更新)：经验 = 经验总量/兵力，低于 0.3 就抬到 0.3；当前补给低于约 5000 小时就补到 10000 小时；
     燃油补满。补充兵员稀释经验后，下一次更新就会被抬回，永远不低于训练有素。
   - 海军舰船(每次更新)：经验低于 0.3 抬到 0.3。
   - 空军联队(每次更新)：经验低于 300(联队经验的训练有素门槛)抬到 300。
   - 海军/空军只处理经验，不处理补给与燃油。
2. 海军登陆去除限制
   - 无视制海权不足：登陆路线校验里“我方是否控制该海区”对玩家恒为“是”(不再提示 Insufficient Naval Dominance)。
   - 每次登陆的师数上限：对玩家恒为 99。
   - 登陆计划数量上限：对玩家恒为 99。
   - 登陆准备时间：对玩家把“准备时间修正”固定为 -0.99，准备时间约剩原来的 1%。
3. 空降去除限制
   - 空降计划数量上限：对玩家恒为 99。
   - 空降每次师数上限：校验时对玩家直接判定“允许”。
   - 空降准备时间：与海军共用同一补丁(修正 id 0xE)，约剩原来的 1%。
4. 使用 mod 也可以解锁成就(对所有人生效，没有“玩家”的概念)
   - 成就管理器里有个“游戏/mod 未被修改”标志(a2)，由一次字符串比较的结果决定；补丁把这次比较的判断
     `test eax,eax` 改成 `xor eax,eax`，标志恒为真。这和创意工坊那份可解锁成就的 hoi4.exe 的唯一一处改动完全一致。
   - 注意：这会让成就在 mod 状态下也被允许；是否同时放过其他作弊检测我没有验证。
5. 非铁人模式也可以解锁成就(对所有人生效)
   - common/achievements.txt 里每个成就的 possible 都有 `is_ironman = yes`。补丁让 is_ironman 触发器
     把“当前游戏是否铁人”恒当作“是”：`and cl,1` -> `mov cl,1`。
   - 副作用：其他脚本里的 is_ironman = yes/no 也会按“铁人”判断。成就另有 难度>1、开局日期<1936.1.2、
     无自定义难度、游戏规则允许成就 这几条，本脚本不改，不满足仍然不会解锁。
   - 开始界面右下角的奖杯图标(红叉=无法获得成就)由另一个函数判断，其中“非铁人 -> 无法获得成就”也一并改成恒为铁人。

兼容性(防止游戏更新后失效)
--------------------------
- 所有补丁入口都用“特征码”在 hoi4.exe 代码段里定位(跳过地址相关的 4 字节位移)，不再写死地址；
  全局变量(国家管理器)靠一段特征码解码 rip 相对位移得到；各个类的 vtable 靠 RTTI 类名查到。
- 特征码必须在代码段里唯一命中才会安装；找不到/不唯一/被补过的原指令对不上，只会跳过该补丁并写日志，不会乱写。
- 游戏更新后只要这些函数的指令没变，补丁照常安装；如果某个特征码失效，日志里会有“特征码未命中”。
- 不能自动适配的是“结构体字段偏移”(如 师 +0x430 经验总量、国家 +0x41C 宗主编号等)，它们写在机器码里；
  如果更新改了这些结构，补丁的判断条件会不成立(多数情况下表现为“不生效”而不是崩溃)，需要重新分析。

用法
----
    Steam 启动项：  pythonw.exe 本脚本 %command%     (启动游戏 + 只活几秒的安装进程)
    手动安装：      pythonw.exe 本脚本 --install      (游戏已在运行时)
    撤销补丁：      pythonw.exe 本脚本 --remove
    查看特征码定位结果：python 本脚本 --status
    清理旧版开机启动项：python 本脚本 --uninstall
日志：%TEMP%\\hoi4_nologistics.log
"""
import argparse
import ctypes
import os
import re
import struct
import sys
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
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


# ---------------------------------------------------------------------------
# 进程/内存辅助(自包含，不依赖其他文件)
# ---------------------------------------------------------------------------
class _PE32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]


class P:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    nt = ctypes.WinDLL("ntdll")

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
        h = P.k32.OpenProcess(0x1F0FFF, False, pid)
        if not h:
            raise OSError(f"OpenProcess 失败(错误 {ctypes.get_last_error()})")
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
    def exe_path(h):
        P.k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                     ctypes.POINTER(wintypes.DWORD)]
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        P.k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        return Path(buf.value)

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

    @staticmethod
    def alloc_near(h, target, size):
        """在 target 的 ±1.8GB 内分配可执行内存(jmp rel32 够得着)。"""
        P.k32.VirtualAllocEx.restype = ctypes.c_void_p
        P.k32.VirtualAllocEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
                                         wintypes.DWORD, wintypes.DWORD]
        a = max((target - 0x70000000) & ~0xFFFF, 0x10000)
        while a < target + 0x70000000:
            p = P.k32.VirtualAllocEx(h, ctypes.c_void_p(a), size, 0x3000, 0x40)
            if p:
                return p
            a += 0x10000
        return None

    @staticmethod
    def patch_code(h, addr, raw):
        """暂停全部线程再改指令，避免改到一半被执行。"""
        P.nt.NtSuspendProcess(h)
        try:
            return P.write_mem(h, addr, raw)
        finally:
            P.nt.NtResumeProcess(h)


P.k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
P.k32.WriteProcessMemory.argtypes = P.k32.ReadProcessMemory.argtypes


# ---------------------------------------------------------------------------
# 可执行文件映像：特征码查找 / RTTI 查 vtable
# ---------------------------------------------------------------------------
class Image:
    """从磁盘上的 hoi4.exe 读取(始终是未打补丁的原始代码)。"""

    def __init__(self, path):
        d = self.data = Path(path).read_bytes()
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        nsec = struct.unpack_from("<H", d, pe + 6)[0]
        optsz = struct.unpack_from("<H", d, pe + 20)[0]
        self.secs = {}
        for i in range(nsec):
            o = pe + 24 + optsz + 40 * i
            name = d[o:o + 8].rstrip(b"\0").decode()
            vsize, rva, rawsz, raw = struct.unpack_from("<IIII", d, o + 8)
            self.secs[name] = (rva, vsize, raw, rawsz)
        rva, vsize, raw, rawsz = self.secs[".text"]
        self.text_rva, self.text = rva, d[raw:raw + rawsz]
        rva, vsize, raw, rawsz = self.secs[".rdata"]
        self.rdata_rva, self.rdata = rva, d[raw:raw + rawsz]

    def rva_to_off(self, rva):
        for _n, (r, v, raw, rawsz) in self.secs.items():
            if r <= rva < r + rawsz:
                return raw + rva - r
        return None

    def off_to_rva(self, off):
        for _n, (r, v, raw, rawsz) in self.secs.items():
            if raw <= off < raw + rawsz:
                return r + off - raw
        return None

    def bytes_at(self, rva, n):
        o = self.rva_to_off(rva)
        return self.data[o:o + n] if o is not None else b""

    def find_sig(self, sig):
        """特征码(十六进制字节，'??' 通配)在代码段里的全部命中 RVA。"""
        toks = sig.split()
        pat = re.compile(b"".join(b"." if t == "??" else re.escape(bytes([int(t, 16)])) for t in toks), re.S)
        # 用最长的连续固定字节做种子，快速定位候选再用完整正则确认
        best, cur = (0, 0), None
        for i, t in enumerate(toks + ["??"]):
            if t != "??":
                cur = cur if cur is not None else i
            else:
                if cur is not None and i - cur > best[1] - best[0]:
                    best = (cur, i)
                cur = None
        s0, s1 = best
        seed = bytes(int(t, 16) for t in toks[s0:s1])
        hits, start = [], 0
        while True:
            p = self.text.find(seed, start)
            if p < 0:
                break
            base = p - s0
            if base >= 0 and pat.match(self.text, base):
                hits.append(self.text_rva + base)
            start = p + 1
        return hits

    def vtable_of(self, cls):
        """RTTI：类名 -> 主 vtable RVA(COL 偏移为 0 的那个)。"""
        name = (".?AV" + cls + "@@").encode() + b"\0"
        d = self.data
        for m in re.finditer(re.escape(name), d):
            td = self.off_to_rva(m.start() - 16)
            if td is None:
                continue
            for mm in re.finditer(re.escape(struct.pack("<I", td)), self.rdata):
                o = mm.start() - 12
                if o < 0:
                    continue
                sig, offs, _cd = struct.unpack_from("<III", self.rdata, o)
                if sig != 1 or offs != 0:
                    continue
                col_rva = self.rdata_rva + o
                ptr = struct.pack("<Q", self.image_base() + col_rva)
                for m3 in re.finditer(re.escape(ptr), self.rdata):
                    return self.rdata_rva + m3.start() + 8
        return None

    def image_base(self):
        pe = struct.unpack_from("<I", self.data, 0x3C)[0]
        return struct.unpack_from("<Q", self.data, pe + 24 + 24)[0]


# ---------------------------------------------------------------------------
# 特征码与机器码(机器码源码见仓库说明；全部在模拟器里测过)
# ---------------------------------------------------------------------------
SIGS = {
    "ARMY": "48 89 5C 24 10 57 48 83 EC 20 48 8B 01 48 8D 54 24 30 48 8B D9 FF 90 C8 01 00 00",
    "SHIP": "40 57 48 83 EC 20 48 8B F9 48 8B 89 18 07 00 00 48 85 C9 0F 8E ?? ?? ?? ??",
    "WING": "41 55 48 83 EC 60 4C 8B E9 E8 ?? ?? ?? ?? 41 39 45 7C 0F 8E ?? ?? ?? ??",
    "INV": "48 83 EC 28 48 8B C2 48 8D 51 10 48 8B 88 E8 00 00 00 E8 ?? ?? ?? ?? 83 F8 01",
    "GET_DIVCAP": "48 83 EC 28 48 81 C1 B8 05 00 00 48 8D 54 24 30 41 B8 20 00 00 00 E8 ?? ?? ?? ??",
    "GET_PLANCAP": "48 83 EC 28 48 81 C1 B8 05 00 00 48 8D 54 24 30 41 B8 83 01 00 00 E8 ?? ?? ?? ??",
    "GET_AIRPLAN": "48 83 EC 28 48 81 C1 B8 05 00 00 48 8D 54 24 30 41 B8 87 01 00 00 E8 ?? ?? ?? ??",
    "AGAINST": "48 89 5C 24 10 48 89 6C 24 18 48 89 74 24 20 57 48 83 EC 20 48 8B F1 49 8B F9",
    "SKIPCAP": "48 8D 8D B8 05 00 00 41 B8 86 01 00 00 48 8D 54 24 60 E8 ?? ?? ?? ?? 48 8B 08",
    "ACH": "85 C0 0F 94 C3 E8 ?? ?? ?? ??",
    "MGR": "83 3B 00 48 8B 3D ?? ?? ?? ?? 75 04 33 C0 EB 08 48 8B CB E8 ?? ?? ?? ?? 48 8B 5C 24 48 48 63 C8 48 8B 87 10 03 00 00 48 8B 04 C8",
    "IRON": "80 E1 01 38 4F 58 0F 94 C0 48 83 C4 30",
    "ACHUI": "45 0F B6 E8 48 89 95 E0 00 00 00",
}

CAVES = {
    "ARMY": (
        "000000000000000000000000000000005052415041514152488b05e1ffffff488b004885c00f840b010000488b"
        "15d6ffffff483990100100000f85f70000008b90800200003b90200500000f85e500000085d20f84dd00000044"
        "8b81d80100004139d07444443b801c0300000f83c40000004c8b88100300004d85c90f84b40000004f8b0cc14d"
        "85c90f84a70000004139911c0400000f859a000000413991340400000f858d0000004881b9100600000065cd1d"
        "7d0b48c7811006000000ca9a3b488b81380100004885c0741c488b80200100004885c07e10483981200600007d"
        "07488981200600004c6389ec0300004d85c97e414983f940773b4c8b91e00300004d85d2742f4531c049634204"
        "4901c04983c20849ffc975f04d85c07e174d69c0307500004c3981300400007d074c898130040000415a415941"
        "585a58"
    ),
    "SHIP": (
        "0000000000000000000000000000000000000000000000000000000000000000505241504151488b05e3ffffff"
        "4839010f85d1000000488b05c3ffffff488b004885c00f84be000000488b15b8ffffff483990100100000f85aa"
        "0000008b90800200003b90200500000f859800000085d20f84900000004c8b81280700004d85c00f8480000000"
        "4c8b0d8affffff4d39087574458b80d80100004139d07430443b801c030000735f4c8b88100300004d85c97453"
        "4f8b0cc14d85c9744a4139911c04000075414139913404000075384c8b81100700004d85c07e2c4c89c04869c0"
        "3075000048059f86010049c7c1a0860100489949f7f9483981080700007d0748898108070000415941585a58"
    ),
    "WING": (
        "000000000000000000000000000000000000000000000000505241504151488b05ebffffff4839010f85850000"
        "00488b05cbffffff488b004885c07476488b15c4ffffff4839901001000075668b90800200003b902005000075"
        "5885d27454448b81c40900004139d07430443b801c030000733f4c8b88100300004d85c974334f8b0cc14d85c9"
        "742a4139911c04000075214139913404000075184881b91802000080c3c9017d0b48c7811802000080c3c90141"
        "5941585a58"
    ),
    "INV": (
        "000000000000000000000000000000000000000000000000505241504151488b05ebffffff4839017576488b05"
        "cfffffff488b004885c07467488b15c8ffffff4839901001000075578b90800200003b9020050000754985d274"
        "45448b41104139d07430443b801c03000073334c8b88100300004d85c974274f8b0cc14d85c9741e4139911c04"
        "0000751541399134040000750c415941585a58b801000000c3415941585a58"
    ),
    "CONST": (
        "0000000000000000000000000000000000000000000000000000000000000000505241504151488b05e3ffffff"
        "483901756d488b05c7ffffff488b004885c0745e488b15c0ffffff48399010010000754e8b90800200003b9020"
        "050000754085d2743c3b901c03000073344c8b88100300004d85c974284189d04f8b0cc14939c9741039911c04"
        "00007514399134040000750c415941585a58b863000000c3415941585a58"
    ),
    "AGAINST": (
        "0000000000000000000000000000000000000000000000000000000000000000505241504151488b05e3ffffff"
        "483901757e4183f81a74064183f80e7572488b05bbffffff488b004885c07463488b15b4ffffff483990100100"
        "0075538b90800200003b9020050000754585d274413b901c03000073394c8b88100300004d85c9742d4189d04f"
        "8b0cc14939c9741039911c04000075193991340400007511415941585a5848c702487dfeff4889d0c341594158"
        "5a58"
    ),
    "SKIPCAP": (
        "0000000000000000000000000000000000000000000000000000000000000000505241504151488b05e3ffffff"
        "48394500756d488b05c6ffffff488b004885c0745e488b15bfffffff48399010010000754e8b90800200003b90"
        "20050000754085d2743c3b901c03000073344c8b88100300004d85c974284189d04f8b0cc14939e9741039951c"
        "0400007514399534040000750c415941585a58ff2578ffffff415941585a58"
    ),
}

# 特征码 MGR：国家管理器全局指针。命中处 +3 起是 `mov rdi,[rip+disp32]`(7 字节)，解码得到全局地址。
MGR_INSN_OFFSET = 3

# 钩子表：(名称, 特征码键, 覆盖的原指令字节数, 机器码键, 机器码数据字段, “允许”分支相对入口偏移, 该分支校验字节, 类型)
#   数据字段 mgr=国家管理器全局 hvt=CHuman cvt=CCountry svt=CShip tvt=CTaskForce wvt=CAirWing xvt=CStrategicNavy yes=跳转目标
HOOKS = (
    ("陆军:经验/补给/燃油", "ARMY", 5, "ARMY", ("mgr", "hvt"), 0, None, "cave"),
    ("海军:舰船经验", "SHIP", 6, "SHIP", ("mgr", "hvt", "svt", "tvt"), 0, None, "cave"),
    ("空军:联队经验", "WING", 6, "WING", ("mgr", "hvt", "wvt"), 0, None, "cave"),
    ("登陆:无视制海权", "INV", 7, "INV", ("mgr", "hvt", "xvt"), 0, None, "cave"),
    ("海军:每次登陆师数上限", "GET_DIVCAP", 11, "CONST", ("mgr", "hvt", "cvt", "yes"), 0, None, "cave"),
    ("海军:登陆计划数量上限", "GET_PLANCAP", 11, "CONST", ("mgr", "hvt", "cvt", "yes"), 0, None, "cave"),
    ("空降:计划数量上限", "GET_AIRPLAN", 11, "CONST", ("mgr", "hvt", "cvt", "yes"), 0, None, "cave"),
    ("登陆/空降:准备时间", "AGAINST", 5, "AGAINST", ("mgr", "hvt", "cvt", "yes"), 0, None, "cave"),
    ("空降:每次师数上限", "SKIPCAP", 7, "SKIPCAP", ("mgr", "hvt", "cvt", "yes"), 0x43,
     bytes.fromhex("b0014883c428"), "cave"),
    ("成就:mod 校验恒通过", "ACH", 2, None, (), 0, None, "direct"),
    ("成就:非铁人也算铁人", "IRON", 3, None, (), 0, None, "direct"),
    ("成就:状态面板不要求铁人", "ACHUI", 4, None, (), 0, None, "direct"),
)
# 直接改写(不需要机器码)的补丁，键 = 特征码键。
#   ACH：成就管理器的 a2 标志(“游戏/mod 未被修改”)由 test eax,eax;sete bl 得到(eax = 某个字符串比较结果)；
#        把 85 C0(test eax,eax) 改成 31 C0(xor eax,eax)，ZF 恒为 1，bl 恒为 1，a2 恒为真(与创意工坊那份
#        补丁版 hoi4.exe 的唯一一处改动相同：文件偏移 0x16E60A，0x85 -> 0x31)。
#   IRON：脚本触发器 is_ironman 的求值 = (游戏标志 & 1) == 触发器值；成就的 possible 条件里都带 is_ironman = yes。
#        把 `and cl,1`(80 E1 01) 改成 `mov cl,1; nop`(B1 01 90)，等于“当前永远是铁人”，非铁人存档也能解锁。
#   ACHUI：开始界面/游戏内的“能否获得成就”面板函数，第 3 个参数(r8b)是“铁人模式”，非铁人时面板直接判“无法获得成就”；
#        把入口的 `movzx r13d,r8b`(44 0F B6 E8) 改成 `push 1; pop r13`(6A 01 41 5D)，面板恒按铁人处理。
DIRECT_PATCHES = {"ACH": bytes.fromhex("31c0"), "IRON": bytes.fromhex("b10190"), "ACHUI": bytes.fromhex("6a01415d")}
# 需要 vtable 的类
VTABLE_CLASSES = {"hvt": "CHuman", "cvt": "CCountry", "svt": "CShip", "tvt": "CTaskForce",
                  "wvt": "CAirWing", "xvt": "CStrategicNavy"}


def resolve(img):
    """用特征码/RTTI 解析出所有入口、全局变量、vtable。返回 (表, 问题列表)。"""
    R, problems = {}, []
    # 国家管理器全局
    hits = img.find_sig(SIGS["MGR"])
    globs = set()
    for rva in hits:
        o = img.rva_to_off(rva + MGR_INSN_OFFSET)
        insn = img.data[o:o + 7]
        if len(insn) == 7 and insn[:3] == bytes.fromhex("488b3d"):
            globs.add(rva + MGR_INSN_OFFSET + 7 + struct.unpack_from("<i", insn, 3)[0])
    if len(globs) == 1:
        R["mgr"] = globs.pop()
    else:
        problems.append(f"国家管理器全局: 特征码命中 {len(hits)} 处，解码出 {len(globs)} 个不同地址")
    for key, cls in VTABLE_CLASSES.items():
        v = img.vtable_of(cls)
        if v:
            R[key] = v
        else:
            problems.append(f"{cls}: RTTI 未找到 vtable")
    # 各钩子入口
    for name, sigkey, pro_len, cavekey, keys, yes_delta, yes_check, kind in HOOKS:
        hits = img.find_sig(SIGS[sigkey])
        if len(hits) != 1:
            problems.append(f"{name}: 特征码{'未命中' if not hits else '命中 %d 处(不唯一)' % len(hits)}")
            continue
        R["entry:" + name] = hits[0]
    return R, problems


def need_keys(keys, R):
    return all(k in R or k == "yes" for k in keys)


def install_all(h, base, img):
    """安装全部补丁。返回 [(名称, 结果)]。"""
    R, problems = resolve(img)
    out = [("特征码问题", p) for p in problems]
    todo = []
    sigkey_of = {h_[0]: h_[1] for h_ in HOOKS}
    for name, sigkey, pro_len, cavekey, keys, yes_delta, yes_check, kind in HOOKS:
        entry = R.get("entry:" + name)
        if entry is None:
            out.append((name, "特征码未命中，跳过"))
            continue
        pro = img.bytes_at(entry, pro_len)
        cur = P.read_mem(h, base + entry, pro_len)
        if cur != pro and ((kind == "cave" and len(cur) == pro_len and cur[0] == 0xE9)
                           or (kind == "direct" and cur[:len(DIRECT_PATCHES[sigkey])] == DIRECT_PATCHES[sigkey])):
            out.append((name, "已存在"))
            continue
        if cur != pro:
            out.append((name, "进程内指令与文件不符，跳过"))
            continue
        if kind == "cave":
            if not need_keys(keys, R):
                out.append((name, "缺少 vtable/全局变量，跳过"))
                continue
            if yes_delta:
                tgt = entry + yes_delta
                if img.bytes_at(tgt, len(yes_check)) != yes_check:
                    out.append((name, "跳转目标校验失败，跳过"))
                    continue
        todo.append((name, entry, pro, cavekey, keys, yes_delta, kind))
    if not todo:
        return out
    arena = None
    cave_todo = [t for t in todo if t[6] == "cave"]
    if cave_todo:
        arena = P.alloc_near(h, base + img.text_rva + len(img.text) // 2, 0x10000)
        if not arena:
            return out + [("补丁", "分配内存失败")]
    cur_off = 0
    for name, entry, pro, cavekey, keys, yes_delta, kind in todo:
        e = base + entry
        if kind == "direct":
            dp = DIRECT_PATCHES[sigkey_of[name]]
            patch = dp + bytes([0x90]) * (len(pro) - len(dp))
            out.append((name, "安装成功" if P.patch_code(h, e, patch) else "写入失败"))
            continue
        code = bytearray(bytes.fromhex(CAVES[cavekey]))
        vals = []
        for k in keys:
            if k == "mgr":
                vals.append(base + R["mgr"])
            elif k == "yes":
                vals.append(base + entry + yes_delta if yes_delta else 0)
            else:
                vals.append(base + R[k])
        for i, v in enumerate(vals):
            struct.pack_into("<Q", code, 8 * i, v)
        code_off = 8 * len(keys)
        cave = arena + cur_off
        code += pro                                   # 被覆盖的原指令搬进补丁
        jmp_at = len(code)
        code += bytes([0xE9]) + struct.pack("<i", (e + len(pro)) - (cave + jmp_at + 5))
        if not P.write_mem(h, cave, bytes(code)):
            out.append((name, "写入补丁失败"))
            continue
        patch = bytes([0xE9]) + struct.pack("<i", (cave + code_off) - (e + 5)) + bytes([0x90]) * (len(pro) - 5)
        out.append((name, "安装成功" if P.patch_code(h, e, patch) else "写入失败"))
        cur_off += (len(code) + 15) & ~15
    return out


def remove_all(h, base, img):
    R, _problems = resolve(img)
    n = 0
    for name, sigkey, pro_len, *_rest in HOOKS:
        entry = R.get("entry:" + name)
        if entry is None:
            continue
        pro = img.bytes_at(entry, pro_len)
        cur = P.read_mem(h, base + entry, pro_len)
        if len(cur) == pro_len and cur != pro:  # 被改过(跳转或直接补丁)就恢复原指令
            if P.patch_code(h, base + entry, pro):
                n += 1
    return n


def attach(wait_seconds):
    """等 hoi4.exe 出现且代码段可读。返回 (h, base, img) 或 None。"""
    deadline = time.time() + wait_seconds
    img = None
    while time.time() < deadline:
        pid = P.find_pid("hoi4.exe")
        if pid:
            try:
                h = P.open_process(pid)
                base = P.module_base(h)
                if img is None:
                    img = Image(P.exe_path(h))
                if P.read_mem(h, base + img.text_rva, 16) == img.text[:16]:
                    return h, base, img, pid
            except OSError:
                pass
        time.sleep(0.3)
    return None


def main():
    global _quiet
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="给运行中的游戏装补丁后退出")
    ap.add_argument("--remove", action="store_true", help="撤销补丁")
    ap.add_argument("--status", action="store_true", help="只显示特征码定位结果，不写入")
    ap.add_argument("--uninstall", action="store_true", help="清理旧版开机启动项")
    ap.add_argument("--wait-game", type=int, default=300)
    args, game_cmd = ap.parse_known_args()
    _quiet = sys.stdout is None or Path(sys.executable).name.lower() == "pythonw.exe"
    if args.uninstall:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            try:
                winreg.DeleteValue(k, "HOI4NoLogistics")
            except FileNotFoundError:
                pass
        return
    if args.status or args.remove:
        a = attach(args.wait_game if not args.status else 5)
        if not a:
            log("未找到 hoi4.exe")
            return 1
        h, base, img, pid = a
        if args.status:
            R, problems = resolve(img)
            for name, *_ in HOOKS:
                log(f"{name}: {'RVA 0x%X' % R['entry:' + name] if 'entry:' + name in R else '未定位'}")
            for k in ("mgr", "hvt", "cvt", "svt", "tvt", "wvt", "xvt"):
                log(f"{k}: {'0x%X' % R[k] if k in R else '未找到'}")
            for p in problems:
                log("问题: " + p)
        else:
            log(f"已撤销 {remove_all(h, base, img)} 个补丁")
        return
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
    a = attach(args.wait_game)
    if not a:
        log("等待 hoi4.exe 超时")
        sys.exit(1)
    h, base, img, pid = a
    res = install_all(h, base, img)
    log(f"补丁结果 (pid {pid}): " + "；".join(f"{n}:{r}" for n, r in res))


if __name__ == "__main__":
    main()
