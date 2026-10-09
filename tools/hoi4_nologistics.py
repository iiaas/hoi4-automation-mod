#!/usr/bin/env python3
"""HOI4 引擎内补丁工具(纯 Python，不需要任何 mod 文本，装完 Python 立即退出，不常驻)。

原理
----
在 hoi4.exe 进程里给若干引擎函数装一小段机器码(“补丁”)。补丁由引擎自己调用，先判断当前调用方是不是
“玩家本国”(读国家管理器里的玩家记录 CHuman，比较国家编号；傀儡国不算)，
不是就原样执行原函数，所以 AI 国家完全不受影响。补丁随游戏进程存在，读档/换国立即生效；游戏重启后需要重装
(Steam 启动项会自动装)。

当前功能(全部只对玩家本国生效，不含傀儡国，除非特别说明)
------------------------------------------------
1. 无补给/燃油消耗 + 至少“训练有素”
   - 陆军师(每次更新)：经验 = 经验总量/兵力，低于 0.3 就抬到 0.3；当前补给低于约 5000 小时就补到 10000 小时；
     燃油补满。补充兵员稀释经验后，下一次更新就会被抬回，永远不低于训练有素。
   - 海军舰船(每次更新)：经验低于 0.3 抬到 0.3，并把舰船置为“需要重算修正”(否则界面显示训练有素、修正仍是乌合之众，潜艇尤其明显)。
   - 空军联队(每次更新)：经验低于 300(联队经验的训练有素门槛)抬到 300，并调用引擎的“按经验更新修正”函数(否则界面显示训练有素、修正仍是 0 级)。
   - 海军/空军只处理经验，不处理补给与燃油。
2. 海军登陆去除限制
   - 无视制海权不足：登陆路线校验里“我方是否控制该海区”对玩家恒为“是”(不再提示 Insufficient Naval Dominance)。
   - 每次登陆的师数上限：对玩家恒为 99。
   - 登陆计划数量上限：对玩家恒为 99；另一个独立的“登陆计划是否已满”判断(0x702540，下达/设置登陆出发港时用，
     自己算上限、不走上面的函数)对玩家恒为“未满”，否则 AI 控制玩家时登陆命令全被判无效。
   - 登陆准备时间：对玩家把“准备时间修正”固定为 -0.99，准备时间约剩原来的 1%。
3. 空降去除限制
   - 空降计划数量上限：对玩家恒为 99；“空降计划是否已满”判断(0x700180)对玩家恒为“未满”。
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

6. 自动国策：改由原版 AI 选国策(见第 12 项“AI 选国策”开关，mod 决议控制，默认关闭)
   - 补丁不再自己计时/并行完成/挑选国策；开关打开时只让玩家的政治大臣运行，并只放行它发出的
     设置国策/持续国策/绕过国策命令(不放行“取消当前国策”，不会覆盖你手选的国策)，选法与原版 AI 国家完全一致。
   - 原来挂在国策进度每日更新上的钩子保留，只做第 7~9 项(MIO/科技/专项项目)。
7. 自动解锁 MIO 特性(只对玩家本国；不再列举特性 id)
   - 与自动国策同一个每日钩子：遍历玩家国家的 MIO(与脚本里 every_military_industrial_organization 一样，
     只处理当前可见的 MIO)，对每个 MIO 模板里的每个特性：没解锁就“+1 规模并解锁”，与效果 complete_mio_trait
     走同一对引擎函数(无视前置条件)，已解锁的跳过。
   - 特性数组的元素大小不写死：用 RTTI 查到的 CTraitTemplate vtable 在内存里自动测出来。
   - 这一项缺少任何一个特征码时只会自动跳过，不影响其它功能。

8. 自动解锁科技(只对玩家本国；不再需要 mod 里的 set_technology 清单)
   - 同一个每日钩子：遍历玩家国家的科技数组，对没研究完的科技，按条件逐个调用引擎自带的 set_technology 效果函数
     (用一个现场拼出来的假效果对象，等价于 set_technology = { 科技 = 1 popup = no }，会正常触发蓝图/经验等奖励)。
   - 条件：科技有所属文件夹，且不在旧式坦克线(armour_folder)与旧式战机线(air_techs_folder)里；
     start_year 早于 1936 的开局即解锁，start_year 为 Y(>=1936) 的在游戏日期超过 Y.1.1 后解锁(与原脚本的年份分组一致)；
     没有 start_year 的按开局解锁。已研究完的跳过，所以按天调用不会重复发奖励。
   - 注意：游戏日期是引擎里的“小时数”(国家管理器 +0x468)，各年 1 月 1 日的小时数由 1936.1.1 = 60759359 推算(机器码里写死)。
   - 没有处理专项项目(special project)：它们仍由 mod 脚本 auto_research_technology_effects.txt 按年份写死的列表完成。

9. 自动完成专项项目(special project)(只对玩家本国；不再列举项目名，也不需要任何 mod 脚本)
   - 同一个每日钩子：用引擎自己的工厂函数造一个真实的 complete_special_project 效果对象(只造一次，之后复用)，
     每天遍历玩家的项目池，对 没完成(IsCompleted=否) 且 引擎判定可开始(CanStart=是，即项目的 available 条件，
     如已研究所需科技)的项目，把效果对象的项目 token 改成它再执行，等价于脚本里的 complete_special_project。
   - 因此项目会在科技到位后依次完成，不按写死的年份。

10. 玩家的运输船(船队/convoy)不会被击沉(只对玩家本国)
   - 挂在引擎的“船队被击沉”处理函数(攻击方统计 convoys_destroyed、登记 CSunkConvoyInfo、扣减船队的那一个)入口：
     被击沉船队的所属国(对象 +0x20 处的国家标识)是玩家本国时，直接返回，什么都不做，所以不会损失船队、
     不会记入对方击沉统计；其他国家(含敌方船队)照常。
   - 尚未在实战里验证；若发现玩家船队仍被击沉，说明还有别的击沉路径，需要再分析。

11. 专项项目完成不弹窗(对所有人生效)
   - “专项项目完成”弹窗由一个只负责显示窗口的函数创建(不做任何游戏逻辑)，补丁把它的第一条指令改成 ret，
     项目完成时不再弹窗(对所有人生效；单人游戏里只有玩家会看到这个弹窗)。

12. AI 控制玩家陆军和空军(实验功能，默认关闭；只能用 mod 决议“AI 控制”开关)
   - 引擎里每个国家(包括玩家)都有一套 AI 对象 CCountryAI(政治/外交/内政/军事大臣等模块)，玩家那套没有被驱动：
     CCountryAI::Update 开头要先过“这个国家是不是 AI 国家”的判断，玩家过不了。
   - 补丁一(AI陆军:放行玩家)：只在 CCountryAI::Update 调用该判断时(靠返回地址限定)，开关打开后对玩家本国返回“是”。
   - 补丁二(AI陆军:状态维护)：开关为 on 时，玩家的 CCountryAI 只让前 4 个模块(政治/外交/内政/军事大臣)运行，
     其余(密码/情报/行动/特工)不运行；关闭时恢复原样。实测：只跑军事大臣时空军没有任何任务(空军 AI 的输入要
     政治、外交、内政三个大臣一起运行后才有，和游戏开始时先 observe 让整套 AI 跑过一遍再切回玩家是同一个原因)。
   - 补丁三(AI陆军:只放行军事/空军/国策命令)：AI 大臣的命令都经过引擎的“发布 AI 命令”函数(0x29EB30，调用方全在
     AI 代码里)。另一个“替国家发命令”的函数(0x2A0930)也被游戏其它系统和玩家自己的操作(如任命顾问)使用，
     对本机玩家直接执行，所以不过滤它(以前过滤它会导致开启 AI 后玩家无法任命顾问)。开关为 on 时，
     对玩家本国只放行陆军(战线/编队/战区/师数需求/部队移动…)和空军(任务/转场/部署…)类命令(白名单
     AI_WHITELIST，约 80 类)，其余(生产、贸易、外交、法律、科研、海军…)命令直接销毁，所以政治/外交/内政
     大臣虽然运行了，但不会真的替你做这些事。
   - 暂未限制在某个战区内：打开后作用于玩家全部陆军和空军。已设置的手动任务可能被 AI 改掉。
   - 补丁四(AI陆军:控制区变更同步给玩家)：引擎重建“控制区”(CControllerArea)时，会调 0x108EA90 把每个 AI 国家的
     AI 将军(CAIGeneral)里引用的旧控制区换成新的，但玩家的将军不在通知名单里，留着已释放的指针，运行一段时间后
     在 AI 将军代码 0x106AE90 处崩溃。补丁在该函数被调用(给任一 AI 将军)时，顺带用同样参数对玩家军事大臣
     (CCountryAI 模块 3，+0x18 将军列表)下的每个将军也调用一次原函数，与原版 AI 国家的处理一致。
   - 登陆：白名单原先缺“添加/移除登陆目标”(CAddNavalInvasionTargetCommand/CRemoveNavalInvasionTargetCommand)等命令，
     玩家的登陆计划建出来却没有目标，永远不执行；已补上这些及其它战线/编组类命令(白名单 96 槽)。
     另见第 2 项“登陆计划是否已满”判断对玩家恒为“未满”，否则设置登陆出发港的命令会被判无效。
   - 决议开关：mod 决议“AI 控制 → 开启/关闭 AI 控制”(common/decisions/autocore_ai_control_*.txt)给玩家设
     国家旗标 autocore_ai_control，值 7700=关、7701=开；补丁二每次玩家 AI 更新时扫描玩家旗标容器
     ([国家+0x230]，+8 数组/+0x14 数量，每项 0x30 字节、+0x28 为值)，据此重算开关。
     开关完全以旗标为准、不在补丁里留状态：每次都从“关”算起，有 7701/7711 才开，结果一次写回(不先清零，
     免得别的线程上的命令过滤读到短暂的“关”而放行全部命令)。旗标随存档保存，所以读档、开新局、换国家都自动正确，
     不会把上一局的开关带过来。
   - AI 选国策(独立开关，补丁数据区第 2 个字节)：决议“开启/关闭 AI 选国策”设国家旗标 autocore_focus_ai，
     值 7710=关、7711=开。只开这一项时玩家 CCountryAI 只跑模块 0(政治大臣)，命令过滤只放行国策命令；
     与陆空 AI 同时开时跑前 4 个模块，两类命令都放行。
   - AI 贸易(独立开关，补丁数据区第 3 个字节)：决议“开启/关闭 AI 贸易”设国家旗标 autocore_trade_ai，值 7720=关、
     7721=开。原版由内政大臣(模块 2)用 CCreateTradeCommand 下单/取消进口，但下单前要读军事大臣算出的一个余量
     (CCountryAI+0xBC8 即军事大臣，其 +0x678，负数就不做贸易；军事大臣不运行时停在初始值 -100)，所以开 AI 贸易时
     玩家 CCountryAI 跑前 4 个模块(含军事大臣)；命令过滤只放行打开的开关对应的命令，军事大臣发出的军队命令在
     没开 AI 控制时照样销毁，外交、生产等也照样销毁。
   - 查看状态：pythonw 本脚本 --ai status(游戏运行时执行，结果写在 %TEMP% 下的 hoi4_nologistics.log)。

兼容性(防止游戏更新后失效)
--------------------------
- 所有补丁入口都用“特征码”在 hoi4.exe 代码段里定位(跳过地址相关的 4 字节位移)，不再写死地址；
  全局变量(国家管理器)靠一段特征码解码 rip 相对位移得到；各个类的 vtable 靠 RTTI 类名查到。
- 特征码必须在代码段里唯一命中才会安装；找不到/不唯一/被补过的原指令对不上，只会跳过该补丁并写日志，不会乱写。
- 游戏更新后只要这些函数的指令没变，补丁照常安装；如果某个特征码失效，日志里会有“特征码未命中”。
- 不能自动适配的是“结构体字段偏移”(如 师 +0x430 经验总量、国家管理器里玩家编号 +0x280/+0x520 等)，它们写在机器码里；
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
    "AIUPD": "48 89 5C 24 08 57 48 83 EC 40 48 8B F9 E8 ?? ?? ?? ?? 48 8B D8 48 85 C0 0F 84 ?? ?? ?? ?? 80 7F 60 00 0F 84 ?? ?? ?? ?? 83 B8 84 04 00 00 00 0F 8E ?? ?? ?? ?? 48 8B C8 E8",
    "AREASYNC": "48 89 5C 24 18 48 89 6C 24 20 56 57 41 56 48 83 EC 20 4C 89 7C 24 48 49 8B E8 4C 63 79 54 48 8B DA",
    "POSTB": "40 53 48 83 EC 40 80 3D ?? ?? ?? ?? 00 48 8B D9 0F 84 ?? ?? ?? ?? 80 3D ?? ?? ?? ?? 00 75 ?? 48 8B CA E8 ?? ?? ?? ??",
    "SPFACTORY": "40 53 48 83 EC 20 B9 E8 02 00 00",
    "CONVOY": "4C 89 4C 24 20 4C 89 44 24 18 48 89 54 24 10 48 89 4C 24 08 55 53 56 57 41 54 41 55 41 56 41 57 48 8D 6C 24 ?? 48 81 EC 88 00 00 00",
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
    "CONVOY": (
        "00000000000000000000000000000000505241504151488b05e3ffffff488b004885c07450488b15dcffffff48"
        "39901001000075408b90800200003b9020050000753285d2742e3b901c03000073264c8b80100300004d85c074"
        "1a4d8b04d04d85c07411488b5120493b50087507415941585a58c3415941585a58"
    ),
    "AIUPD": (
        "000000000000000000000000000000000000000000000000505241504151488b05dbffffff488b004885c00f84"
        "48010000488b15d0ffffff483990100100000f85340100008b90800200003b90200500000f852201000085d20f"
        "841a0100003b901c0300000f830e0100004c8b80100300004d85c00f84fe0000004d8b04d04d85c00f84f10000"
        "004c3941080f85e70000004c8b0d77ffffff4989492049ff41284531db498b80300200004885c0745b8b501448"
        "8b40084885c0744f81fa00100000774785d27443ffca4c8d045249c1e004460fb74400284181f8151e00007506"
        "4183cb01ebdd4181f81f1e000075094181cb00010000ebcb4181f8291e000075c24181cb00000100ebb9458919"
        "ba040000004180390174134180790201740cba010000004180790101752d493949087422488b41204885c0743e"
        "448b412c4183f8057c34458941184c8b004d8941104989490889512ceb20493949087512488b41204d8b41104c"
        "8900418b511889512c49c7410800000000415941585a58"
    ),
    "AIGATE": (
        "000000000000000000000000000000000000000000000000000000000000000050524150488b05e5ffffff4839"
        "4424187569488b05dfffffff833800745d488b05bbffffff488b004885c0744e488b15b4ffffff483990100100"
        "00753e8b90800200003b9020050000753085d2742c3b901c03000073244c8b80100300004d85c074184d8b04d0"
        "4d85c0740f4c39c1750a41585a58b801000000c341585a58"
    ),
    "AREASYNC": (
        "000000000000000000000000000000000000000000000000535657415441554156488b05d8ffffff4885c0747e"
        "488b40204885c0747548394108746f83782c047c69488b58204885db7460488b5b184885db74574c8b1dadffff"
        "ff4c391b754b488b73188b7b244885f6743f81ff0001000077374989cc4989d54d89c64883ec2885ff7e19ffcf"
        "488b0cfe4885c974f14c89ea4d89f0ff1574ffffffebe34883c4284c89e14c89ea4d89f0415e415d415c5f5e5b"
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
        "0000000000000000000000000000505241504151488b05cbfcffff4885c00f84d80000008038020f84cf000000"
        "8338000f84c6000000488b0599fcffff488b004885c00f84b30000004c8b058efcffff4c3980100100000f859f"
        "000000448b8080020000443b80200500000f858b0000004585c00f8482000000448b0a4539c1757a4c8b09488b"
        "055afcffff4c3b0d5bfcffff743b4c3b0d5afcffff74324c3b0d59fcffff74294c3b0d58fcffff742880380175"
        "294c8d0552fcffffb8600000004d390874364983c008ffc875f3eb0e807801017426eb0680780201741e415941"
        "585a584883ec284889c9488b01ba01000000ff104883c42831c0c3415941585a58"
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
    ("运输船:玩家船队不被击沉", "CONVOY", 5, "CONVOY", ("mgr", "hvt"), 0, None, "cave"),
    ("专项项目:完成不弹窗", "SPPOPUP", 1, None, (), 0, None, "direct"),
    ("AI陆军:状态维护", "AIUPD", 5, "AIUPD", ("mgr", "hvt", "bss"), 0, None, "cave"),
    ("AI陆军:放行玩家", "AIGATE", 6, "AIGATE", ("mgr", "hvt", "aiupd_ret", "aibss"), 0, None, "cave"),
    ("AI陆军:控制区变更同步给玩家", "AREASYNC", 5, "AREASYNC", ("aibss", "mmv", "self"), 0, None, "cave"),
    ("AI陆军:只放行军事/空军/国策/贸易命令", "POSTB", 6, "POSTB", ("mgr", "hvt", "aibss", "f0", "f1", "f2", "t0", "w00", "w01", "w02", "w03", "w04", "w05", "w06", "w07", "w08", "w09", "w10", "w11", "w12", "w13", "w14", "w15", "w16", "w17", "w18", "w19", "w20", "w21", "w22", "w23", "w24", "w25", "w26", "w27", "w28", "w29", "w30", "w31", "w32", "w33", "w34", "w35", "w36", "w37", "w38", "w39", "w40", "w41", "w42", "w43", "w44", "w45", "w46", "w47", "w48", "w49", "w50", "w51", "w52", "w53", "w54", "w55", "w56", "w57", "w58", "w59", "w60", "w61", "w62", "w63", "w64", "w65", "w66", "w67", "w68", "w69", "w70", "w71", "w72", "w73", "w74", "w75", "w76", "w77", "w78", "w79", "w80", "w81", "w82", "w83", "w84", "w85", "w86", "w87", "w88", "w89", "w90", "w91", "w92", "w93", "w94", "w95"), 0, None, "cave"),
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
# 不能直接用特征码定位、而是从别的函数里的 call 目标推出来的入口：键 = (宿主特征码键, call 指令相对宿主入口的偏移)
DERIVED = {"AIGATE": ("AIUPD", 0x38)}
# 需要用特征码解析出入口地址、供机器码调用的引擎函数：键 -> 特征码键
SIG_FUNCS = {"complete": "COMPLETE", "vecins": "VECINS", "setfocus": "SETFOCUS", "validfocus": "VALIDFOCUS", "contains": "CONTAINS", "addsize": "ADDSIZE",
             "unlock": "UNLOCK", "visible": "VISIBLE", "setfn": "SETTECH",
             "spexec": "SPEXEC", "spiscomp": "SPISCOMP", "spcanstart": "SPCANSTART", "spfactory": "SPFACTORY",
             "wupd": "WUPD"}
# 缺了也不影响整个补丁的可选键(机器码里值为 0 就跳过对应功能：MIO 特性自动解锁)
OPT_KEYS = ("f0", "f1", "f2", "t0", "setfocus", "validfocus", "tmv", "contains", "addsize", "unlock", "visible", "setfn", "spexec", "spiscomp", "spcanstart", "spfactory", "wupd")
# 需要 vtable 的类
AI_WHITELIST = ['CAiDiscardForceConcentrationTargetCommand', 'CAiStoreForceConcentrationTargetCommand', 'CAiStoreTotalWantedNrDivisionsCommand', 'CArmyGroupCommand', 'CAssignToArmyGroupCommand', 'CAssignToTheaterGroupCommand', 'CAttachAirWingToArmyCommand', 'CCancelMovementCommand', 'CCreateAreaDefenseCommand', 'CDeployAirWingCommand', 'CDetachAirWingFromArmyCommand', 'CDisbandTheaterGroupCommand', 'CMoveAirGroupAndAirTheatreToFreeCommand', 'CMoveAirWingAndAirGroupToAirTheatreCommand', 'CMoveAirWingToAirGroupCommand', 'CMoveArmiesInTheaterCommand', 'CMoveArmyGroupInTheaterCommand', 'COrderAddNewCompletePlanCommand', 'COrderAssignCommand', 'COrderBlockSectionsCommand', 'COrderChildFrontRatioCommand', 'COrderConnectCommand', 'COrderDeleteAllCommand', 'COrderDeleteCommand', 'COrderEditRootCommand', 'COrderExecuteCommand', 'COrderGroupCommand', 'COrderInsertFrontCommand', 'COrderMembersFairSplitCommand', 'COrderMergeRootsCommand', 'COrderNewFallbackCommand', 'COrderNewFrontCommand', 'COrderNewRootCommand', 'COrderReconnectCommand', 'COrderReorderChildFrontCommand', 'COrderReshapeCommand', 'COrderSetCollapseCommand', 'COrderSetInvasionSourceCommand', 'COrderSetParadropSourceCommand', 'COrderSetParadropTargetCommand', 'COrderSetPathCommand', 'COrderSetTrainingCommand', 'COrderUnassignCommand', 'CRemoveFromArmyGroupCommand', 'CReorderAirTheatersCommand', 'CReorderTheatersCommand', 'CSetArmyLeaderCommand', 'CSetOrderGroupExecutionTypeCommand', 'CSetTheaterGroupPriorityCommand', 'CSetTheatreCommand', 'CSetWingReinforcementPriorityCommand', 'CStratAirCancelTransferCommand', 'CStratAirChangeAggressivnessCommand', 'CStratAirConsolidateCommand', 'CStratAirDayNightCommand', 'CStratAirEnableMissionCommand', 'CStratAirMoveEquipmentCommand', 'CStratAirMoveEquipmentToReservesCommand', 'CStratAirSetMissionCommand', 'CStratAirSplitCommand', 'CStratAirTransferCommand', 'CStrategicRedeploymentCommand', 'COrderReplaceRootCommands', 'CMassMoveCommand', 'CSetOrderGroupCohesionTypeCommand', 'CEditAreaDefenseStateCommand', 'CSetAreaDefenseSettingCommand', 'CSetArmyLeaderPreferredTacticCommand', 'CSetCountryReinforcementPriorityCommand', 'CSetPreferredTacticCommand', 'CAddNavalInvasionTargetCommand', 'CRemoveNavalInvasionTargetCommand', 'CAiOnFailedInvasionCommand', 'COrderRemoveRootCommands', 'COrderReplaceFallbackCommands', 'CDeleteOrderGroupCommand', 'CAutoMergeOrdersCommand', 'CSetOrdersLinkCommand', 'CSetOrderGroupMotorizationCommand', 'CSetOrderGroupLeaderProximityCommand', 'CTransportUnitCommand']
VTABLE_CLASSES = {"hvt": "CHuman", "f0": "CSetNationalFocusCommand", "f1": "CSetContinuousFocusCommand", "f2": "CBypassNationalFocusCommand", "t0": "CCreateTradeCommand", "mmv": "CAIMilitaryMinister", "cvt": "CCountry", "svt": "CShip", "tvt": "CTaskForce",
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
    # 各钩子入口
    for name, sigkey, pro_len, cavekey, keys, yes_delta, yes_check, kind in HOOKS:
        if sigkey in DERIVED:                       # 从宿主函数里的 call 指令推出入口
            host, off = DERIVED[sigkey]
            hh = img.find_sig(SIGS[host])
            if len(hh) != 1:
                problems.append(f"{name}: 宿主特征码 {host} {'未命中' if not hh else '不唯一'}")
                continue
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


def need_keys(keys, R):
    return all(k in R or k in ("yes", "bss", "aiupd_ret", "aibss", "self") + OPT_KEYS or k in WL_KEYS for k in keys)


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
                vals.append(base + R["entry:AI陆军:状态维护"] + 0x3D)
            elif k == "self":
                vals.append(e)
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
    log(f"AI 控制玩家陆军: {'开' if on & 0xFF == 1 else '关'}；AI 选国策: {'开' if (on >> 8) & 0xFF == 1 else '关'}；AI 贸易: {'开' if (on >> 16) & 0xFF == 1 else '关'}；玩家国家 AI 对象=0x{ai:X}；已限制模块列表={'是' if restricted else '否'}；累计更新次数={ticks}")
    return 0


def main():
    global _quiet
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="给运行中的游戏装补丁后退出")
    ap.add_argument("--remove", action="store_true", help="撤销补丁")
    ap.add_argument("--status", action="store_true", help="只显示特征码定位结果，不写入")
    ap.add_argument("--ai", choices=("status",), help="查看 AI 控制/AI 选国策/AI 贸易 的开关状态(开关用游戏里的决议切换)")
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
