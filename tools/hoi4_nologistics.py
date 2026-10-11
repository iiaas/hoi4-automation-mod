#!/usr/bin/env python3
"""HOI4 引擎内补丁工具(纯 Python，不需要 mod 脚本；装完补丁就退出，不常驻)。

原理
----
在 hoi4.exe 进程里给一些引擎函数挂上小段机器码。调用时先判断是不是“玩家本国”(不含傀儡国)，
不是就照常执行原函数，所以 AI 国家不受影响。游戏每次启动都要重装(Steam 启动项会自动装)。
除非特别注明，下面的功能都只对玩家本国生效。

功能
----
1. 陆军无补给、燃油消耗
   - 补给低于约 5000 小时就补到 10000 小时，燃油始终补满。

2. 部队经验至少“训练有素”
   - 陆军师经验低于 0.3、舰船经验低于 0.3、空军联队经验低于 300 时，抬到训练有素。
   - 同时让引擎重算修正，否则界面显示训练有素、实际修正还是新兵。

3. 登陆与空降去除限制
   - 登陆无视制海权。
   - 登陆、空降的计划数量上限和每次师数上限都改为 99。
   - 登陆、空降准备时间约剩原来的 1%。

4. 运输船不会被拦截
   - 补给线、贸易线上的运输船不会被敌方海军破交任务攻击(已实测)。
   - 海上运输的部队(登陆、跨海调兵等)不会被敌方海军或空军截击(未实测)。

5. 自动解锁科技(每天)
   - 有文件夹、不在旧式坦克线和旧式战机线里的科技，到了 start_year 当年 1 月 1 日就解锁；
     会正常发蓝图等奖励，不会重复发。

6. 自动解锁 MIO 特性(每天)
   - 所有可见 MIO 的未解锁特性，逐个 +1 规模并解锁(无视前置条件)。

7. 专项项目
   - 自动完成(每天)：没完成、而且已满足开始条件(如所需科技)的项目直接完成。
   - 完成时不弹窗(对所有人生效)。

8. 成就(对所有人生效)
   - 使用 mod 也能解锁成就。
   - 非铁人模式也能解锁成就：is_ironman 恒为“是”，所以其他脚本里的 is_ironman 判断也会受影响。
   - 难度、开局日期、游戏规则等其他成就条件不变。

9. AI 控制(默认全部关闭，用 mod 决议“AI 控制”分类里的按钮开关)
   让原版 AI 替玩家做下面几件事，四个开关互相独立：
   - AI 控制军队：陆军(战线、进攻/登陆/空降计划、编组、将领)和空军(任务、转场)。
   - AI 选择国策：按原版 AI 逻辑选国策，不会取消你手选的国策。
   - AI 贸易：按需进口资源、取消多余的贸易。
   - AI 生产：只调整陆空产线的工厂数、把产线换成同一大类的更新装备(如 36 式步枪 -> 39 式步枪、
     36 年战斗机 -> 40 年战斗机，按装备原型判断)；不新增或删除产线，不管海军。
     工厂分配沿用原版逻辑，只是不为新产线预留工厂(原版会给想新建的产线留工厂，新建被丢弃后这些工厂就空着)。
   其他事情(外交、法律、顾问、建造、海军、情报等)AI 不会替你做。

   实现要点：
   - 引擎给玩家也建了一套国家 AI(政治、外交、内政、军事四个大臣等)，只是不运行。补丁让它对玩家运行，
     按打开的开关决定跑哪些大臣：只开国策跑政治大臣，否则跑前 4 个大臣(贸易要用军事大臣算出的数据)。
   - AI 下的命令经过过滤，只放行打开的开关对应的命令，其余一律丢弃。
     陆空命令按白名单(AI_WHITELIST)放行；生产命令还会剔除海军产线、并检查只能升级同类装备。
   - 原版 AI 先给每种装备打分，再按分数把军工分给各装备，没有产线的装备会新建产线。补丁让玩家没有
     同原型陆空产线的装备打分为 0(和原版给 0 分的路径相同)，工厂就全部按原版规则分给已有产线的装备。
   - AI 雇顾问、修铁路走的是玩家操作也会用的发命令入口，按调用来源单独拦截，你自己的操作不受影响。
   - 开关只认存档里的决议旗标(autocore_*_ai，值 77x0 = 关、77x1 = 开)，每次 AI 更新时重新计算，
     所以读档、开新局都会自动对上。
   - 顺带修复了引擎对玩家 AI 的两个问题：
     * 控制区变更时引擎不通知玩家的 AI 将军，运行久了会崩溃，补丁补上通知；
     * AI 新建集团军时界面会自动选中它，导致生产等面板被关掉，开着 AI 控制军队时不再自动选中
       (副作用：你自己新建集团军后也不会自动选中)。
   - 查看开关状态：pythonw 本脚本 --ai status

兼容性
------
- 补丁位置都用特征码在 hoi4.exe 里查找，类用 RTTI 类名查找，不写死地址。
- 某个特征码找不到或不唯一时，只跳过对应补丁并写日志，不会乱改。
- 结构体字段偏移大多写在机器码里；已知会随版本变化的(装备原型字段)在安装时从引擎代码里读出实际值再填入。
- 已核对的游戏版本：1.19.3.0.c01a、1.19.3.0.3fba(所有特征码在两个版本都唯一命中)。

用法
----
    Steam 启动项：  pythonw.exe 本脚本 %command%     (启动游戏并自动安装)
    手动安装：      pythonw.exe 本脚本 --install      (游戏已在运行时)
    撤销补丁：      pythonw.exe 本脚本 --remove
    查看特征码结果：python 本脚本 --status
    查看 AI 开关：  python 本脚本 --ai status
    清理旧版开机启动项：python 本脚本 --uninstall
日志：%TEMP%\\hoi4_nologistics.log
"""
import argparse
import ctypes
import json
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
        """特征码(十六进制字节，'??' 通配)在代码段里的全部命中 RVA。用 " | " 分隔多个候选(不同游戏版本)时返回各候选命中的并集。"""
        if " | " in sig:
            return sorted({h for alt in sig.split(" | ") for h in self.find_sig(alt)})
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
    "WUPD": "40 57 48 83 EC 40 48 8B 41 38",
    "INV": "48 83 EC 28 48 8B C2 48 8D 51 10 48 8B 88 E8 00 00 00 E8 ?? ?? ?? ?? 83 F8 01",
    "GET_DIVCAP": "48 83 EC 28 48 81 C1 B8 05 00 00 48 8D 54 24 30 41 B8 20 00 00 00 E8 ?? ?? ?? ??",
    "GET_PLANCAP": "48 83 EC 28 48 81 C1 B8 05 00 00 48 8D 54 24 30 41 B8 83 01 00 00 E8 ?? ?? ?? ??",
    "PLANFULL": "48 89 5C 24 10 48 89 74 24 18 57 48 83 EC 20 4C 8B 99 68 01 00 00 33 DB 48 63 81 74 01 00 00 48 8B F1 49 8D 3C C3 4C 3B DF 74 6F 0F 1F 44 00 00 49 8B 03 4C 8B 80 80 00 00 00 48 63 80 8C 00 00 00 4D 8D 14 C0 4D 3B C2 74 47 66 0F 1F 44 00 00 49 8B 08 48 8B 81 98 00 00 00 48 63 89 A4 00 00 00 4C 8D 0C C8 49 3B C1 74 1E 66 0F 1F 44 00 00 48 8B 08 8D 53 01 83 79 30 03 0F 45 D3 48 83 C0",
    "AIRPLANFULL": "48 89 5C 24 10 48 89 74 24 18 57 48 83 EC 20 4C 8B 99 68 01 00 00 33 DB 48 63 81 74 01 00 00 48 8B F1 49 8D 3C C3 4C 3B DF 74 6F 0F 1F 44 00 00 49 8B 03 4C 8B 80 80 00 00 00 48 63 80 8C 00 00 00 4D 8D 14 C0 4D 3B C2 74 47 66 0F 1F 44 00 00 49 8B 08 48 8B 81 98 00 00 00 48 63 89 A4 00 00 00 4C 8D 0C C8 49 3B C1 74 1E 66 0F 1F 44 00 00 48 8B 08 8D 53 01 83 79 30 04 0F 45 D3 48 83 C0",
    "GET_AIRPLAN": "48 83 EC 28 48 81 C1 B8 05 00 00 48 8D 54 24 30 41 B8 87 01 00 00 E8 ?? ?? ?? ??",
    "AGAINST": "48 89 5C 24 10 48 89 6C 24 18 48 89 74 24 20 57 48 83 EC 20 48 8B F1 49 8B F9",
    "SKIPCAP": "48 8D 8D B8 05 00 00 41 B8 86 01 00 00 48 8D 54 24 60 E8 ?? ?? ?? ?? 48 8B 08",
    "ACH": "85 C0 0F 94 C3 E8 ?? ?? ?? ??",
    "MGR": "83 3B 00 48 8B 3D ?? ?? ?? ?? 75 04 33 C0 EB 08 48 8B CB E8 ?? ?? ?? ?? 48 8B 5C 24 48 48 63 C8 48 8B 87 10 03 00 00 48 8B 04 C8",
    "IRON": "80 E1 01 38 4F 58 0F 94 C0 48 83 C4 30",
    "ACHUI": "45 0F B6 E8 48 89 95 E0 00 00 00",
    "DAILY": "48 89 5C 24 18 55 56 57 41 54 41 55 41 56 41 57 48 8D 6C 24 C0 48 81 EC 40 01 00 00 48 8B F9 41 B9 02 00 00 00",
    "COMPLETE": "4C 89 4C 24 20 53 48 83 EC 50 49 8B D9",
    "VECINS": "48 89 5C 24 08 48 89 6C 24 10 48 89 74 24 18 57 41 56 41 57 48 83 EC 20 48 63 41 0C 4C 8B F1 8B 49 08 49 8B D8 48 63 EA 3B C1 0F 85 ?? ?? ?? ?? FF C0 66 0F 6E C1 49 8B 4E 10 41 B8 08 00 00 00 0F 5B C0 F3 0F 59 05 ?? ?? ?? ?? F3 0F 2C F0 3B C6 0F 4F F0 48 8B 01 8B D6 48 C1 E2 03 FF 50 08 48 8B 0B 4C 8D 3C ED 00 00 00 00 4D 8B C7 48 8B F8 49 89 0C 07 48 8B C8",
    "VALIDFOCUS": "48 89 5C 24 08 48 89 74 24 10 57 48 83 EC 40 48 8B 79 30 48 85 FF 74 64 48 8D 35 ?? ?? ?? ?? 48 89 74 24 28 33 C0 48 89 44 24 30 88 44 24 38",
    "SETFOCUS": "4C 8B DC 49 89 5B 18 55 56 57 41 54 41 55 41 56 41 57 48 83 EC 50 48 8B F2 48 8B D9",
    "CONTAINS": "48 89 5C 24 08 48 89 74 24 10 48 89 7C 24 18 41 56 48 83 EC 20 48 8B 3A",
    "ADDSIZE": "48 89 5C 24 08 48 89 74 24 10 57 48 83 EC 40 8B F2 48 8B F9 48 81 C1 20 01 00 00",
    "UNLOCK": "48 89 5C 24 10 57 48 83 EC 50 48 8D 05 ?? ?? ?? ??",
    "VISIBLE": "40 53 48 83 EC 20 48 8B D9 48 8B 89 18 01 00 00 48 85 C9 75 08",
    "SETTECH": "48 89 5C 24 10 55 56 57 41 54 41 55 41 56 41 57 48 83 EC 70 4C 8B E2 48 8B E9",
    "SPEXEC": "48 89 54 24 10 55 53 56 57 41 54 41 55 41 56 41 57 48 8D 6C 24 C8 48 81 EC 38 01 00 00 48 8B FA",
    "SPISCOMP": "48 8B 49 28 E9 ?? ?? ?? ?? CC CC CC CC CC CC CC 48 8B 49 28",
    "SPCANSTART": "48 89 5C 24 08 48 89 6C 24 10 48 89 74 24 20 57 48 83 EC 50 48 8B FA 48 8B D9",
    "SPPOPUP": "48 89 5C 24 10 48 89 6C 24 18 56 57 41 56 48 83 EC 30 4C 8B F2 48 8B F1 80 3D ?? ?? ?? ?? 00",
    "AIUPD": "48 89 5C 24 08 57 48 83 EC ?? 48 8B F9 E8 ?? ?? ?? ?? 48 8B D8 48 85 C0 0F 84 ?? ?? ?? ?? 80 7F 60 00 | 48 89 5C 24 08 57 48 83 EC ?? 48 8B F9 E8 ?? ?? ?? ?? 48 8B D8 48 85 C0 74 ?? 80 7F 60 00",
    "AREASYNC": "48 89 5C 24 18 48 89 6C 24 20 56 57 41 56 48 83 EC 20 4C 89 7C 24 48 49 8B E8 4C 63 79 54 48 8B DA",
    "HRESOLVE": "48 83 EC 28 8B 01 3D 68 12 00 00 76 ?? 48 8B 05 ?? ?? ?? ?? 48 85 C0 74 ?? 48 8B D1 48 8B C8 E8 ?? ?? ?? ?? 48 85 C0 74 ?? 48 8B 00 48 83 C4 28 C3",
    "POSTA": "48 89 5C 24 10 57 48 83 EC 40 48 8B F9 48 8B DA 48 8B 0D ?? ?? ?? ?? 48 8B 01 FF ?? ?? ?? ?? ?? 8B 17 44 8B 00",
    "RS_ADV": "00 00 48 8B CF E8 ?? ?? ?? ?? 48 8B D3 48 8B C8 E8 ?? ?? ?? ?? 40 B7 01 33 DB 48 85 DB",
    "RS_RAILAI": "41 B8 01 00 00 00 48 8B 54 24 48 48 8D 4C 24 30 E8 ?? ?? ?? ?? 4C 8B 54 24 40 4C 8B 74",
    "RS_RAILA": "8B C8 E8 ?? ?? ?? ?? 4C 8B F8 49 8B D7 49 8B CE E8 ?? ?? ?? ?? EB A7 CC CC CC CC CC 48",
    "RS_RAILB": "8B C8 E8 ?? ?? ?? ?? 48 8B F8 48 8B D7 49 8B CC E8 ?? ?? ?? ?? 48 8B 9C 24 88 00 00 00",
    "RS_RAILC": "DD 75 D0 45 0F B6 CD 45 8B C4 49 8B D6 48 8B CE E8 ?? ?? ?? ?? 48 8B 5C 24 68 48 8B 6C",
    "CONVRAID": "48 89 5C 24 10 4C 89 44 24 18 55 56 57 41 54 41 55 41 56 41 57 48 83 EC 40 49 8B F1 4C 8B EA 48",
    "TRANSNAV": "48 89 5C 24 20 4C 89 44 24 18 48 89 54 24 10 55 56 57 41 54 41 55 41 56 41 57 48 81 EC 80 00 00 00 0F 29 74",
    "TRANSAIR": "48 89 5C 24 08 48 89 74 24 10 48 89 7C 24 18 55 41 56 41 57 48 8D AC 24 70 FF FF FF 48 81 EC 90",
    "TECHARR": "48 83 EC 38 4C 63 42 38 41 8D 40 FF 3B 81 ?? ?? ?? ?? 7D ?? 85 C0 78 ?? 48 8B 81 ?? ?? ?? ??",
    # 运输船所属国字段：从类的构造函数里读(开头的 lea 必须指向该类 vtable，见 resolve)
    "CTOR_TRANSFER": "48 8D 05 ?? ?? ?? ?? 48 89 01 48 83 C1 ?? E8 ?? ?? ?? ?? 90 48 8B 05 ?? ?? ?? ?? 49 89 46 ?? 49 8D 4E ?? E8 ?? ?? ?? ?? 90 33 ED 49 89 6E ?? 8B 03 41 89 46 ??",
    "CTOR_CONVOY": "48 8D 05 ?? ?? ?? ?? 48 89 01 8B 02 89 41 ?? 48 8D 05 ?? ?? ?? ?? 48 89 41 ?? 45 33 FF 4C 89 79 ?? 44 89 79 ?? 4C 89 79 ??",
    "ARCHOFF": "48 8D 4B 40 E8 ?? ?? ?? ?? 48 8B 88 F0 03 00 00 49 3B CF 74 0D 4C 39 B9 ?? ?? ?? ??",
    "POSTB": "40 53 48 83 EC 40 80 3D ?? ?? ?? ?? 00 48 8B D9 0F 84 ?? ?? ?? ?? 80 3D ?? ?? ?? ?? 00 75 ?? 48 8B CA E8 ?? ?? ?? ??",
    "SPFACTORY": "40 53 48 83 EC 20 B9 E8 02 00 00",
    # 内政大臣给陆空装备打分的循环里调用打分函数的位置(+40 是 call)：打分函数入口 = call 目标，
    # 只处理从这里调用的那次(返回地址 = +45)；海军装备的打分循环是另一处调用，不受影响
    "PRODWSITE": "8B D7 48 8B CE E8 ?? ?? ?? ?? 49 8B 45 00 48 8D 4D C0 48 89 4C 24 20 4C 8D 8D 88 00 00 00 0F 28 D0 48 8B 14 D8 49 8B CF E8 ?? ?? ?? ?? F2 41 0F 11 04 DE",
}

