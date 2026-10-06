-----------------------------------------------------------------------
-- FieldKit — 脱战恢复 / 补员 / 自动炮击 / 战斗群解锁 / 最终防线科技
-- 放在游戏根目录，每次场景加载执行。仅影响本机模拟，联机会不同步。
-- 出问题就把本文件改名或删除。
-- 背景知识 / 踩过的坑 / 已证伪的方案：
--   C:\Users\Administrator\Documents\CoH3Mods\NOTES.md
-----------------------------------------------------------------------

Scar_DoString([==[

-- 本文件内容的指纹，check.py 每次改完自动重算。
-- 开局日志里会打出来，用来确认游戏读到的确实是最新这份
FieldKit_Build = "ca4a3c"


-----------------------------------------------------------------------
-- 配置：改完存盘、重进对局即可生效
-----------------------------------------------------------------------

FieldKit_Settings =
{
	-- 刷新间隔（秒），0.125 = 与模拟层同频
	tick = 0.125,
	out_of_combat = 6.0,     -- 脱战窗口：这段时间没挨打也没开火才算脱战
	apply_to = "local",      -- "local" 仅本地 / "humans" 所有真人 / "all" 含 AI

	-- 脱战恢复：逐个成员每秒恢复最大生命的百分比
	heal_infantry = true,
	infantry_heal_per_second = 0.06,
	repair_vehicles = true,
	vehicle_repair_per_second = 0.035,
	repair_buildings = true,
	building_repair_per_second = 0.02,

	-- 补员走原版规则：需在补员范围内，正常扣资源
	auto_reinforce = true,

	-- 全部单位保持满星（部分固定炮台无效，见 NOTES.md）
	max_veterancy = false,

	-- 100% 命中
	perfect_accuracy = false,
	accuracy_multiplier = 100.0,
	accuracy_hardpoint = 1,   -- 武器挂点序号，对齐 skirmish_it.scar:5291

	-- 技能无冷却
	no_ability_cooldown = true,
	cooldown_drain = 9999,

	-- 解锁全图视野
	reveal_map = true,

	-- 把**自己选的那个**战斗群的节点买满（含互斥分支两侧）。
	-- 不替你选战斗群，没选之前一直等着；中途选了也能接上
	unlock_battlegroup_nodes = true,

	-- 最终防线：开局随机解锁它自己的科技，三类各取若干。
	-- 名字带 hero 的不占名额、永远解锁（英雄潘兴靠那条被动带出来）
	hoff_tech_passive = 3,
	hoff_tech_ability = 3,
	hoff_tech_unit    = 3,

	-- 自动开火：有炮击技能的单位自动打技能射程内的活敌人。
	-- 射程靠实测学习（发现走位就停下并记住上限），不抢手动命令
	auto_barrage = true,
	auto_barrage_interval = 2.0,   -- 扫描间隔（秒）
	auto_barrage_tries = 8,        -- 每个单位每轮最多尝试几个最近的敌人
	auto_barrage_smoke = false,    -- 是否也自动放烟（默认不放，免得挡自己视野）
	auto_barrage_only_idle = false,-- 只给待机单位开火。开了会"放一次就停"，见 NOTES

	-- 炮击和近距离技能共用：只打单位攻击距离内的敌人，免得它自己走过去
	auto_use_weapon_range = true,

	-- 把自动技能的射程直接设成单位自己的攻击距离、下限设成 0。
	-- 引擎读不到技能射程，与其猜不如自己定：这样手雷 / 铁拳在正常交战距离
	-- 就能扔出去，单位也不用为了够着而往前走
	auto_match_ability_range = true,

	-- 手榴弹 / 反坦克武器（铁拳这类）：敌人进到射程内就自动放
	auto_close = true,
	auto_close_interval = 2.0,      -- 扫描间隔（秒）
	auto_close_regap = 10.0,      -- 手雷：同一支部队隔这么久再下一次，免得打断施法
	auto_close_regap_at = 2.0,    -- 反坦克武器的间隔，比手雷短

	-- 随机施放玩家技能：从解锁到的战斗群 / 最终防线技能里随机抽一个，
	-- 打向最近的活敌人。呼叫类跳过，施放免费不扣弹药
	auto_player_ability = true,
	auto_callin_interval = 60.0,   -- 呼叫类间隔（秒），放在我方部队旁边
	auto_attack_interval = 0,      -- 进攻类定时间隔（秒），0 = 关掉，只在交战时放
	auto_attack_watch = 1.0,       -- 查敌间隔：敌人刚进入交战就立刻放一个进攻技能
	auto_attack_combat_gap = 20.0, -- 交战触发的最小间隔（秒），免得一直放
	auto_attack_safe_radius = 30.0,-- 目标点这个半径内有友军就不放，0 表示不管
	auto_player_callin = true,     -- 呼叫类也放，但地点选我方部队旁边
	dump_pool_info = false,        -- 开局把技能池逐条打进日志，排查分类问题时开

	-- 自动技能不扣弹药：给技能挂一个花费 ×0 的修饰符
	auto_free_ammo = true,

	-- 战役战略大地图（战斗任务不受此开关影响）
	enable_on_campaign_map = false,

	debug = false,           -- 详细日志写进 warnings.log
}


FieldKit_State =
{
	ready = false,
	players = {},
	sg_reinforce = nil,
	eg_entities = nil,
	accuracy_done = {},      -- [squadID] = true，命中率修饰符只挂一次
	bg_done = {},            -- [玩家序号] = true，战斗群已处理（最终防线用）
	bg_seen = {},            -- [玩家序号|战斗群名] = true，这个战斗群已经买满
	bg_paths = nil,          -- 升级名 -> 注册表路径，扫一次就够
	bg_timer = 0,            -- 战斗群重试节流
	cd_done = {},            -- [玩家序号][技能名] = true，充能修饰符只挂一次
	cd_timer = 0,            -- 技能重扫节流
	barrage_timer = 0,       -- 自动炮击节流
	barrage_diag = 10,       -- 还要打几行自动开火诊断，开出火就清零
	barrage_diag_timer = 0,  -- 两行诊断之间隔 30 秒
	barrage_list = nil,      -- 候选炮击技能蓝图，首次用到时扫注册表
	barrage_of = {},         -- [小队蓝图名] = 它的炮击技能，或 false 表示没有
	barrage_of_timer = 0,    -- 上面这张表多久清一次
	close_list = nil,         -- 候选手榴弹 / 反坦克技能
	close_of = {},            -- [小队蓝图名] = 它的近距离技能，或 false
	close_timer = 0,          -- 近距离技能节流
	close_of_timer = 0,       -- 近距离技能缓存多久清一次
	close_form = {},          -- 哪几种施放形态已经生效过，各打一行日志
	close_last = {},         -- [小队ID] = 上次下令的时间
	free_warned = false,     -- 花费修饰符挂不上时只提醒一次
	hold_fire = nil,         -- 停火技能蓝图，首次用到时解析
	sg_enemy = nil,          -- 复用的敌方小队组
	sg_cast = nil,           -- 复用的施法小队组
	sg_one = nil,            -- 只装一个小队的组，当施法者
	sg_foe_one = nil,        -- 只装一个敌方小队的组，当目标
	sg_aim = nil,            -- 问"这队在打谁"时接结果的组
	aim_shape = nil,         -- 那个接口该怎么调，试出来一次就记住
	aim_warned = false,      -- 一直读不到目标只提醒一次
	range_set = {},          -- [小队ID|技能名] = 已经把射程设成了多少
	range_warned = false,    -- 射程修饰符挂不上时只提醒一次
	home_logged = 0,         -- 呼叫落点诊断已经打了几行
	player_abils = {},       -- [玩家序号] = 解锁到的玩家技能蓝图表
	attack_abils = {},       -- [玩家序号] = 进攻类技能
	callin_abils = {},       -- [玩家序号] = 呼叫类技能
	abils_pruned = {},       -- [玩家序号] = true，技能池已筛过
	callin_timer = 0,        -- 呼叫类节流
	attack_timer = 0,        -- 进攻类节流
	combat_timer = 0,        -- 交战触发节流
	watch_timer = 0,         -- 查敌节流
	was_attacking = {},      -- [小队ID] = true，上一次查敌时它在交战
	hoff_attack = nil,       -- 最终防线本阵营进攻技能池，只算一次
	hoff_callin = nil,       -- 最终防线本阵营呼叫技能池
	player_casts = 0,        -- 已随机施放次数
}


-----------------------------------------------------------------------
-- 自动开火
-----------------------------------------------------------------------

FieldKit_BarrageWords = { "barrage", "bombard" }

-- 反坦克武器的名字特征。这些优先于手雷，能放就先放
FieldKit_AtWords =
{
	"faust", "bazooka", "piat", "schreck", "sticky", "satchel", "anti_tank",
}

-- 手榴弹和反坦克武器的名字特征。缺哪种自己往里加
FieldKit_CloseWords =
{
	"grenade", "faust", "bazooka", "piat", "schreck", "sticky", "satchel",
}

-- 防御建筑的小队类型，名字取自 Attrib.sga 的 attrib/type_squad_type.rgd。
-- 不能拿 teamweapon / suppression 来判，真机枪组也带这两个
FieldKit_FixedTypes = { "building", "emplacement", "base_defense" }


-- 扫蓝图注册表，按名字关键词筛技能，结果缓存在 cache 指定的槽里
function FieldKit_AbilitiesNamed(s, words, cache, dropSmoke)

	if FieldKit_State[cache] ~= nil then
		return FieldKit_State[cache]
	end

	local out = {}

	-- 最终防线的单位混着用：火箭炮之类挂 abilities/hoff 下的专属炮击技能，
	-- 迫击炮这些是从 sbps/races 继承来的、用 abilities/races 下的。所以那一局两边都要
	local hoff = (type(Hoff_GrantTechnologyForWave) == "function")

	if PBG_Ability ~= nil and type(BP_GetPropertyBagGroupCount) == "function" then

		local n = BP_GetPropertyBagGroupCount(PBG_Ability)

		for j = 0, (n or 0) - 1 do

			local path = BP_GetPropertyBagGroupPathName(PBG_Ability, j)

			if path ~= nil then

				local norm = string.lower(string.gsub(path, "\\", "/"))
				local leaf = string.match(norm, "([^/]+)$")
				local isHoff = (string.find(norm, "/hoff/", 1, true) ~= nil)

				local skip = (string.find(norm, "/campaign/", 1, true) ~= nil)
					or (string.find(norm, "cmap", 1, true) ~= nil)
					or (isHoff and not hoff)

				if not skip and dropSmoke
					and string.find(leaf or "", "smoke", 1, true) ~= nil then
					skip = true
				end

				local hitWord = false

				if not skip and leaf ~= nil then
					for _, w in pairs(words) do
						if string.find(leaf, w, 1, true) ~= nil then
							hitWord = true
						end
					end
				end

				if hitWord and BP_AbilityExists(leaf) then
					table.insert(out, BP_GetAbilityBlueprint(leaf))
				end
			end
		end
	end

	FieldKit_State[cache] = out
	print("[FieldKit] 候选技能(" .. cache .. ") " .. tostring(#out) .. " 个")

	return out
end


-- 炮击类候选技能
function FieldKit_BarrageAbilities(s)
	return FieldKit_AbilitiesNamed(s, FieldKit_BarrageWords,
		"barrage_list", not s.auto_barrage_smoke)
end


-- 手榴弹 / 反坦克类候选技能
function FieldKit_CloseAbilities(s)
	return FieldKit_AbilitiesNamed(s, FieldKit_CloseWords, "close_list", true)
end


-- 取这个小队在 pool 里会用的技能（列表），没有则返回 nil。按小队蓝图名缓存。
-- probe 是一个试探用的目标点，给 Squad_HasAbility 认不出来时兜底
function FieldKit_AbilitiesOf(squad, s, pool, cache, probe, player, allowProbe)

	local key = tostring(BP_GetName(Squad_GetBlueprint(squad)))
	local hit = FieldKit_State[cache][key]

	if hit ~= nil then
		if hit == false then
			return nil
		end
		return hit
	end

	local found = {}

	for _, abp in pairs(pool) do
		if Squad_HasAbility(squad, abp) then
			table.insert(found, abp)
		end
	end

	-- Squad_HasAbility 在最终防线里认不出来（实测一个都匹配不上），
	-- 那就直接问引擎能不能对着某个点放，能放就说明这个小队有。
	-- 先把冷却清掉，否则刚打完的单位会被判成"不能放"，白白探空
	if #found == 0 and probe ~= nil and allowProbe then

		local reset = (s.no_ability_cooldown and player ~= nil
			and type(Player_ResetAbilityCooldowns) == "function")

		for _, abp in pairs(pool) do

			if reset then
				Player_ResetAbilityCooldowns(player, abp)
			end

			if Squad_CanCastAbilityOnPosition(squad, abp, probe) then
				table.insert(found, abp)
			end
		end
	end

	if #found == 0 then
		FieldKit_State[cache][key] = false
		return nil
	end

	FieldKit_State[cache][key] = found

	if s.debug then
		local names = {}
		for _, abp in pairs(found) do
			table.insert(names, tostring(BP_GetName(abp)))
		end
		print("[FieldKit] " .. key .. " " .. cache .. " " .. #found
			.. " 个：" .. table.concat(names, ", "))
	end

	return found
end


-- 这个小队会用的炮击技能。最终防线里 Squad_HasAbility 认不出来，所以允许试探
function FieldKit_BarragesOf(squad, s, probe, player)
	return FieldKit_AbilitiesOf(squad, s, FieldKit_BarrageAbilities(s),
		"barrage_of", probe, player, true)
end


-- 这个小队会用的手榴弹 / 反坦克技能。
-- 这里**不许试探**：实测试探会把建筑之类都判成有手雷，
-- 结果对着没这技能的单位狂下令，引擎静默忽略，日志看着在放其实什么都没发生
function FieldKit_CloseOf(squad, s, probe, player)
	return FieldKit_AbilitiesOf(squad, s, FieldKit_CloseAbilities(s),
		"close_of", probe, player, false)
end






-- 取停火技能的蓝图（toggle 技能，开着时算"正在使用"）
function FieldKit_HoldFireAbility()

	if FieldKit_State.hold_fire ~= nil then
		if FieldKit_State.hold_fire == false then
			return nil
		end
		return FieldKit_State.hold_fire
	end

	local abp = nil
	if BP_AbilityExists("hold_fire") then
		abp = BP_GetAbilityBlueprint("hold_fire")
	end

	FieldKit_State.hold_fire = abp or false
	return abp
end


-- 这个小队现在能不能被自动下令：要完全空闲、且没开停火
function FieldKit_BarrageReady(squad, s)

	if FieldKit_IsDowned(squad) then
		return false
	end

	local hf = FieldKit_HoldFireAbility()
	if hf ~= nil and type(Squad_IsDoingAbility) == "function"
		and Squad_IsDoingAbility(squad, hf) then
		return false
	end

	-- 只认 idle 会导致"放过一次就再也不放"：炮击完单位不会回到待机，
	-- 得手动下个命令才清得掉。默认只挡玩家自己下的移动 / 撤退命令
	if s.auto_barrage_only_idle and type(Squad_IsIdle) == "function" then
		return Squad_IsIdle(squad)
	end

	if type(Squad_IsMoving) == "function" and Squad_IsMoving(squad) then
		return false
	end
	if type(Squad_IsRetreating) == "function" and Squad_IsRetreating(squad) then
		return false
	end

	return true
end


-- 倒在地上等救治的伤员小队。既不该往它身上扔手榴弹，自己也放不了技能
function FieldKit_IsDowned(squad)

	if type(Squad_IsCasualty) ~= "function" then
		return false
	end

	local ok, downed = pcall(Squad_IsCasualty, squad)

	return ok and downed == true
end


-- 是不是能打的活目标。尸体 / 空壳小队要滤掉，
-- 三重判断：小队还活着、有成员、成员里有活人
function FieldKit_IsLiveTarget(squad)

	if not Squad_IsAlive(squad) then
		return false
	end
	if Squad_Count(squad) <= 0 then
		return false
	end
	if type(Squad_AliveCount) == "function" and Squad_AliveCount(squad) <= 0 then
		return false
	end
	-- 血量归零但还在地上挣扎、已经没血条的，不算活目标。
	-- 要先确认最大血量大于 0，否则接口给不出数据时会把所有人都滤掉
	if type(Squad_GetHealth) == "function"
		and type(Squad_GetHealthMax) == "function"
		and Squad_GetHealthMax(squad) > 0
		and Squad_GetHealth(squad) <= 0 then
		return false
	end

	return true
end


-- 把敌方**活着的**小队收进一个 SGroup。尸体不能当目标
function FieldKit_CollectEnemies(player)

	local sg = FieldKit_State.sg_enemy
	SGroup_Clear(sg)

	for i = 1, World_GetPlayerCount() do
		local other = World_GetPlayerAt(i)
		if other ~= player and Player_GetRelationship(other, player) == R_ENEMY then
			SGroup_ForEach(Player_GetSquads(other), function(gid, idx, foe)
				if FieldKit_IsLiveTarget(foe) then
					SGroup_Add(sg, foe)
				end
			end)
		end
	end

	return sg
end


-- 自动炮击主循环：按间隔遍历我方小队，能打的就打
function FieldKit_AutoBarrage(s)

	FieldKit_State.barrage_timer = FieldKit_State.barrage_timer - s.tick
	if FieldKit_State.barrage_timer > 0 then
		return
	end
	FieldKit_State.barrage_timer = s.auto_barrage_interval

	-- 定期只清掉"这个兵种没有炮击技能"的负结果：技能可能是后来才挂上的
	-- （最终防线靠科技给），第一次查早了会把整个兵种整局拉黑。
	-- 认出来的正结果要留着——重新试探要求那一刻正好能放，很难碰上
	FieldKit_State.barrage_of_timer =
		FieldKit_State.barrage_of_timer - s.auto_barrage_interval

	if FieldKit_State.barrage_of_timer <= 0 then

		FieldKit_State.barrage_of_timer = 30

		for key, hit in pairs(FieldKit_State.barrage_of) do
			if hit == false then
				FieldKit_State.barrage_of[key] = nil
			end
		end
	end

	for idx, player in pairs(FieldKit_State.players) do

		if Player_IsAlive(player) then

			local enemies = FieldKit_CollectEnemies(player)
			local count = SGroup_CountSpawned(enemies)

			if count > 0 then

				local mine = FieldKit_State.sg_cast
				SGroup_Clear(mine)
				SGroup_AddGroup(mine, Player_GetSquads(player))

				local ready, armed, fired, blocked, busy = 0, 0, 0, 0, 0

				-- 随便挑个敌人的位置，给认技能时试探用
				local probe = nil
				SGroup_ForEach(enemies, function(g, i, foe)
					if probe == nil then
						probe = Squad_GetPosition(foe)
					end
				end)

				SGroup_ForEach(mine, function(sgroup, index, squad)

					if FieldKit_BarrageReady(squad, s) then

						ready = ready + 1
						local abils = FieldKit_BarragesOf(squad, s, probe, player)

						if abils ~= nil then

							armed = armed + 1

							local how = FieldKit_TryBarrage(idx, player, squad,
								abils, enemies, s)

							if how == "开火" then
								fired = fired + 1
							elseif how == "施法中" then
								busy = busy + 1
							else
								blocked = blocked + 1
							end
						end
					end
				end)

				-- 这一轮没开出火就每 30 秒打一行。开火成功的轮次不打，
				-- 但也不永久关掉——"打了一次就不打了"这种正是要抓的
				FieldKit_State.barrage_diag_timer =
					FieldKit_State.barrage_diag_timer - s.auto_barrage_interval

				if FieldKit_State.barrage_diag > 0 and fired == 0
					and FieldKit_State.barrage_diag_timer <= 0 then

					FieldKit_State.barrage_diag = FieldKit_State.barrage_diag - 1
					FieldKit_State.barrage_diag_timer = 30

					-- 一个有炮击技能的都没有，就把我方兵种名列出来
					local who = ""

					if armed == 0 then

						local names = {}

						SGroup_ForEach(mine, function(g, i, sq)
							if #names < 8 then
								table.insert(names,
									tostring(BP_GetName(Squad_GetBlueprint(sq))))
							end
						end)

						who = "，我方兵种: " .. table.concat(names, ", ")
					end

					print("[FieldKit] 自动开火诊断：我方 "
						.. tostring(SGroup_CountSpawned(mine))
						.. "，可开火 " .. tostring(ready)
						.. "，有炮击技能 " .. tostring(armed)
						.. "，活敌人 " .. tostring(count)
						.. "，引擎拒绝 " .. tostring(blocked)
						.. "，施法中 " .. tostring(busy)
						.. "，实放 " .. tostring(fired) .. who)
				end
			end
		end
	end
end


-- 头一次用某种施放形态时打一行，好确认铁拳到底走没走通
function FieldKit_NoteCloseForm(how)

	if FieldKit_State.close_form[how] == nil then
		FieldKit_State.close_form[how] = true
		print("[FieldKit] 近距离技能：" .. how .. "生效")
	end
end


-- 能对着这个敌人放吗。铁拳的 target 是 tp_entity_and_squad_entity，
-- 小队和实体两种都要试。这两个接口官方零调用，套 pcall 兜着
function FieldKit_CloseTarget(squad, abp, foe)

	-- 目标只能给小队或位置。官方 actionlist.scar:2293 明写着
	-- scartype(target) ~= ST_SQUAD 就不下令，实体不是合法目标
	if type(Squad_CanCastAbilityOnSquad) == "function" then
		local ok, can = pcall(Squad_CanCastAbilityOnSquad, squad, abp, foe)
		if ok and can == true then
			FieldKit_NoteCloseForm("对小队")
			return foe
		end
	end

	-- 只有小队那条接口压根不存在时才退到实体，聊胜于无
	if type(Squad_CanCastAbilityOnSquad) ~= "function"
		and type(Squad_CanCastAbilityOnEntity) == "function"
		and type(Squad_EntityAt) == "function" then

		for i = 0, 1 do

			local ok, ent = pcall(Squad_EntityAt, foe, i)

			if ok and ent ~= nil then
				local ok2, can = pcall(Squad_CanCastAbilityOnEntity,
					squad, abp, ent)
				if ok2 and can == true then
					FieldKit_NoteCloseForm("对实体")
					return ent
				end
			end
		end
	end

	return nil
end


-- 是不是反坦克武器（按名字认）
function FieldKit_IsAtWeapon(abp)

	local low = string.lower(tostring(BP_GetName(abp)))

	for _, w in pairs(FieldKit_AtWords) do
		if string.find(low, w, 1, true) ~= nil then
			return true
		end
	end

	return false
end


-- Cmd_Ability 的施法者要 SGroup，不能是裸小队。
-- 官方 foggia_retake_01.scar:478 判定用小队、下令传 SGroup，
-- actionlist.scar:2205 也只认 SGROUP / EGROUP / PLAYER 三种施法者
function FieldKit_OneSquad(squad)

	local sg = FieldKit_State.sg_one

	SGroup_Clear(sg)
	SGroup_Add(sg, squad)

	return sg
end


-- 从接口给回来的东西里抠出一个目标，返回 目标, 是不是实体。
-- 可能是小队、实体、两种组、或者一张表——单位也会打建筑，实体那路不能少
function FieldKit_FirstTargetOf(v)

	if v == nil then
		return nil, false
	end

	if type(scartype) == "function" then

		local t = scartype(v)

		if ST_SQUAD ~= nil and t == ST_SQUAD then
			return v, false
		end

		if ST_ENTITY ~= nil and t == ST_ENTITY then
			return v, true
		end

		if ST_SGROUP ~= nil and t == ST_SGROUP then

			if SGroup_CountSpawned(v) <= 0 then
				return nil, false
			end

			return SGroup_GetSpawnedSquadAt(v, 1), false
		end

		if ST_EGROUP ~= nil and t == ST_EGROUP then

			if EGroup_CountSpawned(v) <= 0 then
				return nil, false
			end

			return EGroup_GetSpawnedEntityAt(v, 1), true
		end
	end

	if type(v) == "table" and v[1] ~= nil then
		return FieldKit_FirstTargetOf(v[1])
	end

	return nil, false
end


-- 一直读不到当前攻击目标时提醒一次。没有保底，读不到就真的不放
function FieldKit_NoteNoAim()

	if FieldKit_State.aim_shape ~= nil or FieldKit_State.aim_warned then
		return
	end

	FieldKit_State.aim_warned = true

	print("[FieldKit] 还没读到过当前攻击目标（Squad_GetAttackTargets），"
		.. "在读到之前自动手雷 / 反坦克不会放")
end


-- 试出来哪种调法能用，记下来并打一行日志
function FieldKit_NoteAimShape(shape)

	if FieldKit_State.aim_shape == shape then
		return
	end

	FieldKit_State.aim_shape = shape

	print("[FieldKit] 当前攻击目标读到了（第 " .. tostring(shape) .. " 种调法）")
end


-- 这支部队正在打谁，返回 目标, 是不是实体。
-- Squad_GetAttackTargets 官方一次没用过、签名不明，所以头一回把两种调法都试一遍，
-- 哪种出东西就把编号记进 aim_shape，之后只走那一种。
-- 读不到就是没有目标，不找替代——手雷只打这支部队自己在打的东西
function FieldKit_AimedFoe(squad)

	if type(Squad_GetAttackTargets) ~= "function" then
		FieldKit_NoteNoAim()
		return nil, false
	end

	local sg = FieldKit_State.sg_aim
	local shape = FieldKit_State.aim_shape

	if shape == nil or shape == 1 then

		local ok, v = pcall(Squad_GetAttackTargets, squad)

		if ok then

			local foe, isEnt = FieldKit_FirstTargetOf(v)

			if foe ~= nil then
				FieldKit_NoteAimShape(1)
				return foe, isEnt
			end
		end
	end

	if (shape == nil or shape == 2) and sg ~= nil then

		SGroup_Clear(sg)

		local ok = pcall(Squad_GetAttackTargets, squad, sg)

		if ok and SGroup_CountSpawned(sg) > 0 then
			FieldKit_NoteAimShape(2)
			return SGroup_GetSpawnedSquadAt(sg, 1), false
		end
	end

	-- 一次都没读到过就提醒一句：可能只是它没在打人，也可能这接口用不了。
	-- 后一种情况下自动手雷会一直不放，得让人看得见
	if shape == nil then
		FieldKit_NoteNoAim()
	end

	return nil, false
end


-- 目标也包一层组用的，不能和施法者共用同一个组
function FieldKit_OneFoe(squad)

	local sg = FieldKit_State.sg_foe_one

	SGroup_Clear(sg)
	SGroup_Add(sg, squad)

	return sg
end


-- 刚给这个小队下过令就先别打扰它。每 2 秒重下一次会不停打断施法动作，
-- 结果就是命令一直在发、技能一次都放不完
-- kind 分开记：反坦克和手雷各有各的间隔，互不影响
function FieldKit_CloseBusy(squad, s, kind)

	if type(World_GetGameTime) ~= "function" then
		return false
	end

	local last = FieldKit_State.close_last[Squad_GetID(squad) .. "|" .. kind]
	local gap = (kind == "at") and s.auto_close_regap_at or s.auto_close_regap

	return last ~= nil and (World_GetGameTime() - last) < gap
end


-- 记下这个小队某一类技能刚被下过令的时间
function FieldKit_CloseMark(squad, kind)

	if type(World_GetGameTime) == "function" then
		FieldKit_State.close_last[Squad_GetID(squad) .. "|" .. kind] =
			World_GetGameTime()
	end
end


-- 是不是走不了位的固定物：机枪掩体、前哨、炮台这类。
-- 只判 emplacement 是不够的，机枪掩体压根没这个类型，见 NOTES
function FieldKit_IsFixed(squad)

	if type(Squad_IsOfType) ~= "function" then
		return false
	end

	for _, name in pairs(FieldKit_FixedTypes) do

		local ok, fixed = pcall(Squad_IsOfType, squad, name)

		if ok and fixed == true then
			return true
		end
	end

	return false
end


-- 是不是钻进了建筑 / 掩体里。进去以后它的坐标就是那栋建筑的坐标，
-- 拿来当呼叫落点，援兵全被叫到掩体上
function FieldKit_IsGarrisoned(squad)

	if type(Squad_IsInHoldEntity) ~= "function" then
		return false
	end

	local ok, inside = pcall(Squad_IsInHoldEntity, squad)

	return ok and inside == true
end


-- 单位的攻击距离，返回 nil 表示不限。炮击和近距离技能共用同一套规则：
-- 固定炮台走不了位所以不限；火箭炮这类没有普通武器的读不到距离，也不能限，
-- 否则会被全挡掉
function FieldKit_WeaponRange(squad, s)

	if not s.auto_use_weapon_range then
		return nil
	end

	if FieldKit_IsFixed(squad) then
		return nil
	end

	if type(Squad_GetEffectiveMaxWeaponRange) == "function" then

		local ok, r = pcall(Squad_GetEffectiveMaxWeaponRange, squad)

		if ok and type(r) == "number" and r > 0 then
			return r
		end
	end

	return nil
end


-- 把这个技能的射程设成这支部队的攻击距离、下限设成 0。
-- 引擎读不到技能射程（找遍了没有这个接口），与其猜不如自己定：
-- 技能真够得着了，单位就不会为了放它往前走。攻击距离会随老兵涨，所以值变了要重设
function FieldKit_SetAbilityRange(squad, abp, s)

	if not s.auto_match_ability_range
		or type(Modifier_Create) ~= "function"
		or MAT_Ability == nil or MUT_Set == nil then
		return
	end

	local r = FieldKit_WeaponRange(squad, s)

	if r == nil then
		return
	end

	local key = Squad_GetID(squad) .. "|" .. tostring(BP_GetName(abp))

	if FieldKit_State.range_set[key] == r then
		return
	end
	FieldKit_State.range_set[key] = r

	-- 第四个参数 exclusive，官方 skirmish_it.scar:5285 的 MUT_Set 也是传 true
	local ok = pcall(function()
		Modifier_ApplyToSquad(
			Modifier_Create(MAT_Ability, "ability_max_range_modifier",
				MUT_Set, true, r, abp),
			squad, 0)
		Modifier_ApplyToSquad(
			Modifier_Create(MAT_Ability, "ability_min_range_modifier",
				MUT_Set, true, 0, abp),
			squad, 0)
	end)

	if not ok and not FieldKit_State.range_warned then
		FieldKit_State.range_warned = true
		print("[FieldKit] 技能射程修饰符挂不上，退回只按攻击距离卡")
	end
end


-- 战略点、胜利点这类实体只能占领、打不动，扔雷过去纯属浪费还把步兵引过去。
-- 官方 anvil_objects.scar:40 也是这两个一起判
function FieldKit_IsCapturePoint(ent)

	if type(Entity_IsStrategicPoint) == "function" then
		local ok, yes = pcall(Entity_IsStrategicPoint, ent)
		if ok and yes == true then
			return true
		end
	end

	if type(Entity_IsVictoryPoint) == "function" then
		local ok, yes = pcall(Entity_IsVictoryPoint, ent)
		if ok and yes == true then
			return true
		end
	end

	return false
end


-- 是不是载具。反坦克武器的提示是"选择目标载具"，只能打这类
function FieldKit_IsVehicle(foe)

	if type(Squad_IsOfType) ~= "function" then
		return true
	end

	local ok, yes = pcall(Squad_IsOfType, foe, "vehicle")

	return ok and yes == true
end


-- 拿一组技能挨个试同一个目标，放出去就返回 true。
-- 只有这一个目标，放不出去就不放，不换别人
function FieldKit_CloseWith(s, squad, abils, foe, isEnt, pos, kind, d)

	for _, abp in pairs(abils) do

		local at = nil

		if not isEnt then

			at = FieldKit_CloseTarget(squad, abp, foe)

			-- 拿到的确实是小队时才包一层组（官方 actionlist.scar:2231 里
			-- target 同样可以是 SGroup）。返回实体时不能替换，否则实体被丢掉
			if at ~= nil and at == foe then
				at = FieldKit_OneFoe(foe)
			end
		end

		-- 再试"对着它所在的位置放"。还是同一个目标，只是换个下令形式
		if at == nil and pos ~= nil
			and Squad_CanCastAbilityOnPosition(squad, abp, pos) then
			at = pos
			FieldKit_NoteCloseForm("对地面")
		end

		if at ~= nil then

			-- 第四个是朝向，第五个是免费施放。花费已经被修饰符乘 0，
			-- 所以这里传 false 走正常扣费流程
			Cmd_Ability(FieldKit_OneSquad(squad), abp, at, nil, false)
			FieldKit_CloseMark(squad, kind)

			return true
		end
	end

	return false
end


-- 这个目标能不能挨手雷：活的、没倒地、不是只能占领的战略点
function FieldKit_CloseOkTarget(foe, isEnt)

	if foe == nil then
		return false
	end

	if isEnt then
		return not FieldKit_IsCapturePoint(foe)
	end

	return FieldKit_IsLiveTarget(foe) and not FieldKit_IsDowned(foe)
end


-- 放手榴弹 / 打铁拳：只打这支部队自己正在打的那个目标。
-- 读不到目标、目标不合适、放不出去，都是不放，不会换个人打
function FieldKit_TryClose(idx, player, squad, abils, s)

	local foe, isEnt = FieldKit_AimedFoe(squad)

	if not FieldKit_CloseOkTarget(foe, isEnt) then
		return
	end

	local pos = isEnt and Entity_GetPosition(foe) or Squad_GetPosition(foe)
	local d = World_DistancePointToPoint(Squad_GetPosition(squad), pos)

	local ready = {}
	local reach = FieldKit_WeaponRange(squad, s)

	-- 先把技能射程设成这支部队的攻击距离，再按同一个距离卡：
	-- 技能真够得着，单位就不会为了扔雷自己往前走
	for _, abp in pairs(abils) do

		FieldKit_SetAbilityRange(squad, abp, s)

		if reach == nil or d <= reach then
			if not (type(Squad_IsDoingAbility) == "function"
				and Squad_IsDoingAbility(squad, abp)) then
				FieldKit_ClearSquadCooldown(s, idx, player, abp)
				table.insert(ready, abp)
			end
		end
	end

	-- 武器跟着目标走：打的是载具就只用反坦克武器，别的一律用手雷。
	-- 反坦克武器打步兵引擎会静默丢弃，所以必须按名字分开
	local vehicle = (not isEnt) and FieldKit_IsVehicle(foe)
	local kind = vehicle and "at" or "other"
	local pick = {}

	for _, abp in pairs(ready) do
		if FieldKit_IsAtWeapon(abp) == vehicle then
			table.insert(pick, abp)
		end
	end

	if #pick == 0 or FieldKit_CloseBusy(squad, s, kind) then
		return
	end

	if FieldKit_CloseWith(s, squad, pick, foe, isEnt, pos, kind, d) and vehicle then
		FieldKit_NoteCloseForm("反坦克武器")
	end
end


-- 近距离技能主循环：按间隔遍历我方小队，射程内有敌人就放
function FieldKit_AutoClose(s)

	FieldKit_State.close_timer = FieldKit_State.close_timer - s.tick
	if FieldKit_State.close_timer > 0 then
		return
	end
	FieldKit_State.close_timer = s.auto_close_interval

	-- 跟炮击一样，只清"没有这个技能"的负结果
	FieldKit_State.close_of_timer =
		FieldKit_State.close_of_timer - s.auto_close_interval

	if FieldKit_State.close_of_timer <= 0 then

		FieldKit_State.close_of_timer = 30

		for key, hit in pairs(FieldKit_State.close_of) do
			if hit == false then
				FieldKit_State.close_of[key] = nil
			end
		end
	end

	for idx, player in pairs(FieldKit_State.players) do

		if Player_IsAlive(player) then

			local enemies = FieldKit_CollectEnemies(player)

			if SGroup_CountSpawned(enemies) > 0 then

				local mine = FieldKit_State.sg_cast
				SGroup_Clear(mine)
				SGroup_AddGroup(mine, Player_GetSquads(player))

				local probe = nil
				SGroup_ForEach(enemies, function(g, i, foe)
					if probe == nil then
						probe = Squad_GetPosition(foe)
					end
				end)

				SGroup_ForEach(mine, function(sgroup, index, squad)

					if FieldKit_BarrageReady(squad, s) then

						local abils = FieldKit_CloseOf(squad, s, probe, player)

						if abils ~= nil then
							FieldKit_TryClose(idx, player, squad, abils, s)
						end
					end
				end)
			end
		end
	end
end


-- 把这个技能的资源花费乘 0，走官方修饰符，不用自己退款。
-- 名字取自 attrib/ability_modifier_type.rgd 里的合法清单
FieldKit_CostMods =
{
	"ability_cost_munition", "ability_cost_manpower", "ability_cost_fuel",
}


-- 给一个技能挂上花费归零的修饰符，每个技能只需要挂一次
function FieldKit_FreeAbility(player, abp, s)

	if not s.auto_free_ammo or type(Modifier_Create) ~= "function"
		or MAT_Ability == nil or MUT_Multiplication == nil then
		return
	end

	for _, name in pairs(FieldKit_CostMods) do

		local ok = pcall(function()
			Modifier_ApplyToPlayer(
				Modifier_Create(MAT_Ability, name,
					MUT_Multiplication, false, 0, abp),
				player, 0)
		end)

		if not ok and not FieldKit_State.free_warned then
			FieldKit_State.free_warned = true
			print("[FieldKit] 花费修饰符 " .. name .. " 挂不上，技能仍然扣资源")
		end
	end
end


-- 清掉小队技能的冷却。小队技能不在 Player_GetAvailableAbilities 里，
-- 所以那边的统一清冷却盖不到，得在开炮前单独清一次
function FieldKit_ClearSquadCooldown(s, idx, player, abp)

	if s.no_ability_cooldown
		and type(Player_ResetAbilityCooldowns) == "function" then
		Player_ResetAbilityCooldowns(player, abp)
	end

	-- 修饰符只需要挂一次。冷却和花费是两回事，别互相牵连
	local seen = FieldKit_State.cd_done[idx]

	if seen == nil then
		seen = {}
		FieldKit_State.cd_done[idx] = seen
	end

	local key = BP_GetName(abp)

	if key ~= nil and seen[key] == nil then

		seen[key] = true

		if s.no_ability_cooldown then
			Modify_AbilityRechargeTime(player, abp, 0)
		end

		FieldKit_FreeAbility(player, abp, s)
	end
end


-- 给一个小队开炮：目标按距离从近到远试，技能把它会的都试一遍。
-- 距离按技能各自学到的射程卡
function FieldKit_TryBarrage(idx, player, squad, abils, enemies, s)

	local from = Squad_GetPosition(squad)
	local list = {}

	SGroup_ForEach(enemies, function(gid, i, foe)
		if FieldKit_IsLiveTarget(foe) then

			local pos = Squad_GetPosition(foe)

			table.insert(list,
				{ pos = pos, d = World_DistancePointToPoint(from, pos) })
		end
	end)

	table.sort(list, function(a, b) return a.d < b.d end)

	local busy = 0

	local reach = FieldKit_WeaponRange(squad, s)

	for _, abp in pairs(abils) do

		FieldKit_SetAbilityRange(squad, abp, s)

		if type(Squad_IsDoingAbility) == "function"
			and Squad_IsDoingAbility(squad, abp) then

			busy = busy + 1

		else

			FieldKit_ClearSquadCooldown(s, idx, player, abp)

			local tries = 0

			for _, e in ipairs(list) do

				tries = tries + 1
				if tries > s.auto_barrage_tries then
					break
				end

				if (reach == nil or e.d <= reach)
					and Squad_CanCastAbilityOnPosition(squad, abp, e.pos) then

					-- 花费同样已经被修饰符乘 0
					Cmd_Ability(FieldKit_OneSquad(squad), abp, e.pos, nil, false)

					if s.debug then
						print("[FieldKit] 自动炮击: "
							.. tostring(BP_GetName(Squad_GetBlueprint(squad)))
							.. " -> " .. tostring(BP_GetName(abp))
							.. " 距离 " .. string.format("%.0f", e.d))
					end

					return "开火"
				end
			end
		end
	end

	if busy > 0 and busy == #abils then
		return "施法中"
	end

	return "拒绝"
end


-- 游戏里那行提示的关键词。Loc_ToAnsi 吐的是系统码页，所以 GBK / UTF-8 / 英文都列上
FieldKit_Labels =
{
	attack = { "\189\248\185\165", "\232\191\155\230\148\187", "Attack", "attack" },
	callin = { "\186\244\189\208", "\229\145\188\229\143\171", "Call", "call" },
	-- "选择目标阵地"：要求能选点，把"进攻/限时"这种排掉
	position = { "\209\161\212\241\196\191\177\234\213\243\181\216",
		"\233\128\137\230\139\169\231\155\174\230\160\135\233\152\181\229\156\176",
		"position", "Position" },
}


-- 技能在游戏里那行提示（"进攻/选择目标阵地"这种），取不到返回 nil
function FieldKit_AbilityLabel(abp)

	if type(BP_GetAbilityUIInfo) ~= "function"
		or type(Loc_ToAnsi) ~= "function" then
		return nil
	end

	local ok, info = pcall(BP_GetAbilityUIInfo, abp)

	if not ok or type(info) ~= "table" or info.helpText == nil then
		return nil
	end

	local ok2, text = pcall(Loc_ToAnsi, info.helpText)

	if not ok2 or text == nil or tostring(text) == "" then
		return nil
	end

	return tostring(text)
end


-- 提示里有没有某一类的字样
function FieldKit_LabelHas(label, needles)

	for _, n in pairs(needles) do
		if string.find(label, n, 1, true) ~= nil then
			return true
		end
	end

	return false
end


-- 把技能的 UI 信息逐字段拼成一行，locstring 顺带翻成文字。排查分类用
function FieldKit_DescribeAbilityUI(abp)

	if type(BP_GetAbilityUIInfo) ~= "function" then
		return "无 UIInfo 接口"
	end

	local ok, info = pcall(BP_GetAbilityUIInfo, abp)

	if not ok or type(info) ~= "table" then
		return "UIInfo 取不到"
	end

	local parts = {}

	for k, v in pairs(info) do

		local text = tostring(v)

		if type(Loc_ToAnsi) == "function" then
			local ok2, s = pcall(Loc_ToAnsi, v)
			if ok2 and s ~= nil and tostring(s) ~= "" then
				text = text .. "«" .. tostring(s) .. "»"
			end
		end

		table.insert(parts, tostring(k) .. "=" .. text)
	end

	table.sort(parts)
	return table.concat(parts, "  ")
end


-- 技能的类别名列表（小写）。这个接口给的是合并后的值，继承来的也读得到。
-- 空表 = 被动或解锁单位，根本放不出来；接口不可用时返回 nil
function FieldKit_AbilityCategories(abp)

	if type(BP_GetAbilityCategories) ~= "function" then
		return nil
	end

	local ok, got = pcall(BP_GetAbilityCategories, abp)

	if not ok or type(got) ~= "table" then
		return nil
	end

	local names = {}

	for _, cat in pairs(got) do
		local ok2, nm = pcall(BP_GetName, cat)
		if ok2 and nm ~= nil then
			table.insert(names, string.lower(tostring(nm)))
		end
	end

	return names
end


-- 技能归哪一类，以及要不要选点。返回 "attack" / "callin" / nil 和 selfCast。
-- 游戏里那行提示最准（还顺带说明要不要选阵地），其次是类别标记，
-- 最后看名字里有没有 call_in——只有靠名字认出来的才按自身施放
function FieldKit_ClassifyAbility(name, cats, label)

	if label ~= nil then

		local pickPos = FieldKit_LabelHas(label, FieldKit_Labels.position)

		if FieldKit_LabelHas(label, FieldKit_Labels.callin) then
			return "callin", not pickPos
		end
		if pickPos and FieldKit_LabelHas(label, FieldKit_Labels.attack) then
			return "attack", false
		end
	end

	if cats ~= nil then
		for _, nm in pairs(cats) do
			if string.find(nm, "call_in", 1, true) ~= nil then
				return "callin", false
			end
		end
	end

	local low = string.lower(tostring(name or ""))

	if string.find(low, "call_in", 1, true) ~= nil
		or string.find(low, "callin", 1, true) ~= nil then
		return "callin", true
	end

	return nil, false
end


-- 最终防线：扫本阵营 hoff/<阵营>/player/ 下的技能，分进攻 / 呼叫两份并授予玩家
function FieldKit_HoffPlayerPools(s, player)

	if FieldKit_State.hoff_attack ~= nil then
		return FieldKit_State.hoff_attack, FieldKit_State.hoff_callin
	end

	local attack, callin = {}, {}
	FieldKit_State.hoff_attack = attack
	FieldKit_State.hoff_callin = callin

	if PBG_Ability == nil or type(BP_GetPropertyBagGroupCount) ~= "function" then
		return attack, callin
	end

	-- 阵营目录名两种写法都试：race name 本身，和 RaceFolder 映射出来的
	local race = string.lower(tostring(Player_GetRaceName(player)))
	local want = { ["/hoff/" .. race .. "/player/"] = true }

	if FieldKit_RaceFolder[race] ~= nil then
		want["/hoff/" .. FieldKit_RaceFolder[race] .. "/player/"] = true
	end

	local seen, granted = 0, 0

	for j = 0, BP_GetPropertyBagGroupCount(PBG_Ability) - 1 do

		local path = BP_GetPropertyBagGroupPathName(PBG_Ability, j)

		if path ~= nil then

			local norm = string.lower(string.gsub(path, "\\", "/"))
			local hit = false

			for prefix, _ in pairs(want) do
				if string.find(norm, prefix, 1, true) ~= nil then
					hit = true
				end
			end

			local leaf = string.match(norm, "([^/]+)$")

			if hit and leaf ~= nil and BP_AbilityExists(leaf) then

				seen = seen + 1

				local abp = BP_GetAbilityBlueprint(leaf)
				local kind, selfCast = FieldKit_ClassifyAbility(leaf,
					FieldKit_AbilityCategories(abp), FieldKit_AbilityLabel(abp))

				local bucket = nil

				if kind == "callin" then
					if s.auto_player_callin then
						bucket = callin
					end
				elseif kind == "attack" then
					bucket = attack
				end

				if bucket ~= nil then

					table.insert(bucket, { abp = abp, selfCast = selfCast })

					if type(Player_AddAbility) == "function"
						and (type(Player_HasAbility) ~= "function"
							or not Player_HasAbility(player, abp)) then
						Player_AddAbility(player, abp)
						granted = granted + 1
					end

					if s.no_ability_cooldown then
						Modify_AbilityRechargeTime(player, abp, 0)
					end
				end
			end
		end
	end

	print("[FieldKit] 最终防线技能池：本阵营 " .. tostring(seen)
		.. " 个玩家技能，进攻 " .. tostring(#attack)
		.. " 个，呼叫 " .. tostring(#callin)
		.. " 个，已授予 " .. tostring(granted) .. " 个")

	return attack, callin
end


-- 把技能池筛成进攻 / 呼叫两份，每个玩家只筛一次
function FieldKit_PrunePlayerAbilities(s, idx, player)

	local abils = FieldKit_State.player_abils[idx]

	if abils == nil or FieldKit_State.abils_pruned[idx] then
		return
	end

	FieldKit_State.abils_pruned[idx] = true

	local owns = (type(Player_HasAbility) == "function")
	local attackList, callinList, all, labeled = {}, {}, {}, 0

	for _, abp in pairs(abils) do
		if not owns or Player_HasAbility(player, abp) then

			local cats = FieldKit_AbilityCategories(abp)
			local label = FieldKit_AbilityLabel(abp)

			if label ~= nil then
				labeled = labeled + 1
			end

			local kind, selfCast =
				FieldKit_ClassifyAbility(BP_GetName(abp), cats, label)
			local isCallin = (kind == "callin")
			local isAttack = (kind == "attack")
			local rec = { abp = abp, selfCast = selfCast }

			table.insert(all, rec)

			if isCallin then
				if s.auto_player_callin then
					table.insert(callinList, rec)
				end
			elseif isAttack then
				table.insert(attackList, rec)
			end

			if s.dump_pool_info then
				print("[FieldKit]   " .. tostring(BP_GetName(abp))
					.. (isCallin and "  [呼叫]" or "")
					.. (isAttack and "  [进攻]" or "")
					.. "  类别=" .. table.concat(cats or {}, "/")
					.. "  " .. FieldKit_DescribeAbilityUI(abp))
			end
		end
	end

	-- 提示一个都读不到、或者两份都空，都退回全量，免得功能被静默关掉
	if #all > 0 and (labeled == 0
		or (#attackList == 0 and #callinList == 0)) then

		attackList, callinList = all, all

		print("[FieldKit] " .. (labeled == 0 and "读不到技能提示"
			or "技能分类没筛出东西") .. "，退回全量")
	end

	-- 最终防线：两类都改从本阵营全部技能里抽，空了就保留已解锁的
	if type(Hoff_GrantTechnologyForWave) == "function" then

		local hoffAttack, hoffCallin = FieldKit_HoffPlayerPools(s, player)

		if #hoffAttack > 0 then
			attackList = hoffAttack
		end
		if #hoffCallin > 0 then
			callinList = hoffCallin
		end
	end

	FieldKit_State.attack_abils[idx] = attackList
	FieldKit_State.callin_abils[idx] = callinList

	print("[FieldKit] 随机技能池：候选 " .. tostring(#abils)
		.. " 个，进攻 " .. tostring(#attackList)
		.. " 个，呼叫 " .. tostring(#callinList)
		.. " 个（读到提示 " .. tostring(labeled) .. " 个）")
end


-- 头几次把落点算成什么样打出来。不看 debug 开关：
-- 等用户自己去开 debug 等于没有诊断，但也只打前 3 次，免得刷屏
function FieldKit_NoteHome(count, skipped, pos)

	if FieldKit_State.home_logged >= 3 then
		return
	end

	FieldKit_State.home_logged = FieldKit_State.home_logged + 1

	local at = "没落点"

	if pos ~= nil then
		at = string.format("%.0f,%.0f", pos.x, pos.z)
	end

	print("[FieldKit] 呼叫落点：可用部队 " .. tostring(count)
		.. " 个（排除固定物/驻守 " .. tostring(skipped) .. " 个）-> " .. at)
end


-- 我方随便一支能动的部队旁边，呼叫类技能往这儿放。
-- 掩体、前哨这类固定物不算；躲进建筑里的也不算——它们的坐标就是那栋建筑的，
-- 用了等于把援兵叫到掩体上。一支能站在外面的都没有了才退回出生点，
-- 不再随便挑一栋建筑：实体分不出哪栋是掩体（ebps 类型都是 default）
function FieldKit_HomePosition(player, s)

	local mine = FieldKit_State.sg_cast
	SGroup_Clear(mine)
	SGroup_AddGroup(mine, Player_GetSquads(player))

	local list = {}
	local skipped = 0

	SGroup_ForEach(mine, function(gid, i, squad)
		if FieldKit_IsLiveTarget(squad) then
			if FieldKit_IsFixed(squad) or FieldKit_IsGarrisoned(squad) then
				skipped = skipped + 1
			else
				table.insert(list, Squad_GetPosition(squad))
			end
		end
	end)

	local pos = nil

	if #list > 0 then
		pos = FieldKit_PickSome(list, 1)[1]
	elseif type(Player_GetStartingPosition) == "function" then
		local ok, home = pcall(Player_GetStartingPosition, player)
		if ok then
			pos = home
		end
	end

	FieldKit_NoteHome(#list, skipped, pos)

	return pos
end


-- 这个点离最近的友军（含自己和盟友）有多远。一个友军都没有时返回 nil
function FieldKit_FriendlyDistance(player, pos)

	local best = nil

	for i = 1, World_GetPlayerCount() do

		local other = World_GetPlayerAt(i)

		if Player_GetRelationship(other, player) ~= R_ENEMY then

			SGroup_ForEach(Player_GetSquads(other), function(gid, idx, squad)
				if FieldKit_IsLiveTarget(squad) then
					local d = World_DistancePointToPoint(
						Squad_GetPosition(squad), pos)
					if best == nil or d < best then
						best = d
					end
				end
			end)
		end
	end

	return best
end


-- 这个点能不能打：友军离得够远才行
function FieldKit_SafeToStrike(player, pos, s)

	if s.auto_attack_safe_radius <= 0 then
		return true
	end

	local d = FieldKit_FriendlyDistance(player, pos)

	return d == nil or d > s.auto_attack_safe_radius
end


-- 挑进攻目标：离友军最近但仍在安全距离外的那个敌人。都不安全就返回 nil
function FieldKit_FrontlineEnemy(player, s)

	local enemies = FieldKit_CollectEnemies(player)

	if SGroup_CountSpawned(enemies) <= 0 then
		return nil
	end

	local best, bestD = nil, nil

	SGroup_ForEach(enemies, function(gid, i, foe)

		local fp = Squad_GetPosition(foe)
		local d = FieldKit_FriendlyDistance(player, fp)

		if FieldKit_SafeToStrike(player, fp, s)
			and (bestD == nil or (d or 0) < bestD) then
			best, bestD = fp, (d or 0)
		end
	end)

	return best
end


-- 从一份池子里抽一个放出去。选点还是自身施放由技能自己决定
function FieldKit_CastPlayerAbility(s, player, abils, pos, tag)

	if abils == nil or #abils == 0 then
		return false
	end

	local rec = FieldKit_PickSome(abils, 1)[1]

	if rec == nil then
		return false
	end

	local abp = rec.abp

	if not rec.selfCast and pos == nil then
		return false
	end

	-- 一律先带位置下令（第四个参数是朝向，第五个是免费施放，跟官方脚本一致）。
	-- 以前"自身施放"那类只传技能不传位置，援兵就落到引擎自己挑的点上，
	-- 最终防线里那个点正好是防线的机枪掩体。技能真不吃位置的话引擎会忽略，
	-- 连下令都不认才退回不带位置的老写法
	local placed = false

	if pos ~= nil then
		placed = pcall(Cmd_Ability, player, abp, pos, nil, true)
	end

	if not placed then
		Cmd_Ability(player, abp)
		pos = nil
	end

	FieldKit_State.player_casts = FieldKit_State.player_casts + 1

	if FieldKit_State.player_casts == 1 then
		print("[FieldKit] 随机技能开始施放，首个: " .. tostring(BP_GetName(abp)))
	end

	if s.debug then
		local at = "自身"
		if pos ~= nil then
			at = string.format("%.0f,%.0f", pos.x, pos.z)
		end
		print("[FieldKit] 随机技能(" .. tag .. "): "
			.. tostring(BP_GetName(abp)) .. " @ " .. at)
	end

	return true
end


-- 找刚进入交战状态的敌人（上次查还没打、这次在打），返回其中能安全打的那个
function FieldKit_NewlyAttackingEnemy(player, s)

	if type(Squad_IsAttacking) ~= "function" then
		return nil
	end

	local enemies = FieldKit_CollectEnemies(player)

	if SGroup_CountSpawned(enemies) <= 0 then
		return nil
	end

	local seen = {}
	local best, bestD = nil, nil

	SGroup_ForEach(enemies, function(gid, i, foe)

		if Squad_IsAttacking(foe, 3) then

			local id = Squad_GetID(foe)
			seen[id] = true

			if not FieldKit_State.was_attacking[id] then

				local fp = Squad_GetPosition(foe)
				local d = FieldKit_FriendlyDistance(player, fp)

				if FieldKit_SafeToStrike(player, fp, s)
					and (bestD == nil or (d or 0) < bestD) then
					best, bestD = fp, (d or 0)
				end
			end
		end
	end)

	-- 整张表换掉，死掉和脱战的自然消失
	FieldKit_State.was_attacking = seen

	return best
end


-- 呼叫类主循环：按间隔放一个，落点取我方部队旁边
function FieldKit_AutoCallIn(s)

	FieldKit_State.callin_timer = FieldKit_State.callin_timer - s.tick
	if FieldKit_State.callin_timer > 0 then
		return
	end
	FieldKit_State.callin_timer = s.auto_callin_interval

	for idx, player in pairs(FieldKit_State.players) do
		if Player_IsAlive(player) then

			FieldKit_PrunePlayerAbilities(s, idx, player)
			FieldKit_CastPlayerAbility(s, player,
				FieldKit_State.callin_abils[idx],
				FieldKit_HomePosition(player, s), "呼叫")
		end
	end
end


-- 进攻类主循环：敌人刚进入交战就立刻放一个，否则按间隔放
function FieldKit_AutoAttackAbility(s)

	FieldKit_State.attack_timer = FieldKit_State.attack_timer - s.tick
	FieldKit_State.combat_timer = FieldKit_State.combat_timer - s.tick
	FieldKit_State.watch_timer = FieldKit_State.watch_timer - s.tick

	-- 间隔设成 0 就是关掉定时触发，只留交战触发
	local due = (s.auto_attack_interval > 0
		and FieldKit_State.attack_timer <= 0)
	local watch = (FieldKit_State.watch_timer <= 0)

	if not due and not watch then
		return
	end

	if watch then
		FieldKit_State.watch_timer = s.auto_attack_watch
	end

	for idx, player in pairs(FieldKit_State.players) do

		if Player_IsAlive(player) then

			FieldKit_PrunePlayerAbilities(s, idx, player)

			local abils = FieldKit_State.attack_abils[idx]
			local pos, tag = nil, "进攻"

			if watch then

				-- 边沿状态每轮都要刷新，冷却里也不能跳过，
				-- 否则冷却一过会把这期间所有还在打的敌人当成新的
				local at = FieldKit_NewlyAttackingEnemy(player, s)

				if at ~= nil and FieldKit_State.combat_timer <= 0 then
					pos, tag = at, "进攻·交战"
				end
			end

			if pos == nil and due then
				pos = FieldKit_FrontlineEnemy(player, s)
			end

			if FieldKit_CastPlayerAbility(s, player, abils, pos, tag) then

				FieldKit_State.attack_timer = s.auto_attack_interval

				if tag == "进攻·交战" then
					FieldKit_State.combat_timer = s.auto_attack_combat_gap
				end
			end
		end
	end

	-- 到点了但没放出去也要重置，免得每 tick 都重扫
	if due and FieldKit_State.attack_timer <= 0 then
		FieldKit_State.attack_timer = s.auto_attack_interval
	end
end


FieldKit_RaceFolder =
{
	americans = "american",
	germans = "german",
	british = "british",
	british_africa = "british",
	afrika_korps = "afrika_korps",
}


-- 最终防线科技名 -> 对应的技能蓝图
function FieldKit_HoffAbilityOf(techName)
	local abn = string.gsub(techName, "^hoff_technology_ability_", "hoff_player_")
	if abn ~= techName and BP_AbilityExists(abn) then
		return BP_GetAbilityBlueprint(abn)
	end
	return nil
end


-- 把科技对应的技能加给玩家并清冷却
function FieldKit_EnableHoffAbilities(s, player, abils)

	local added = 0

	for _, abp in pairs(abils) do

		if type(Player_AddAbility) == "function" then
			Player_AddAbility(player, abp)
			added = added + 1
		end

		if s.no_ability_cooldown then
			Modify_AbilityRechargeTime(player, abp, 0)
		end
	end

	return added
end


-- 从表里随机取 n 个（同步安全，超出表长自动截断）
function FieldKit_PickSome(t, n)
	if n <= 0 or #t == 0 then
		return {}
	elseif n >= #t then
		return t
	elseif n == 1 then
		return { Table_GetRandomItem(t) }
	end
	return Table_GetRandomItem(t, n)
end


-- 最终防线：按被动 / 主动 / 单位三类各随机解锁若干科技
function FieldKit_HoffTechnologies(s, player, idx)

	local want = {
		passive = s.hoff_tech_passive,
		ability = s.hoff_tech_ability,
		unit    = s.hoff_tech_unit,
	}

	if want.passive <= 0 and want.ability <= 0 and want.unit <= 0 then
		FieldKit_State.bg_done[idx] = true
		print("[FieldKit] 最终防线，不解锁科技")
		return
	end

	if type(Technologies_GetAvailableTechnologies) ~= "function" then
		return
	end

	local pool = Technologies_GetAvailableTechnologies(player)
	if pool == nil then
		return
	end

	local bucket = { passive = {}, ability = {}, unit = {} }
	local must = {}
	local pooled = 0

	for _, pbg in pairs(pool) do
		if pbg ~= nil and not Player_HasUpgrade(player, pbg) then

			pooled = pooled + 1
			local nm = string.lower(tostring(BP_GetName(pbg)))

			-- 英雄类科技不占随机名额，永远解锁：奖励单位（英雄潘兴）靠它带出来
			if string.find(nm, "_hero_", 1, true) ~= nil then
				table.insert(must, { pbg = pbg, name = nm })
			else
				for kind, _ in pairs(bucket) do
					if string.find(nm, "hoff_technology_" .. kind .. "_",
						1, true) == 1 then
						table.insert(bucket[kind], { pbg = pbg, name = nm })
						break
					end
				end
			end
		end
	end

	if pooled == 0 then
		return
	end

	local cpBefore = nil
	if type(Player_GetResource) == "function" and RT_Command ~= nil then
		cpBefore = Player_GetResource(player, RT_Command)
	end

	local got = { passive = 0, ability = 0, unit = 0 }
	local heroes = 0
	local abils = {}

	for _, r in pairs(must) do

		if not Player_HasUpgrade(player, r.pbg) then
			Player_SetUpgradeAvailability(player, r.pbg, ITEM_UNLOCKED)
			Player_CompleteUpgrade(player, r.pbg)
		end

		if Player_HasUpgrade(player, r.pbg) then
			heroes = heroes + 1
			if s.debug then
				print("[FieldKit]   hero: " .. r.name)
			end
		end
	end

	for kind, list in pairs(bucket) do
		for _, r in pairs(FieldKit_PickSome(list, want[kind])) do

			if not Player_HasUpgrade(player, r.pbg) then
				Player_SetUpgradeAvailability(player, r.pbg, ITEM_UNLOCKED)
				Player_CompleteUpgrade(player, r.pbg)
			end

			if Player_HasUpgrade(player, r.pbg) then

				got[kind] = got[kind] + 1

				if s.debug then
					print("[FieldKit]   " .. kind .. ": " .. r.name)
				end

				if kind == "ability" then
					local abp = FieldKit_HoffAbilityOf(r.name)
					if abp ~= nil then
						table.insert(abils, abp)
					end
				end
			end
		end
	end

	local added = FieldKit_EnableHoffAbilities(s, player, abils)

	FieldKit_State.player_abils[idx] = abils

	if cpBefore ~= nil then
		local cpAfter = Player_GetResource(player, RT_Command)
		if cpAfter ~= cpBefore then
			Player_SetResource(player, RT_Command, cpBefore)
			print("[FieldKit] 指挥点还原 " .. tostring(cpAfter)
				.. " -> " .. tostring(cpBefore))
		end
	end

	FieldKit_State.bg_done[idx] = true

	print("[FieldKit] 最终防线：候选 " .. tostring(pooled)
		.. " 个（被动 " .. tostring(#bucket.passive)
		.. " / 主动 " .. tostring(#bucket.ability)
		.. " / 单位 " .. tostring(#bucket.unit) .. "）")

	print("[FieldKit] 已解锁：被动 " .. tostring(got.passive)
		.. " / 主动 " .. tostring(got.ability)
		.. " / 单位 " .. tostring(got.unit)
		.. " / 英雄 " .. tostring(heroes)
		.. "，技能解析出 " .. tostring(#abils)
		.. " 个、已加给玩家 " .. tostring(added) .. " 个")
end


-- 升级名 -> 注册表路径。全表两千多条，只扫一次
function FieldKit_UpgradePaths()

	if FieldKit_State.bg_paths ~= nil then
		return FieldKit_State.bg_paths
	end

	local pathOf = {}

	for j = 0, BP_GetPropertyBagGroupCount(PBG_Upgrade) - 1 do

		local path = BP_GetPropertyBagGroupPathName(PBG_Upgrade, j)

		if path ~= nil then
			local norm = string.lower(string.gsub(path, "\\", "/"))
			local leaf = string.match(norm, "([^/]+)$")
			if leaf ~= nil then
				pathOf[leaf] = norm
			end
		end
	end

	FieldKit_State.bg_paths = pathOf

	return pathOf
end


-- 把一个战斗群的所有节点买满（含互斥分支两侧），返回买到的技能表
function FieldKit_BuyBranches(player, info)

	local abils, got, total = {}, 0, 0

	for _, branch in pairs(info.branches) do
		for _, upgrade in pairs(branch.upgrades) do

			total = total + 1

			if not Player_HasUpgrade(player, upgrade) then
				Player_SetUpgradeAvailability(player, upgrade, ITEM_UNLOCKED)
				Player_CompleteUpgrade(player, upgrade)
			end

			if Player_HasUpgrade(player, upgrade) then
				got = got + 1
			end

			local un = BP_GetName(upgrade)

			if un ~= nil and BP_AbilityExists(tostring(un)) then
				table.insert(abils, BP_GetAbilityBlueprint(tostring(un)))
			end
		end
	end

	return abils, got, total
end


-- 只买玩家自己选的那个战斗群。没选之前什么都不做，一直等着；
-- 中途选了、或者换了别的，下一轮就接上
function FieldKit_UnlockChosenBattlegroup(s, idx, player, folder)

	local pathOf = FieldKit_UpgradePaths()
	local needle = folder .. "/battlegroups/"

	for _, techtree in pairs(BP_GetTechTreeBlueprintsByType("battlegroup")) do

		local info = BP_GetTechTreeBPInfo(techtree)
		local act = info.activation_upgrade
		local name = string.lower(tostring(BP_GetName(act)))
		local actPath = pathOf[name]
		local key = tostring(idx) .. "|" .. name

		-- 是本阵营的、玩家自己点开了的、还没买过的
		if actPath ~= nil
			and string.find(actPath, needle, 1, true) ~= nil
			and not FieldKit_State.bg_seen[key]
			and Player_HasUpgrade(player, act) then

			FieldKit_State.bg_seen[key] = true

			local cpBefore = nil
			if type(Player_GetResource) == "function" and RT_Command ~= nil then
				cpBefore = Player_GetResource(player, RT_Command)
			end

			local abils, got, total = FieldKit_BuyBranches(player, info)

			print("[FieldKit] 战斗群 " .. name .. " 买满节点 "
				.. tostring(got) .. "/" .. tostring(total)
				.. "，技能 " .. tostring(#abils) .. " 个")

			if cpBefore ~= nil then
				local cpAfter = Player_GetResource(player, RT_Command)
				if cpAfter ~= cpBefore then
					Player_SetResource(player, RT_Command, cpBefore)
					print("[FieldKit] 指挥点还原 " .. tostring(cpAfter)
						.. " -> " .. tostring(cpBefore))
				end
			end

			-- 追加而不是覆盖：换战斗群时两边的技能都留着
			local pool = FieldKit_State.player_abils[idx] or {}
			for _, abp in pairs(abils) do
				table.insert(pool, abp)
			end
			FieldKit_State.player_abils[idx] = pool

			-- 池子变了，随机技能那边要重新筛一次
			FieldKit_State.abils_pruned[idx] = nil

			if s.no_ability_cooldown then
				for _, abp in pairs(abils) do
					Modify_AbilityRechargeTime(player, abp, 0)
				end
			end
		end
	end
end


-- 买满玩家选的那个战斗群的所有节点，买完还原指挥点
function FieldKit_UnlockBattlegroups(s)

	FieldKit_State.bg_timer = FieldKit_State.bg_timer - s.tick
	if FieldKit_State.bg_timer > 0 then
		return
	end
	FieldKit_State.bg_timer = 1.0

	for idx, player in pairs(FieldKit_State.players) do

		local hoff = (type(Hoff_GrantTechnologyForWave) == "function")
		local folder = FieldKit_RaceFolder[Player_GetRaceName(player)]

		if hoff then

			-- 最终防线那边是一次性的，做完就不用再来
			if not FieldKit_State.bg_done[idx] then
				FieldKit_HoffTechnologies(s, player, idx)
			end

		elseif folder ~= nil then

			-- 遭遇战这边要一直盯着：玩家什么时候点开战斗群都能接上
			FieldKit_UnlockChosenBattlegroup(s, idx, player, folder)
		end
	end
end


-- 把玩家级技能的充能时间清零。按技能名去重，避免修饰符叠加
function FieldKit_ClearAbilityCooldowns(s)

	FieldKit_State.cd_timer = FieldKit_State.cd_timer - s.tick
	if FieldKit_State.cd_timer > 0 then
		return
	end
	FieldKit_State.cd_timer = 2.0

	for idx, player in pairs(FieldKit_State.players) do

		local seen = FieldKit_State.cd_done[idx]
		if seen == nil then
			seen = {}
			FieldKit_State.cd_done[idx] = seen
		end

		for _, abp in pairs(Player_GetAvailableAbilities(player)) do

			local key = BP_GetName(abp)

			if key ~= nil and seen[key] == nil then
				seen[key] = true
				Modify_AbilityRechargeTime(player, abp, 0)

				if s.debug then
					print("[FieldKit] 技能清冷却: " .. tostring(key))
				end
			end
		end
	end
end


-----------------------------------------------------------------------
-----------------------------------------------------------------------

-- 场景守卫：主菜单背景、战役大地图等不该跑的场景挡掉
function FieldKit_ShouldRun()

	if type(Game_IsFrontEndScenario) == "function" and Game_IsFrontEndScenario() then
		return false
	end

	if type(Game_HasLocalPlayer) == "function" and not Game_HasLocalPlayer() then
		return false
	end

	if not FieldKit_Settings.enable_on_campaign_map
		and type(World_IsCampaignMetamapGame) == "function"
		and World_IsCampaignMetamapGame() then
		return false
	end

	return true
end


-----------------------------------------------------------------------
-----------------------------------------------------------------------

-- 首次运行的初始化：建组、挑出生效的玩家、开视野
function FieldKit_LazyInit()

	local s = FieldKit_Settings

	FieldKit_State.sg_reinforce = SGroup_CreateIfNotFound("sg_fieldkit_reinforce")
	FieldKit_State.eg_entities = EGroup_CreateIfNotFound("eg_fieldkit_entities")
	FieldKit_State.sg_enemy = SGroup_CreateIfNotFound("sg_fieldkit_enemy")
	FieldKit_State.sg_cast = SGroup_CreateIfNotFound("sg_fieldkit_cast")
	FieldKit_State.sg_one = SGroup_CreateIfNotFound("sg_fieldkit_one")
	FieldKit_State.sg_foe_one = SGroup_CreateIfNotFound("sg_fieldkit_foe_one")
	FieldKit_State.sg_aim = SGroup_CreateIfNotFound("sg_fieldkit_aim")
	FieldKit_State.players = {}
	FieldKit_State.accuracy_done = {}
	FieldKit_State.cd_done = {}

	for i = 1, World_GetPlayerCount() do

		local player = World_GetPlayerAt(i)
		local take

		if s.apply_to == "all" then
			take = true
		elseif s.apply_to == "humans" then
			take = Player_IsHuman(player)
		else
			take = (player == Game_GetLocalPlayer())
		end

		if take then
			table.insert(FieldKit_State.players, player)
		end
	end

	FieldKit_State.ready = true

	if s.reveal_map then
		for _, player in pairs(FieldKit_State.players) do
			FOW_PlayerRevealAll(player)
		end
	end

	print("[FieldKit] 已启用（版本 " .. FieldKit_Build
		.. "），生效玩家数：" .. tostring(#FieldKit_State.players))
end


-----------------------------------------------------------------------
-----------------------------------------------------------------------

-- 主循环，每 tick 调一次，按开关分发到各功能
function FieldKit_Update()

	if not FieldKit_ShouldRun() then
		return
	end

	if not FieldKit_State.ready then
		FieldKit_LazyInit()
	end

	local s = FieldKit_Settings

	if s.unlock_battlegroup_nodes then
		FieldKit_UnlockBattlegroups(s)
	end

	if s.auto_barrage then
		FieldKit_AutoBarrage(s)
	end

	if s.auto_close then
		FieldKit_AutoClose(s)
	end

	if s.auto_player_ability then
		FieldKit_AutoCallIn(s)
		FieldKit_AutoAttackAbility(s)
	end

	if s.no_ability_cooldown then
		FieldKit_ClearAbilityCooldowns(s)
	end

	for _, player in pairs(FieldKit_State.players) do
		if Player_IsAlive(player) then

			FieldKit_ProcessSquads(player, s)

			if s.repair_buildings or s.max_veterancy or s.no_ability_cooldown then
				FieldKit_ProcessEntities(player, s)
			end

		end
	end
end


-----------------------------------------------------------------------
-----------------------------------------------------------------------

-- 遍历玩家的小队。升星额外走一趟全量遍历（含未生成的）
function FieldKit_ProcessSquads(player, s)

	local sg = Player_GetSquads(player)

	SGroup_ForEach(sg, function(sgroup, index, squad)
		FieldKit_ProcessSquad(squad, s)
	end)

	if not s.max_veterancy then
		return
	end

	local n = SGroup_Count(sg)

	for i = 1, (n or 0) do
		local squad = SGroup_GetSquadAt(sg, i)
		if squad ~= nil and Squad_IsAlive(squad) then
			FieldKit_MaxVeterancy(squad, s)
		end
	end
end


-- 单个小队：升星、命中率、清冷却，脱战后再回血 / 补员
function FieldKit_ProcessSquad(squad, s)

	if not Squad_IsAlive(squad) then
		return
	end

	if s.max_veterancy then
		FieldKit_MaxVeterancy(squad, s)
	end

	if s.perfect_accuracy then
		FieldKit_ApplyAccuracy(squad, s)
	end

	if s.no_ability_cooldown then
		Squad_AdjustAbilityCooldown(squad, -s.cooldown_drain)
	end

	if Squad_IsRetreating(squad) then
		return
	end

	if Squad_IsUnderAttack(squad, s.out_of_combat) or Squad_IsAttacking(squad, s.out_of_combat) then
		return
	end

	local is_vehicle = Squad_HasVehicle(squad)

	local enabled, rate
	if is_vehicle then
		enabled, rate = s.repair_vehicles, s.vehicle_repair_per_second
	else
		enabled, rate = s.heal_infantry, s.infantry_heal_per_second
	end

	if enabled and rate > 0 then
		FieldKit_HealMembers(squad, rate * s.tick, s)
	end

	if s.auto_reinforce and not is_vehicle
		and not Squad_IsReinforcing(squad) and Squad_CanInstantReinforceNow(squad) then

		SGroup_Clear(FieldKit_State.sg_reinforce)
		SGroup_Add(FieldKit_State.sg_reinforce, squad)

		LocalCommand_Squad(
			Squad_GetPlayerOwner(squad),
			FieldKit_State.sg_reinforce,
			SCMD_InstantReinforceUnit,
			false)

		if s.debug then
			print("[FieldKit] reinforce squad " .. tostring(Squad_GetID(squad)))
		end
	end
end


-- 逐个成员回血。不能用 Squad_SetHealth，它会把所有成员拉成同一值
function FieldKit_HealMembers(squad, amount, s)

	for i = 0, Squad_Count(squad) - 1 do

		local entity = Squad_EntityAt(squad, i)

		if Entity_IsAlive(entity) then

			local health = Entity_GetHealthPercentage(entity)

			if health > 0 and health < 1.0 then

				local healed = math.min(1.0, health + amount)
				Entity_SetHealth(entity, healed)

				if s.debug then
					print(string.format("[FieldKit] heal %s[%d]: %.2f -> %.2f",
						tostring(Squad_GetID(squad)), i, health, healed))
				end
			end
		end
	end
end


-- 给小队武器挂命中率修饰符，每个小队只挂一次
function FieldKit_ApplyAccuracy(squad, s)

	local id = Squad_GetID(squad)

	if FieldKit_State.accuracy_done[id] then
		return
	end
	FieldKit_State.accuracy_done[id] = true

	Modifier_ApplyToSquad(
		Modifier_Create(MAT_Weapon, "accuracy_weapon_modifier", MUT_Multiplication,
			false, s.accuracy_multiplier, s.accuracy_hardpoint),
		squad, 0)

	Modifier_ApplyToSquad(
		Modifier_Create(MAT_Weapon, "weapon_moving_accuracy_modifier", MUT_Multiplication,
			false, s.accuracy_multiplier, s.accuracy_hardpoint),
		squad, 0)

	if s.debug then
		print("[FieldKit] accuracy squad " .. tostring(id))
	end
end


-- 把小队升到满星
function FieldKit_MaxVeterancy(squad, s)

	local rank = Squad_GetVeterancyRank(squad)
	local max_rank = Squad_GetMaxVeterancyRank(squad) or 0

	if max_rank > 0 and rank < max_rank then
		Squad_IncreaseVeterancyRank(squad, max_rank - rank, true)
	end
end


-----------------------------------------------------------------------
-----------------------------------------------------------------------

-- 遍历玩家的实体（建筑、防御工事等）
function FieldKit_ProcessEntities(player, s)

	EGroup_Clear(FieldKit_State.eg_entities)
	Player_GetAll(player, FieldKit_State.eg_entities)

	EGroup_ForEach(FieldKit_State.eg_entities, function(egroup, index, entity)
		FieldKit_ProcessEntity(entity, s)
	end)
end


-- 单个实体：升星、清冷却，脱战后修复
function FieldKit_ProcessEntity(entity, s)

	if Entity_IsPartOfSquad(entity) then
		return
	end

	if not Entity_IsSpawned(entity) or not Entity_IsAlive(entity) then
		return
	end

	if Entity_IsWreck(entity) or Entity_IsPlannedStructure(entity) then
		return
	end

	if Entity_IsStrategicPoint(entity) or Entity_IsInvulnerable(entity) then
		return
	end


	if s.max_veterancy then
		FieldKit_MaxVeterancyEntity(entity, s)
	end

	if s.no_ability_cooldown then
		Entity_AdjustAbilityCooldown(entity, -s.cooldown_drain)
	end

	if not s.repair_buildings then
		return
	end

	if Entity_IsUnderAttack(entity, s.out_of_combat) then
		return
	end

	local health = Entity_GetHealthPercentage(entity)

	if health > 0 and health < 1.0 then

		local repaired = math.min(1.0, health + s.building_repair_per_second * s.tick)
		Entity_SetHealth(entity, repaired)

		if s.debug then
			print(string.format("[FieldKit] repair entity %s: %.2f -> %.2f",
				tostring(Entity_GetID(entity)), health, repaired))
		end
	end
end


-- 把实体升到满星
function FieldKit_MaxVeterancyEntity(entity, s)

	local rank = Entity_GetVeterancyRank(entity)
	local max_rank = Entity_GetMaxVeterancyRank(entity) or 0

	if max_rank > 0 and rank < max_rank then
		Entity_IncreaseVeterancyRank(entity, max_rank - rank, true)
	end
end


-----------------------------------------------------------------------
-----------------------------------------------------------------------

if not Rule_Exists(FieldKit_Update) then
	Rule_AddInterval(FieldKit_Update, FieldKit_Settings.tick)
end

]==])