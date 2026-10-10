local root
local source = debug.getinfo(1, "S").source
if source:sub(1, 1) == "@" then root = source:sub(2):match("^(.*[/\\])Scripts[/\\][^/\\]+$") end
if not root then
    local dirs = IterateGameDirectories()
    root = dirs.Game.Binaries.Win64.__absolute_path .. "/ue4ss/Mods/AC8SkinManager/"
end
package.path = root .. "Scripts/?.lua;" .. package.path
local json, Core, Adapter, Menu, Registry = require("json"), require("core"), require("adapter"), require("menu"), require("registry")
local NativeMode = require("native_mode")
local Storage = require("storage")
local function log(message) print("[AC8SkinManager] " .. tostring(message) .. "\n") end
local function read(name, default)
    local check = name == "config.json" and Storage.config or name == "catalog.json" and Storage.catalog or Storage.selections
    return Storage.read(root .. name, default, check, json, log)
end
local function persist(saved)
    Storage.write(root .. "selections.json", saved, json)
end
-- The installed UE4SS build supports an explicit execution method. Keep this
-- local to our mod instead of changing the shared UE4SS settings file.
local game_thread_method = EGameThreadMethod and ProcessEventAvailable == true and EGameThreadMethod.ProcessEvent
local game_thread_started = false
local function game_thread(callback)
    local function run()
        if not game_thread_started then
            game_thread_started = true; log("游戏线程回调已执行")
        end
        callback()
    end
    if game_thread_method then return ExecuteInGameThread(run, game_thread_method) end
    return ExecuteInGameThread(run)
end
local config = read("config.json", {runtime_switch_enabled = true, package_registration_enabled = true, diagnostic_self_test = false})
for _, key in ipairs({"runtime_switch_enabled", "package_registration_enabled", "mission_switch_enabled"}) do
    if config[key] == nil then config[key] = true end
end
config.hangar_widget_candidates = config.hangar_widget_candidates or {
    "WBP_Menu_Hangar_AircraftSettings_Select_000_C", "WBP_Menu_Hangar_AircraftSettings_000_C"}
local catalog = read("catalog.json", {schema_version = 1, aircraft = {}, skins = {}})
local ok, registered = pcall(function()
    local tree = IterateGameDirectories().Game.Binaries.Win64.ue4ss.Mods.AC8SkinManager.Skins
    return Registry.discover(tree, json, log)
end)
if ok then
    catalog.skins = registered
else
    catalog.skins = {}
    log("独立皮肤目录尚未读取：" .. tostring(registered))
end
local core = Core.new(catalog, read("selections.json", {selections = {}}), persist)
local adapter, menu = Adapter.new(config, catalog.aircraft, root), Menu.new()
local native_mode = NativeMode.new()
local binding_capture = require("binding_capture").new(root, adapter, json)
local last_probe_time = 0
local function capture_probe(reason)
    local now = os.time()
    if reason ~= "F7" and now - last_probe_time < 5 then return end
    last_probe_time = now
    local ok, result = pcall(function() return adapter:probe() end)
    if not ok then result = "Probe failed: " .. tostring(result) end
    local file, err = io.open(root .. "interface-probe.txt", "wb")
    if file then
        file:write("Menu test: " .. tostring(reason or "F7") .. "\n", result)
        file:close()
        log("接口记录已保存：AC8SkinManager/interface-probe.txt")
    else log("接口记录无法保存：" .. tostring(err)) end