CAVES = {
    "ARMY": (
        "000000000000000000000000000000005052415041514152488b05e1ffffff488b004885c00f84cb000000488b"
        "15d6ffffff483990100100000f85b70000008b90800200003b90200500000f85a500000085d20f849d00000044"
        "8b81d80100004139d00f858d0000004881b9100600000065cd1d7d0b48c7811006000000ca9a3b488b81380100"
        "004885c0741c488b80200100004885c07e10483981200600007d07488981200600004c6389ec0300004d85c97e"
        "414983f940773b4c8b91e00300004d85d2742f4531c0496342044901c04983c20849ffc975f04d85c07e174d69"
        "c0307500004c3981300400007d074c898130040000415a415941585a58"
    ),
    "SHIP": (
        "0000000000000000000000000000000000000000000000000000000000000000505241504151488b05e3ffffff"
        "4839010f8598000000488b05c3ffffff488b004885c00f8485000000488b15b8ffffff4839901001000075758b"
        "90800200003b9020050000756785d274634c8b81280700004d85c074574c8b0d9affffff4d3908754b458b80d8"
        "0100004139d0753f4c8b81100700004d85c07e334c89c04869c03075000048059f86010049c7c1a08601004899"
        "49f7f9483981080700007d0e48898108070000c6810008000001415941585a58"
    ),
    "WING": (
        "000000000000000000000000000000000000000000000000000000000000000050515241504151415241534883"
        "ec20488b05daffffff4839017563488b05beffffff488b004885c07454488b15b7ffffff483990100100007544"
        "8b90800200003b9020050000753685d27432448b81c40900004139d075264881b91802000080c3c9017d1948c7"
        "811802000080c3c901488b0581ffffff4885c07402ffd04883c420415b415a415941585a5958"
    ),
    "INV": (
        "000000000000000000000000000000000000000000000000505241504151488b05ebffffff4839017546488b05"
        "cfffffff488b004885c07437488b15c8ffffff4839901001000075278b90800200003b9020050000751985d274"
        "15448b41104139d0750c415941585a58b801000000c3415941585a58"
    ),
    "CONST": (
        "0000000000000000000000000000000000000000000000000000000000000000505241504151488b05e3ffffff"
        "483901755d488b05c7ffffff488b004885c0744e488b15c0ffffff48399010010000753e8b90800200003b9020"
        "050000753085d2742c3b901c03000073244c8b88100300004d85c974184189d04f8b0cc14939c9750c41594158"
        "5a58b863000000c3415941585a58"
    ),
    "AGAINST": (
        "0000000000000000000000000000000000000000000000000000000000000000505241504151488b05e3ffffff"
        "483901756e4183f81a74064183f80e7562488b05bbffffff488b004885c07453488b15b4ffffff483990100100"
        "0075438b90800200003b9020050000753585d274313b901c03000073294c8b88100300004d85c9741d4189d04f"
        "8b0cc14939c97511415941585a5848c702487dfeff4889d0c3415941585a58"
    ),
    # 同 CONST，但对玩家返回 0(“计划数已满”判断恒为否)
    "ZERO": (
        "0000000000000000000000000000000000000000000000000000000000000000505241504151488b05e3ffffff"
        "483901755d488b05c7ffffff488b004885c0744e488b15c0ffffff48399010010000753e8b90800200003b9020"
        "050000753085d2742c3b901c03000073244c8b88100300004d85c974184189d04f8b0cc14939c9750c41594158"
        "5a5831c0909090c3415941585a58"
    ),
    "SKIPCAP": (
        "0000000000000000000000000000000000000000000000000000000000000000505241504151488b05e3ffffff"
        "48394500755d488b05c6ffffff488b004885c0744e488b15bfffffff48399010010000753e8b90800200003b90"
        "20050000753085d2742c3b901c03000073244c8b88100300004d85c974184189d04f8b0cc14939e9750c415941"
        "585a58ff2588ffffff415941585a58"
    ),
    "AIUPD": (
        "000000000000000000000000000000000000000000000000505241504151488b05dbffffff488b004885c00f84"
        "5b010000488b15d0ffffff483990100100000f85470100008b90800200003b90200500000f853501000085d20f"
        "842d0100003b901c0300000f83210100004c8b80100300004d85c00f84110100004d8b04d04d85c00f84040100"
        "004c3941080f85fa0000004c8b0d77ffffff4989492049ff41284531db498b80300200004885c0746d8b501448"
        "8b40084885c0746181fa00100000775985d27455ffca4c8d045249c1e004460fb74400284181f8151e00007506"
        "4183cb01ebdd4181f81f1e000075094181cb00010000ebcb4181f8291e000075094181cb00000100ebb94181f8"
        "331e000075b04181cb00000001eba7458919ba04000000418039017414664183790200750cba01000000418079"
        "0101752d493949087422488b41204885c0743e448b412c4183f8057c34458941184c8b004d8941104989490889"
        "512ceb20493949087512488b41204d8b41104c8900418b511889512c49c7410800000000415941585a58"
    ),
    "AIGATE": (
        "000000000000000000000000000000000000000000000000000000000000000000000000000000005052415048"
        "8b05ddffffff48394424187421488b05dfffffff4885c0747e48394424187577488b05c4ffffff803801756beb"
        "0c488b05b6ffffff833800745d488b0592ffffff488b004885c0744e488b158bffffff48399010010000753e8b"
        "90800200003b9020050000753085d2742c3b901c03000073244c8b80100300004d85c074184d8b04d04d85c074"
        "0f4c39c1750a41585a58b801000000c341585a58"
    ),
    "AREASYNC": (
        "000000000000000000000000000000000000000000000000535657415441554156488b05d8ffffff4885c0747e"
        "488b40204885c0747548394108746f83782c047c69488b58204885db7460488b5b184885db74574c8b1dadffff"
        "ff4c391b754b488b73188b7b244885f6743f81ff0001000077374989cc4989d54d89c64883ec2885ff7e19ffcf"
        "488b0cfe4885c974f14c89ea4d89f0ff1574ffffffebe34883c4284c89e14c89ea4d89f0415e415d415c5f5e5b"
    ),
    "POSTA": (
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "0000000000000000000000000000000000000050488b442408483b05cbffffff744b483b05d2ffffff7513488b"
        "442468483b05bcffffff7434e998000000483b05beffffff0f858b000000488b842488000000483b05b1ffffff"
        "757a488b8424e8000000483b0588ffffff7569488b056fffffff4885c0745d8338007458488b054effffff488b"
        "004885c0744941504c8b0545ffffff4c3980100100007535448b8080020000443b802005000075254585c07420"
        "443b01751b4158584883ec284889d1488b01ba01000000ff104883c42831c0c3415858"
    ),
    "CONVRAID": (
        "0000000000000000000000000000000050524150488b05e5ffffff488b004885c074544c8b05deffffff4c3980"
        "1001000075448b90800200003b9020050000753685d274323b901c030000732a4c8b80100300004d85c0741e4d"
        "8b04d04d85c07415488b5424084885d2740b4c394238750541585a58c341585a58"
    ),
    "TRANSNAV": (
        "0000000000000000000000000000000050415041514989d14d85c97440488b05dcffffff488b004885c074314c"
        "8b05d5ffffff4c3980100100007521448b8080020000443b802005000075114585c0740c453b41587506415941"
        "5858c34159415858"
    ),
    "TRANSAIR": (
        "0000000000000000000000000000000050415041514c8b4c24404d85c97440488b05daffffff488b004885c074"
        "314c8b05d3ffffff4c3980100100007521448b8080020000443b802005000075114585c0740c453b4158750641"
        "59415858c34159415858"
    ),
    "POSTB": (
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "00505241504151488b05abfcffff4885c00f84450200008038020f843c0200008338000f8433020000488b0579"
        "fcffff488b004885c00f84200200004c8b056efcffff4c3980100100000f850c020000448b8080020000443b80"
        "200500000f85f80100004585c00f84ef010000448b0a4539c10f85e30100004c8b09488b0536fcffff4c3b0d37"
        "fcffff74584c3b0d36fcffff744f4c3b0d35fcffff74464c3b0d34fcffff744c4c3b0d33fcffff74524c3b0d32"
        "fcffff74498038010f857c0100004c8d0538fcffffb8600000004d39080f84850100004983c008ffc875efe95a"
        "010000807801010f846e010000e94b010000807802010f845f010000e93c010000807803010f85320100005153"
        "5657415441554889ce4d89cc4889e34883e4f04883ec204c3b25bdfbffff0f8489000000488d4e28ff15b5fbff"
        "ff4885c00f84ee000000488b0dadfbffff4839080f85de000000488bb8880000004885ff0f84ce000000488d4e"
        "30ff1582fbffff4885c00f84bb000000488b88f0030000488b97f00300004885c90f84a40000004885d20f849b"
        "0000004c8b81d80400004d85c04c0f44c14c8b8ad80400004d85c94c0f44ca4d39c8757aeb6b8b7e3485ff7e71"
        "81ff0002000077693b7e4c75644531e44531ed4139fd733f488b4e284a8d0ce9ff1509fbffff4885c07427488b"
        "0d05fbffff483908751b488b46284a8b0ce84a890ce0488b4640428b0ca842890ca041ffc441ffc5ebbc4585e4"
        "7415448966344489664c4889dc415d415c5f5e5b59eb294889dc415d415c5f5e5b59415941585a584883ec2848"
        "89c9488b01ba01000000ff104883c42831c0c3415941585a58"
    ),
    "PRODW": (
        "00000000000000000000000000000000000000000000000000000000000000000000000000000000488b042448"
        "3b05edffffff0f851d010000488b05d0ffffff4885c00f840d010000807803010f85030100004c8b15beffffff"
        "4d85d20f84f3000000488b0596ffffff488b004885c00f84e00000004c8b1d8bffffff4c3998100100000f85cc"
        "000000448b98800200004585db0f84bc000000443b98200500000f85af0000004885c90f84a6000000443b5908"
        "0f859c0000004885d20f8493000000488b82f00300004885c00f84830000004c8b98d80400004d85db4c0f44d8"
        "565753488b81680f00004885c07463488b7058486378644885f674564885ff7e4a4881ff001000007748488b06"
        "4885c074304c3910752b488b80880000004885c0741f488b80f00300004885c07413488b98d80400004885db48"
        "0f44d84c39db74104883c60848ffcf75bf5b5f5e0f57c0c35b5f5e"
    ),
    "FOCUS": (
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "00eb603f1d9f038f3f9f03c7619f03ff839f0337a69f0387c89f03bfea9f03f70ca0032f2fa0037f51a003b773"
        "a003ef95a00327b8a00377daa003affca003e71ea1031f41a1036f63a103a785a103dfa7a10317caa10367eca1"
        "039f0ea203d730a20350515241504151415241535356574154415541564157554883ec504989cc488b05f1feff"
        "ff488b004885c00f84e0040000488b15e6feffff483990100100000f85cc0400008b90800200003b9020050000"
        "0f85ba04000085d20f84b20400003b901c0300000f83a60400004c8b88100300004d85c90f84960400004189d0"
        "4f8b2cc14d85ed0f84860400004d396c24080f857b040000488b1df9feffff4c3923741c4c892348c743080000"
        "0000488dbb20020000b90002000031c0f348ab48ff430848833da4feffff000f84c30100004d8bbd600f00004d"
        "85ff0f84b301000049638f940000004885c90f8ea30100004d8bb7880000004d85f60f84930100004989cf31ed"
        "4c39fd0f8d85010000498b34ee48ffc54885f674eb488bbe600100004885ff74df807f400074d98b87dc030000"
        "3986740100007dcb488b9f800300004885db74bf488b4318488b4b20488d53084883f90f7604488b53084883f8"
        "0d750f48b961726d6f75725f6648390a74944883f810751348b96169725f7465636848390a0f847bffffff8b8f"
        "d803000081f9900700007c2f81e99007000083f9180f835effffff488d05f2fdffff8b0488488b155efdffff48"
        "8b123982680400000f8e3effffff4881ec000100000f57c00f114424200f114424300f114424400f114424500f"
        "114424600f114424700f118424800000000f118424900000000f118424a00000000f118424b00000000f118424"
        "c00000000f118424d00000000f118424e00000000f118424f0000000488d8424a00000004889442478c7842484"
        "00000001000000488d8424b000000048898424a0000000c68424a8000000014889bc24c0000000410f1045080f"
        "118424d8000000488d4c2420488d9424d0000000ff15e7fcffff4881c400010000e972feffff48833dabfcffff"
        "000f840701000048833da5fcffff000f84f900000048833d9ffcffff000f84eb00000048833d99fcffff000f84"
        "dd000000498b85680f00004885c00f84cd0000004c8bb0300100004d85f60f84bd0000004c63b83c01000031ed"
        "4c39fd0f8dab000000498b34ee48ffc54885f674eb48833d55fcffff00740d4889f1ff154afcffff84c074d448"
        "8b86100100004885c074c8488b78304885ff74bf4c63603c4d85e47eb6488b0501fcffff48390775aabbd80300"
        "004983fc017e18bb0800000081fb0010000073924839041f740583c308ebed4889f9488d9640010000ff15d1fb"
        "ffff84c0751a4889f1ba01000000ff15c7fbffff4889f14889faff15c3fbffff4801df49ffcc7fcae94cffffff"
        "48833dc6fbffff000f845b01000048833dc0fbffff000f844d01000048833dbafbffff000f843f01000048833d"
        "b4fbffff000f8431010000488b1daffbffff4c8b73184d85f67516ff1598fbffff4885c00f84120100004989c6"
        "48894318498b85a80f00004885c00f84fb000000488b40184885c00f84ee0000004c63781c488b70104885f60f"
        "84dd0000004d85ff0f8ed40000004889f1ff1538fbffff84c00f85b40000004889f131d2ff152dfbffff84c00f"
        "84a10000008b46184189869000000041c7868c000000174c000041c64661004881ec000100000f57c00f114424"
        "200f114424300f114424400f114424500f114424600f114424700f118424800000000f118424900000000f1184"
        "24a00000000f118424b00000000f118424c00000000f118424d00000000f118424e00000000f118424f0000000"
        "410f1045080f114424284c89f1488d542420ff157bfaffff4881c4000100004881c6c001000049ffcfe923ffff"
        "ff4883c4505d415f415e415d415c5f5e5b415b415a415941585a5958"
    ),
}