end
local last_restore_attempt, last_restore_time, restore_failures = nil, 0, 0
local last_ui_state, last_status_time = nil, 0
local function report_ui(state, message, ctx)
    local now = os.time()
    local identity = state .. "|" .. tostring(message) .. "|" .. tostring(ctx and ctx.ui_fingerprint)
    if identity == last_ui_state and now - last_status_time < 5 then return end
    if identity ~= last_ui_state then log(state .. ": " .. tostring(message)) end
    last_ui_state, last_status_time = identity, now
    local file = io.open(root .. "menu-status.json", "wb")
    if file then
        file:write(json.encode({state = state, message = tostring(message), updated_at = now,
            revision = "20261009-native-coexistence", apply_status = core.status,
            package_registry = adapter.native_registry,
            dispatcher = game_thread_method and "ProcessEvent" or "default",
            aircraft_id = ctx and ctx.aircraft_id, model_ready = ctx and ctx.model_ready,
            layout = menu.layout, selected_skin = core.saved.selections[core.aircraft or ""], applied_skin = core.applied_skin,
            discovery = adapter.discovery or {}}))
        file:close()
    end
end
local active_component
local function set_context(ctx)
    local changed = core:set_aircraft(ctx and ctx.aircraft_id or nil)
    if ctx and ctx.model_ready ~= false and active_component ~= ctx.fingerprint then
        active_component = ctx.fingerprint; core.applied_skin = "original"
        last_restore_attempt = nil; restore_failures = 0
    elseif not ctx and active_component then
        active_component = nil; last_restore_attempt = nil
    end
    if changed and ctx and not config.runtime_switch_enabled then
        core.status = "点击按钮 · 页面测试"
    end
end
local function choose(ctx, index)
    if not ctx or ctx.interactive == false or not ctx.aircraft_id then return end
    if not index or not core:rows()[index] then return end
    core.opened, core.cursor = true, index
    if not config.runtime_switch_enabled then
        core.applied_skin = core:rows()[index].id
        core.status = "已点击：" .. core:rows()[index].name .. "（页面测试）"
        log(core.status)
        return
    end
    local success, message = core:apply(adapter)
    last_restore_attempt = nil; restore_failures = 0 -- explicit click permits a fresh attempt
    native_mode:sync(adapter, core, config.runtime_switch_enabled)
    log(message)
end
local function restore_saved(ctx)
    if not config.runtime_switch_enabled or ctx.model_ready == false or not ctx.aircraft_id then return end
    local selected = core.saved.selections[ctx.aircraft_id]
    if not selected then return end
    local token = ctx.fingerprint .. "|" .. selected
    if token ~= last_restore_attempt then restore_failures = 0 end
    local rows = ctx.phase == "mission" and catalog.skins or core:rows()
    for _, row in ipairs(rows) do
        if row.id == selected and row.aircraft_id == ctx.aircraft_id and (row.status == "ready" or row.id == "original") then
            if adapter:is_applied(ctx, row) then
                core.applied_skin = selected; last_restore_attempt = nil; return
            end
            -- A native refresh has removed our material: clear the stale
            -- highlight immediately and retry transient load failures later.
            core.applied_skin = ""
            local now = os.time()
            if last_restore_attempt == token and (restore_failures >= 3 or now - last_restore_time < 3) then return end
            last_restore_attempt, last_restore_time = token, now
            local success, message = adapter:apply(ctx, row)
            if success then core.applied_skin = selected; restore_failures = 0
            else restore_failures = restore_failures + 1 end
            if message then core.status = message end
            if not success then log(message) end
            return
        end
    end