# 特征码 MGR：国家管理器全局指针。命中处 +3 起是 `mov rdi,[rip+disp32]`(7 字节)，解码得到全局地址。
MGR_INSN_OFFSET = 3

# 钩子表：(名称, 特征码键, 覆盖的原指令字节数, 机器码键, 机器码数据字段, “允许”分支相对入口偏移, 该分支校验字节, 类型)
#   数据字段 mgr=国家管理器全局 hvt=CHuman cvt=CCountry svt=CShip tvt=CTaskForce wvt=CAirWing xvt=CStrategicNavy yes=跳转目标
HOOKS = (
    ("陆军:经验/补给/燃油", "ARMY", 5, "ARMY", ("mgr", "hvt"), 0, None, "cave"),
    ("海军:舰船经验", "SHIP", 6, "SHIP", ("mgr", "hvt", "svt", "tvt"), 0, None, "cave"),
    ("空军:联队经验", "WING", 6, "WING", ("mgr", "hvt", "wvt", "wupd"), 0, None, "cave"),
    ("登陆:无视制海权", "INV", 7, "INV", ("mgr", "hvt", "xvt"), 0, None, "cave"),
    ("海军:每次登陆师数上限", "GET_DIVCAP", 11, "CONST", ("mgr", "hvt", "cvt", "yes"), 0, None, "cave"),
    ("海军:登陆计划数量上限", "GET_PLANCAP", 11, "CONST", ("mgr", "hvt", "cvt", "yes"), 0, None, "cave"),
    ("空降:计划数量上限", "GET_AIRPLAN", 11, "CONST", ("mgr", "hvt", "cvt", "yes"), 0, None, "cave"),
    ("海军:登陆计划已满判断", "PLANFULL", 5, "ZERO", ("mgr", "hvt", "cvt", "yes"), 0, None, "cave"),
    ("空降:计划已满判断", "AIRPLANFULL", 5, "ZERO", ("mgr", "hvt", "cvt", "yes"), 0, None, "cave"),
    ("登陆/空降:准备时间", "AGAINST", 5, "AGAINST", ("mgr", "hvt", "cvt", "yes"), 0, None, "cave"),
    ("空降:每次师数上限", "SKIPCAP", 7, "SKIPCAP", ("mgr", "hvt", "cvt", "yes"), 0x43,
     bytes.fromhex("b0014883c428"), "cave"),
    ("每日:MIO/科技/专项项目", "DAILY", 5, "FOCUS", ("mgr", "hvt", "complete", "vecins", "setfocus", "validfocus", "tmv", "contains", "addsize", "unlock", "visible", "setfn",
      "spexec", "spiscomp", "spcanstart", "spfactory", "bss"), 0, None, "cave"),
    ("运输船:海军破交不攻击玩家运输船", "CONVRAID", 5, "CONVRAID", ("mgr", "hvt"), 0, None, "cave"),
    ("运输船:海军不截击玩家运输船", "TRANSNAV", 5, "TRANSNAV", ("mgr", "hvt"), 0, None, "cave"),
    ("运输船:空军不截击玩家运输船", "TRANSAIR", 5, "TRANSAIR", ("mgr", "hvt"), 0, None, "cave"),
    ("专项项目:完成不弹窗", "SPPOPUP", 1, None, (), 0, None, "direct"),
    ("AI陆军:状态维护", "AIUPD", 5, "AIUPD", ("mgr", "hvt", "bss"), 0, None, "cave"),
    ("AI陆军:放行玩家", "AIGATE", 6, "AIGATE", ("mgr", "hvt", "aiupd_ret", "aibss", "agc_ret"), 0, None, "cave"),
    ("AI陆军:控制区变更同步给玩家", "AREASYNC", 5, "AREASYNC", ("aibss", "mmv", "self"), 0, None, "cave"),
    ("AI陆军:只放行军事/空军/国策/贸易/生产命令", "POSTB", 6, "POSTB", ("mgr", "hvt", "aibss", "f0", "f1", "f2", "t0", "p0", "p1", "hres", "mlv", "w00", "w01", "w02", "w03", "w04", "w05", "w06", "w07", "w08", "w09", "w10", "w11", "w12", "w13", "w14", "w15", "w16", "w17", "w18", "w19", "w20", "w21", "w22", "w23", "w24", "w25", "w26", "w27", "w28", "w29", "w30", "w31", "w32", "w33", "w34", "w35", "w36", "w37", "w38", "w39", "w40", "w41", "w42", "w43", "w44", "w45", "w46", "w47", "w48", "w49", "w50", "w51", "w52", "w53", "w54", "w55", "w56", "w57", "w58", "w59", "w60", "w61", "w62", "w63", "w64", "w65", "w66", "w67", "w68", "w69", "w70", "w71", "w72", "w73", "w74", "w75", "w76", "w77", "w78", "w79", "w80", "w81", "w82", "w83", "w84", "w85", "w86", "w87", "w88", "w89", "w90", "w91", "w92", "w93", "w94", "w95"), 0, None, "cave"),
    ("AI生产:不为新产线预留工厂", "PRODW", 7, "PRODW", ("mgr", "hvt", "aibss", "mlv", "wret"), 0, None, "cave"),
    ("AI:拦截 AI 经替国家发命令入口发出的命令", "POSTA", 5, "POSTA", ("mgr", "hvt", "aibss", "rs_adv", "rs_railai", "rs_raila", "rs_railb", "rs_railc"), 0, None, "cave"),
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
DIRECT_PATCHES = {"SPPOPUP": bytes.fromhex("c3"), "ACH": bytes.fromhex("31c0"), "IRON": bytes.fromhex("b10190"), "ACHUI": bytes.fromhex("6a01415d")}
# 机器码需要额外的零初始化数据区(bss)，紧跟在补丁代码后面；大小(字节)
CAVE_BSS = {"FOCUS": 4640, "AIUPD": 64}
# 机器码里写死、但不同游戏版本可能不同的结构体偏移：(R 里的键, 机器码里的占位值)
CAVE_FIELD_PATCH = {
    "POSTB": [("archoff", 0x4D8)],
    "PRODW": [("archoff", 0x4D8)],
    # 每日钩子读科技数组的两条指令(movsxd rcx,[r15+数量]；mov r14,[r15+数组])，按实际偏移重写；
    # 找不到偏移时安装会被拒绝(见 CAVE_FIELD_REQUIRED)，避免读错地址崩溃
    "FOCUS": [("techcnt", bytes.fromhex("49638F"), 0x94), ("techarr", bytes.fromhex("4D8BB7"), 0x88)],
    # 运输船补丁里比较所属国的指令(偏移是 1 字节)
    "CONVRAID": [("convoy_owner", bytes.fromhex("4C3942"), 0x38, 1)],
    "TRANSNAV": [("transfer_owner", bytes.fromhex("453B41"), 0x58, 1)],
    "TRANSAIR": [("transfer_owner", bytes.fromhex("453B41"), 0x58, 1)],
}
CAVE_FIELD_REQUIRED = {"FOCUS": ("techcnt", "techarr"), "POSTB": ("archoff",), "PRODW": ("archoff",), "CONVRAID": ("convoy_owner",),
                       "TRANSNAV": ("transfer_owner",), "TRANSAIR": ("transfer_owner",)}
# 不能直接用特征码定位、而是从别的函数里的 call 目标推出来的入口：键 = (宿主特征码键, call 指令相对宿主入口的偏移)
DERIVED = {"AIGATE": ("AIUPD", None), "PRODW": ("PRODWSITE", 40)}   # None：在宿主开头找第一处 mov rcx,rax; call(不同版本位置不同)
# 需要用特征码解析出入口地址、供机器码调用的引擎函数：键 -> 特征码键
SIG_FUNCS = {"complete": "COMPLETE", "vecins": "VECINS", "setfocus": "SETFOCUS", "validfocus": "VALIDFOCUS", "contains": "CONTAINS", "addsize": "ADDSIZE",
             "unlock": "UNLOCK", "visible": "VISIBLE", "setfn": "SETTECH",
             "spexec": "SPEXEC", "spiscomp": "SPISCOMP", "spcanstart": "SPCANSTART", "spfactory": "SPFACTORY",
             "wupd": "WUPD", "hres": "HRESOLVE"}
# 缺了也不影响整个补丁的可选键(机器码里值为 0 就跳过对应功能：MIO 特性自动解锁)
OPT_KEYS = ("f0", "f1", "f2", "t0", "p0", "p1", "hres", "mlv", "setfocus", "validfocus", "tmv", "contains", "addsize", "unlock", "visible", "setfn", "spexec", "spiscomp", "spcanstart", "spfactory", "wupd")
# 需要 vtable 的类
AI_WHITELIST = ['CAiDiscardForceConcentrationTargetCommand', 'CAiStoreForceConcentrationTargetCommand', 'CAiStoreTotalWantedNrDivisionsCommand', 'CArmyGroupCommand', 'CAssignToArmyGroupCommand', 'CAssignToTheaterGroupCommand', 'CAttachAirWingToArmyCommand', 'CCancelMovementCommand', 'CCreateAreaDefenseCommand', 'CDeployAirWingCommand', 'CDetachAirWingFromArmyCommand', 'CDisbandTheaterGroupCommand', 'CMoveAirGroupAndAirTheatreToFreeCommand', 'CMoveAirWingAndAirGroupToAirTheatreCommand', 'CMoveAirWingToAirGroupCommand', 'CMoveArmiesInTheaterCommand', 'CMoveArmyGroupInTheaterCommand', 'COrderAddNewCompletePlanCommand', 'COrderAssignCommand', 'COrderBlockSectionsCommand', 'COrderChildFrontRatioCommand', 'COrderConnectCommand', 'COrderDeleteAllCommand', 'COrderDeleteCommand', 'COrderEditRootCommand', 'COrderExecuteCommand', 'COrderGroupCommand', 'COrderInsertFrontCommand', 'COrderMembersFairSplitCommand', 'COrderMergeRootsCommand', 'COrderNewFallbackCommand', 'COrderNewFrontCommand', 'COrderNewRootCommand', 'COrderReconnectCommand', 'COrderReorderChildFrontCommand', 'COrderReshapeCommand', 'COrderSetCollapseCommand', 'COrderSetInvasionSourceCommand', 'COrderSetParadropSourceCommand', 'COrderSetParadropTargetCommand', 'COrderSetPathCommand', 'COrderSetTrainingCommand', 'COrderUnassignCommand', 'CRemoveFromArmyGroupCommand', 'CReorderAirTheatersCommand', 'CReorderTheatersCommand', 'CSetArmyLeaderCommand', 'CSetOrderGroupExecutionTypeCommand', 'CSetTheaterGroupPriorityCommand', 'CSetTheatreCommand', 'CSetWingReinforcementPriorityCommand', 'CStratAirCancelTransferCommand', 'CStratAirChangeAggressivnessCommand', 'CStratAirConsolidateCommand', 'CStratAirDayNightCommand', 'CStratAirEnableMissionCommand', 'CStratAirMoveEquipmentCommand', 'CStratAirMoveEquipmentToReservesCommand', 'CStratAirSetMissionCommand', 'CStratAirSplitCommand', 'CStratAirTransferCommand', 'CStrategicRedeploymentCommand', 'COrderReplaceRootCommands', 'CMassMoveCommand', 'CSetOrderGroupCohesionTypeCommand', 'CEditAreaDefenseStateCommand', 'CSetAreaDefenseSettingCommand', 'CSetArmyLeaderPreferredTacticCommand', 'CSetCountryReinforcementPriorityCommand', 'CSetPreferredTacticCommand', 'CAddNavalInvasionTargetCommand', 'CRemoveNavalInvasionTargetCommand', 'CAiOnFailedInvasionCommand', 'COrderRemoveRootCommands', 'COrderReplaceFallbackCommands', 'CDeleteOrderGroupCommand', 'CAutoMergeOrdersCommand', 'CSetOrdersLinkCommand', 'CSetOrderGroupMotorizationCommand', 'CSetOrderGroupLeaderProximityCommand', 'CTransportUnitCommand']
VTABLE_CLASSES = {"hvt": "CHuman", "agcv": "CArmyGroupCommand", "f0": "CSetNationalFocusCommand", "f1": "CSetContinuousFocusCommand", "f2": "CBypassNationalFocusCommand", "t0": "CCreateTradeCommand", "p0": "CSetProductionLineCommand", "p1": "CAddMassFactoryAssignmentCommand", "mlv": "CMilitaryProductionLine", "mmv": "CAIMilitaryMinister", "cvt": "CCountry", "svt": "CShip", "tvt": "CTaskForce",
                  "wvt": "CAirWing", "xvt": "CStrategicNavy",
                  "tmv": "CTraitTemplate@NIndustrialOrganisation"}
WL_KEYS = {f"w{i:02d}" for i in range(96)}
VTABLE_CLASSES.update({f"w{i:02d}": c for i, c in enumerate(AI_WHITELIST)})


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
    for key, sk in SIG_FUNCS.items():
        hits = img.find_sig(SIGS[sk])
        if len(hits) == 1:
            R[key] = hits[0]
        else:
            problems.append(f"引擎函数 {key}: 特征码{'未命中' if not hits else '命中 %d 处(不唯一)' % len(hits)}")
    # 装备类型(CEquipmentType)里“原型”指针的字段偏移(1.19.3.0.c01a 为 0x4D8，3fba 为 0x4E0)：从引擎里一处读它的指令取出
    hits = img.find_sig(SIGS["ARCHOFF"])
    if len(hits) == 1:
        R["archoff"] = struct.unpack("<I", img.bytes_at(hits[0] + 24, 4))[0]
    else:
        problems.append("装备原型字段偏移: 特征码" + ("未命中" if not hits else "不唯一"))
    # 科技管理器里科技数组的字段偏移(c01a: 数组 +0x88/数量 +0x94；3fba: +0x90/+0x9C)
    hits = img.find_sig(SIGS["TECHARR"])
    if len(hits) == 1:
        R["techcnt"] = struct.unpack("<I", img.bytes_at(hits[0] + 14, 4))[0]
        R["techarr"] = struct.unpack("<I", img.bytes_at(hits[0] + 27, 4))[0]
    else:
        problems.append("科技数组字段偏移: 特征码" + ("未命中" if not hits else "不唯一"))
    # 运输船所属国字段偏移：构造函数里写入的位置(海上运输部队 CNavalUnitTransfer 写所属国编号；
    # 补给/贸易运输船 CConvoyClient 依次初始化的第 3 个字段是所属国家指针)
    for key, sk, cls in (("transfer_owner", "CTOR_TRANSFER", "CNavalUnitTransfer"),
                         ("convoy_owner", "CTOR_CONVOY", "CConvoyClient")):
        vt = img.vtable_of(cls)
        found = [hit for hit in img.find_sig(SIGS[sk])
                 if vt and hit + 7 + struct.unpack("<i", img.bytes_at(hit + 3, 4))[0] == vt]
        if len(found) == 1:
            R[key] = img.bytes_at(found[0] + len(SIGS[sk].split()) - 1, 1)[0]
        else:
            problems.append(f"{cls} 所属国字段偏移: 构造函数特征码" + ("未命中" if not found else "不唯一"))
    hits = img.find_sig(SIGS["PRODWSITE"])
    if len(hits) == 1 and img.bytes_at(hits[0] + 40, 1)[0] == 0xE8:
        R["wret"] = hits[0] + 45
    else:
        problems.append("AI 生产装备打分调用点: 特征码" + ("未命中" if not hits else "不唯一或不是 call"))
    # 调用点的返回地址(特征码命中处 +16 是 call，返回地址 = +21)
    for key in ("RS_ADV", "RS_RAILAI", "RS_RAILA", "RS_RAILB", "RS_RAILC"):
        hits = img.find_sig(SIGS[key])
        if len(hits) == 1 and img.bytes_at(hits[0] + 16, 1)[0] == 0xE8:
            R[key.lower()] = hits[0] + 21
        else:
            problems.append(f"调用点 {key}: 特征码{'未命中' if not hits else '不唯一或不是 call'}")
    # 各钩子入口
    for name, sigkey, pro_len, cavekey, keys, yes_delta, yes_check, kind in HOOKS:
        if sigkey in DERIVED:                       # 从宿主函数里的 call 指令推出入口
            host, off = DERIVED[sigkey]
            hh = img.find_sig(SIGS[host])
            if len(hh) != 1:
                problems.append(f"{name}: 宿主特征码 {host} {'未命中' if not hh else '不唯一'}")
                continue
            if off is None:
                head = img.bytes_at(hh[0], 0x80)
                k = head.find(bytes.fromhex("488BC8E8"))
                if k < 0:
                    problems.append(f"{name}: 宿主 {host} 开头找不到 mov rcx,rax; call")
                    continue
                off = k + 3
                R["derived_off:" + sigkey] = off
            o = hh[0] + off
            b = img.bytes_at(o, 5)
            if b[0] != 0xE8:
                problems.append(f"{name}: 宿主 {host}+0x{off:X} 处不是 call 指令")
                continue
            R["entry:" + name] = o + 5 + struct.unpack("<i", b[1:])[0]
            continue
        hits = img.find_sig(SIGS[sigkey])
        if len(hits) != 1:
            problems.append(f"{name}: 特征码{'未命中' if not hits else '命中 %d 处(不唯一)' % len(hits)}")
            continue
        R["entry:" + name] = hits[0]
    return R, problems


def agc_ret(img, R, gate):
    """CArmyGroupCommand::Execute(vtable 第 10 项)里调用“是否 AI 国家”判断的那条 call 的返回地址(RVA)；找不到返回 0。"""
    ib = img.image_base()
    ex = struct.unpack("<Q", img.bytes_at(R["agcv"] + 8 * 10, 8))[0] - ib
    code = img.bytes_at(ex, 0x900)
    for i in range(len(code) - 5):
        if code[i] == 0xE8 and ex + i + 5 + struct.unpack_from("<i", code, i + 1)[0] == gate:
            return ex + i + 5
    return 0


def need_keys(keys, R):
    return all(k in R or k in ("yes", "bss", "aiupd_ret", "aibss", "self", "agc_ret") + OPT_KEYS or k in WL_KEYS for k in keys)


shared = {}   # 装完后留给 --ai status 用的地址(AI 开关字节所在的数据区)


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
    shared.clear()
    for name, entry, pro, cavekey, keys, yes_delta, kind in todo:
        e = base + entry
        if kind == "direct":
            dp = DIRECT_PATCHES[sigkey_of[name]]
            patch = dp + bytes([0x90]) * (len(pro) - len(dp))
            out.append((name, "安装成功" if P.patch_code(h, e, patch) else "写入失败"))
            continue
        if cavekey == "AIGATE" and "aibss" not in shared:
            out.append((name, "依赖的 AI陆军:状态维护 未安装，跳过"))
            continue
        code = bytearray(bytes.fromhex(CAVES[cavekey]))
        if any(k not in R for k in CAVE_FIELD_REQUIRED.get(cavekey, ())):
            out.append((name, "找不到随版本变化的字段偏移，跳过"))
            continue
        for item in CAVE_FIELD_PATCH.get(cavekey, ()):  # 机器码里随游戏版本变化的结构体偏移，安装时换成实际值
            if len(item) == 2:
                rkey, placeholder = item
                code = bytearray(bytes(code).replace(struct.pack("<I", placeholder), struct.pack("<I", R[rkey])))
            else:
                rkey, prefix, placeholder, *size = item
                if size and size[0] == 1:
                    if not 0 <= R[rkey] < 0x80:
                        out.append((name, "字段偏移超出 1 字节，跳过"))
                        code = None
                        break
                    code = bytearray(bytes(code).replace(prefix + bytes([placeholder]), prefix + bytes([R[rkey]])))
                else:
                    code = bytearray(bytes(code).replace(prefix + struct.pack("<I", placeholder), prefix + struct.pack("<I", R[rkey])))
        if code is None:
            continue
        cave = arena + cur_off
        vals = []
        for k in keys:
            if k == "mgr":
                vals.append(base + R["mgr"])
            elif k == "yes":
                vals.append(base + entry + yes_delta if yes_delta else 0)
            elif k == "bss":
                vals.append(cave + ((len(code) + len(pro) + 5 + 15) & ~15))
                if cavekey == "AIUPD":
                    shared["aibss"] = vals[-1]
            elif k == "aiupd_ret":
                vals.append(base + R["entry:AI陆军:状态维护"] + R["derived_off:AIGATE"] + 5)
            elif k == "self":
                vals.append(e)
            elif k == "agc_ret":
                vals.append(base + agc_ret(img, R, entry) if "agcv" in R else 0)
            elif k == "aibss":
                vals.append(shared.get("aibss", 0))
            elif (k in OPT_KEYS or k in WL_KEYS) and k not in R:
                vals.append(0)
            else:
                vals.append(base + R[k])
        for i, v in enumerate(vals):
            struct.pack_into("<Q", code, 8 * i, v)
        code_off = 8 * len(keys)
        code += pro                                   # 被覆盖的原指令搬进补丁
        jmp_at = len(code)
        code += bytes([0xE9]) + struct.pack("<i", (e + len(pro)) - (cave + jmp_at + 5))
        if not P.write_mem(h, cave, bytes(code)):
            out.append((name, "写入补丁失败"))
            continue
        patch = bytes([0xE9]) + struct.pack("<i", (cave + code_off) - (e + 5)) + bytes([0x90]) * (len(pro) - 5)
        out.append((name, "安装成功" if P.patch_code(h, e, patch) else "写入失败"))
        cur_off += ((len(code) + 15) & ~15) + CAVE_BSS.get(cavekey, 0)
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


STATE = Path(os.environ.get("TEMP", str(HERE))) / "hoi4_nologistics_state.json"


def ai_status():
    """--ai status：读补丁数据区里的开关状态(开关只由决议旗标决定，这里只读不写)。"""
    pid = P.find_pid("hoi4.exe")
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    if not pid or st.get("pid") != pid or not st.get("aibss"):
        log("游戏没在运行，或本次启动没有装上 AI 补丁(看日志里“AI陆军”两项)")
        return 1
    h = P.open_process(pid)
    bss = st["aibss"]
    on, restricted, _s, _c, ai, ticks = struct.unpack("<QQQQQQ", P.read_mem(h, bss, 48))
    log(f"AI 控制玩家陆军: {'开' if on & 0xFF == 1 else '关'}；AI 选国策: {'开' if (on >> 8) & 0xFF == 1 else '关'}；AI 贸易: {'开' if (on >> 16) & 0xFF == 1 else '关'}；AI 生产: {'开' if (on >> 24) & 0xFF == 1 else '关'}；玩家国家 AI 对象=0x{ai:X}；已限制模块列表={'是' if restricted else '否'}；累计更新次数={ticks}")
    return 0


def main():
    global _quiet
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="给运行中的游戏装补丁后退出")
    ap.add_argument("--remove", action="store_true", help="撤销补丁")
    ap.add_argument("--status", action="store_true", help="只显示特征码定位结果，不写入")
    ap.add_argument("--ai", choices=("status",), help="查看 AI 控制/AI 选国策/AI 贸易/AI 生产 的开关状态(开关用游戏里的决议切换)")
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
    if args.ai:
        return ai_status()
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
    if shared.get("aibss"):
        try:
            STATE.write_text(json.dumps({"pid": pid, "aibss": shared["aibss"]}), encoding="utf-8")
        except OSError:
            pass


if __name__ == "__main__":
    main()