end
local diagnostic_done = false
local function diagnostic_roundtrip(ctx)
    if not config.diagnostic_self_test or diagnostic_done or ctx.model_ready == false
        or ctx.aircraft_id ~= "PP0021_su57" then return end
    diagnostic_done = true
    local result = {revision = "20261008-native-authority", aircraft_id = ctx.aircraft_id,
        scope = "Independent texture loading and hangar material readback; visual and flight checks are separate.",
        steps = {}, updated_at = os.time()}
    local original = core:rows()[1]
    local ok, error_message = pcall(function()
        local skin
        for _, row in ipairs(core:rows()) do if row.status == "ready" then skin = row; break end end
        assert(skin, "没有可测试的独立皮肤")
        if adapter.material_snapshot then result.native_before = adapter:material_snapshot(ctx, skin.bindings) end
        for cycle = 1, 2 do
            for _, row in ipairs({skin, original}) do
                local applied, message = adapter:apply(ctx, row)
                assert(applied, message)
                assert(adapter:is_applied(ctx, row), "材质读回与请求不一致")
                result.steps[#result.steps + 1] = {cycle = cycle, skin = row.id, passed = true,
                    materials = adapter.material_snapshot and adapter:material_snapshot(ctx, skin.bindings) or nil}
            end
        end
        if adapter.material_snapshot then result.native_after = adapter:material_snapshot(ctx, skin.bindings) end
        result.texture_dimensions = {}
        for path, texture in pairs(adapter.textures) do
            local dimensions = {path = path}
            pcall(function() dimensions.width = texture:Blueprint_GetSizeX(); dimensions.height = texture:Blueprint_GetSizeY() end)
            result.texture_dimensions[#result.texture_dimensions + 1] = dimensions
        end
    end)
    result.passed, result.error = ok, not ok and tostring(error_message) or nil
    -- Diagnostic operations never save selections and always leave the native
    -- material restored; restore_saved below reapplies the user's saved choice.
    local restored, restore_message = adapter:apply(ctx, original)
    result.restored_original, result.restore_message = restored, restore_message
    if not restored then result.passed = false end
    result.package_registry = adapter.native_registry
    local file = io.open(root .. "switch-diagnostic.json", "wb")
    if file then file:write(json.encode(result)); file:close() end
    log("涂装往返检查：" .. tostring(result.passed) .. (result.error and (" " .. result.error) or ""))
end
local function update(action, diagnose_failure)
    game_thread(function()
        local ok, err = pcall(function()
            local ctx, why = adapter:context()
            set_context(ctx)
            if not ctx then
                menu:hide()
                report_ui("waiting", why)
                if action then log(why) end
                if diagnose_failure then capture_probe(why) end
                return
            end
            if action then action(ctx) end
            local good, reason = menu:render(core, ctx)
            if not good then
                report_ui("mount-failed", reason, ctx)
                core.opened = false; log(reason)
                if diagnose_failure then capture_probe(reason) end
            else
                report_ui("mounted", "LIVERY 按钮已挂载", ctx)
            end
        end)
        if not ok then
            menu:hide(); log(err)
            if diagnose_failure then capture_probe(err) end
        end
    end)
end
local function bind(key, callback)
    if IsKeyBindRegistered(key) then log("按键被其他 MOD 占用：" .. tostring(key)); return end
    RegisterKeyBind(key, callback)
end
menu.on_click = function(index, ui_key)
    -- poll() already runs on the game thread. A second queued callback can
    -- outlive the clicked widget while the native page changes aircraft.
    local ctx = adapter:context()
    set_context(ctx)
    if not ctx or (ctx.ui_fingerprint or ctx.fingerprint) ~= ui_key then return end
    choose(ctx, index)
    menu:render(core, ctx)
end
bind(Key.F6, function() update(function() core.opened = true; core.status = "点击按钮 · 滚轮查看更多" end, true) end)
bind(Key.F9, function() update(function() core.opened = true; core:move(-1) end) end)
bind(Key.F10, function() update(function() core.opened = true; core:move(1) end) end)
bind(Key.F11, function() update(function(ctx)
    choose(ctx, core.cursor)
end) end)
bind(Key.F7, function()
    game_thread(function()
        capture_probe("F7")
        local ok, result = pcall(function() return binding_capture:save() end)
        log(ok and ("材质记录已保存：" .. result.aircraft_id) or tostring(result))
    end)
end)
local pending, pending_since, pending_warned = false, 0, false
local last_ui_error
local input_pending = false
local idle_ticks = 0
local has_skins = #catalog.skins > 0
-- Notifications invalidate discovery only; they never touch a partially built UObject.
if has_skins and type(NotifyOnNewObject) == "function" then
    pcall(NotifyOnNewObject, "/Script/UMG.UserWidget", function()
        adapter.discovery_dirty = true
    end)
end
LoopAsync(1200, function()
    -- File check only. Actual UObject capture is explicitly requested and
    -- dispatched once on the game thread, including with an empty skin library.
    if not pending and not input_pending then
        local request = io.open(root .. "binding-request.json", "rb")
        if request then
            request:close()
            pending, pending_since, pending_warned = true, os.time(), false
            local queued = pcall(game_thread, function()
                pcall(function() binding_capture:poll() end)
                pending = false
            end)
            if not queued then pending = false end
            return false
        end
    end
    if not has_skins then
        if last_ui_state ~= "inactive" then report_ui("inactive", "未安装涂装，自动扫描已休眠") end
        return false
    end
    if input_pending then return false end
    if not menu.panel then
        idle_ticks = idle_ticks + 1
        if idle_ticks % 3 ~= 1 then return false end -- 3.6s outside aircraft selection
    end
    if pending then
        if not pending_warned and os.time() - pending_since >= 5 then
            pending_warned = true
            report_ui("dispatch-pending", "游戏线程尚未执行已排队的界面检查")
        end
        return false
    end
    pending, pending_since, pending_warned = true, os.time(), false
    local queued, queue_error = pcall(game_thread, function()
        local ok, err = pcall(function()
            local ctx, why = adapter:context()
            if adapter.prune then adapter:prune() end
            set_context(ctx)
            if ctx then diagnostic_roundtrip(ctx); restore_saved(ctx)
            elseif adapter.mission_context then
                local needed = false
                for _, skin in ipairs(catalog.skins) do
                    if skin.status == "ready" and core.saved.selections[skin.aircraft_id] == skin.id then needed = true; break end
                end
                local mission = needed and adapter:mission_context()
                if mission then restore_saved(mission) else last_restore_attempt = nil end
            else last_restore_attempt = nil end
            native_mode:sync(adapter, core, config.runtime_switch_enabled)
            local good, reason = menu:render(core, ctx)
            if not ctx then
                report_ui("waiting", why)
                if adapter.discovery and adapter.discovery.hangar_bodies > 0 and last_ui_error ~= why then
                    last_ui_error = why; capture_probe(why)
                end
            elseif good then
                report_ui("mounted", "LIVERY 按钮已挂载", ctx)
            else
                report_ui("mount-failed", reason, ctx)
            end
            if ctx and not good and last_ui_error ~= reason then
                last_ui_error = reason; log(reason); capture_probe(reason)
            elseif good then last_ui_error = nil end
        end)
        pending = false
        if not ok then log(err) end
    end)
    if not queued then
        pending = false; report_ui("dispatch-failed", queue_error)
    end
    return false
end)
local phase_ticks = 0
LoopAsync(33, function()
    if input_pending or pending or not has_skins or not menu.panel then return false end
    phase_ticks = phase_ticks + 1
    local check_phase = phase_ticks >= 8
    if check_phase then phase_ticks = 0 end
    input_pending = true
    local queued, queue_error = pcall(game_thread, function()
        local ok, err = pcall(function()
            if check_phase then
                local ctx = adapter:context()
                set_context(ctx)
                if ctx then restore_saved(ctx) end
                native_mode:sync(adapter, core, config.runtime_switch_enabled)
                -- Reconcile aircraft identity, actual materials and attachment
                -- together; this also rebuilds rows after a native actor swap.
                menu:render(core, ctx)
            end
            menu:poll()
        end)
        input_pending = false
        if not ok then menu:hide(); log(err) end
    end)
    if not queued then input_pending = false; log(queue_error) end
    return false
end)
log("按钮测试版已加载。选机界面自动显示四列按钮，F7 采集接口。")
log("本组件线程回调方式：" .. (game_thread_method and "ProcessEvent" or "default"))
