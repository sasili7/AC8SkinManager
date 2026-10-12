-- Candidate discovery uses actual cooked widget names. Runtime writes stay gated
-- until the selected-plane/material bindings have been captured in-game.
local Adapter = {}
Adapter.__index = Adapter

local function valid(object)
    local ok, result = pcall(function() return object and object:IsValid() end)
    return ok and result == true
end

local function name(object)
    if not valid(object) then return "" end
    local ok, result = pcall(function() return object:GetFullName() end)
    return ok and result or ""
end

local function all(class)
    local ok, objects = pcall(FindAllOf, class)
    return ok and objects or {}
end

-- AC8 embeds its menu widgets in its own UI layer. IsInViewport() is false
-- for the captured AircraftSettings widget, even while the selection is shown.
local function widget_visible(widget)
    local current, seen = widget, {}
    for _ = 1, 32 do
        if not valid(current) or seen[name(current)] then return false end
        seen[name(current)] = true
        local ok, visible = pcall(function() return current:IsVisible() end)
        if not ok or not visible then return false end
        local parent_ok, parent = pcall(function() return current:GetParent() end)
        if parent_ok and valid(parent) then current = parent
        else
            local outer_ok, outer = pcall(function() return current:GetOuter() end)
            if outer_ok and valid(outer) and name(outer):match("^WidgetTree ") then
                local owner_ok, owner = pcall(function() return outer:GetOuter() end)
                if not owner_ok or not valid(owner) then return false end
                current = owner
            else return true end
        end
    end
    return false
end

local function display_body_state(component)
    local path = name(component)
    if not path:find("/Game/Maps/Hangar/", 1, true)
        or not path:find("BP_DisplayPlane_", 1, true)
        or not path:match("%.PlaneBodyMesh$") then return false, "not-hangar-display" end
    local ok, shown = pcall(function() return component:IsVisible() end)
    if not ok or not shown then return false, "component-not-visible" end
    local hidden_ok, hidden = pcall(function() return component.bHiddenInGame end)
    if hidden_ok and hidden == true then return false, "component-hidden-in-game" end
    local owner_ok, owner = pcall(function() return component:GetOwner() end)
    if not owner_ok or not valid(owner) then return false, "owner-unavailable" end
    local actor_ok, actor_hidden = pcall(function() return owner:IsHidden() end)
    if not actor_ok then actor_ok, actor_hidden = pcall(function() return owner.bHidden end) end
    if not actor_ok or type(actor_hidden) ~= "boolean" then return false, "owner-hidden-state-unavailable" end
    if actor_hidden then return false, "owner-hidden" end
    return true, "visible"
end

function Adapter.new(config, aircraft, root)
    return setmetatable({config = config, aircraft = aircraft or {}, root = root, originals = {}, textures = {},
        applied = {}, native_parameters = {}, components = {}, snapshots = {}, object_cache = {}, failed_textures = {}}, Adapter)
end

-- Reuse discovery lists, but read live visibility/text/mesh on each reconciliation.
-- Invalid objects are filtered before calling reflected methods.
function Adapter:objects(class)
    if self.discovery_dirty then self.object_cache = {}; self.discovery_dirty = false end
    local now, cached = os.time(), self.object_cache[class]
    if not cached or now - cached.time >= 2 then
        cached = {time = now, objects = all(class)}; self.object_cache[class] = cached
    end
    local result = {}
    for _, object in ipairs(cached.objects) do if valid(object) then result[#result + 1] = object end end
    return result
end

function Adapter:has_applied(aircraft, id)
    for key, state in pairs(self.applied) do
        if state.aircraft_id == aircraft and state.id == id and valid(self.components[key]) then
            if self:is_applied({component = self.components[key], fingerprint = key}, {id = id}) then return true end
        end
    end
    return false
end

-- Ownership survives a native material refresh until STD restores/releases it.
-- Exact readback is for retry/highlight, not permission to enable a second writer.
function Adapter:owns_overrides(aircraft, id)
    for key, state in pairs(self.applied) do
        if state.aircraft_id == aircraft and state.id == id and valid(self.components[key]) then return true end
    end
    return false
end

function Adapter:prune()
    for key, component in pairs(self.components) do
        local release = not valid(component)
        if not release and name(component):find("BP_DisplayPlane_", 1, true) then
            local shown, why = display_body_state(component)
            if not shown and (why == "owner-hidden" or why == "component-not-visible" or why == "component-hidden-in-game") then
                -- Retire a hidden hangar actor without touching the currently selected one.
                release = pcall(function()
                    for index, original in pairs(self.originals[key] or {}) do assert(valid(original), "restore unavailable") end
                    for index, original in pairs(self.originals[key] or {}) do component:SetMaterial(index, original) end
                end)
            end
        end
        if release then
            self.components[key], self.originals[key], self.applied[key], self.native_parameters[key], self.snapshots[key] = nil, nil, nil, nil, nil
        end
    end
    -- Only current applied resources merit a Lua cache. Material parameters own
    -- the engine references; dropping this cache allows old assets to be collected.
    local used = {}
    for _, state in pairs(self.applied) do
        for _, item in ipairs(state.parameters) do
            used[item.texture] = true
            used[item.texture:match("^[^ ]+ (.+)$") or item.texture] = true
        end
    end
    for path, texture in pairs(self.textures) do if not used[path] or not valid(texture) then self.textures[path] = nil end end
end

local selection_classes = {
    WBP_Menu_Hangar_AircraftSettings_000_C = true,
    WBP_Menu_Hangar_AircraftSettings_Select_000_C = true,
}
local excluded_pages = {
    "WBP_Menu_Hangar_WeaponSettings1_000_C", "WBP_Menu_Hangar_Sortie_000_C",
    "WBP_Menu_Hangar_AircraftSettings_001_C", "WBP_Menu_Hangar_AircraftSettings_002_C",
    "WBP_Menu_Hangar_AircraftSettings_003_C", "WBP_Menu_Hangar_AircraftSettings_Select_002_C",
    "WBP_Menu_Hangar_AircraftSettings_Weathering_000_C",
}

function Adapter:native_skin_page()
    for _, widget in ipairs(self:objects("WBP_Menu_Hangar_AircraftSettings_Select_002_C")) do
        if widget_visible(widget) then return widget end
    end
end

function Adapter:selection_page_visible()
    -- Old configs included weapon/sortie pages. Enforce the policy here too,
    -- and reject a visible child page even if its parent remains visible.
    for _, class in ipairs(excluded_pages) do
        for _, widget in ipairs(self:objects(class)) do
            if widget_visible(widget) then return false end
        end
    end
    for class in pairs(selection_classes) do
        for _, widget in ipairs(self:objects(class)) do if widget_visible(widget) then return true end end
    end
    -- Custom candidates are retained for explicit test/adapter fixtures only.
    for _, class in ipairs(self.config.hangar_widget_candidates or {}) do
        if not class:match("^WBP_Menu_Hangar_") then
            for _, widget in ipairs(self:objects(class)) do if widget_visible(widget) then return true end end
        end
    end
    return false
end

function Adapter:clone_material(component, source)
    local library = StaticFindObject("/Script/Engine.Default__KismetMaterialLibrary")
    assert(valid(library), "独立材质工厂不可用")
    local dynamic = StaticFindObject("/Script/Engine.MaterialInstanceDynamic")
    local parent = source
    for _ = 1, 16 do
        if not parent:IsA(dynamic) then break end
        parent = parent.Parent
        assert(valid(parent), "原生材质父级不可用")
    end
    assert(not parent:IsA(dynamic), "原生材质父级循环")
    local mid = library:CreateDynamicMaterialInstance(component, parent, FName("None"), 0)
    assert(valid(mid) and name(mid) ~= name(source), "材质工厂复用了原生实例")
    mid:K2_CopyMaterialInstanceParameters(source, false)
    return mid
end

function Adapter:register_independent_packages()
    if not self.config.package_registration_enabled then return true end
    if self.native_registry and self.native_registry.ready then return true end
    if self.native_registry and (self.native_registry.state == "blocked" or self.native_registry.state == "partial") then
        return false, "资源登记已停止：" .. tostring(self.native_registry.detail)
    end
    if not self.root then return false, "缺少资源注册组件目录" end
    if os.getenv("EOS_USE_ANTICHEATCLIENTNULL") ~= "1" then return false, "资源注册需要离线启动" end
    if not self.native_register then
        local entry, err = package.loadlib(self.root .. "Native/registrar.dll", "register_packages")
        if not entry then return false, "资源注册组件无法加载：" .. tostring(err) end
        self.native_register = entry
    end
    local removed, remove_error = os.remove(self.root .. "Native/registrar-status.json")
    if not removed then
        local stale = io.open(self.root .. "Native/registrar-status.json", "rb")
        if stale then stale:close(); return false, "无法清除旧的资源状态：" .. tostring(remove_error) end
    end
    local ok, err = pcall(self.native_register)
    if not ok then return false, "资源注册调用失败：" .. tostring(err) end
    -- A failed status write must not make a previous session look successful.
    local file = io.open(self.root .. "Native/registrar-status.json", "rb")
    if not file then return false, "资源注册组件没有返回状态" end
    local content = file:read("*a"); file:close()
    local decoded, result = pcall(require("json").decode, content)
    if not decoded or type(result) ~= "table" or result.revision ~= "20261008-cached-store" then
        return false, "资源注册状态无效"
    end
    self.native_registry = result
    result.ready = result.state == "registered" or result.state == "already-registered"
        or (result.state == "partial" and ((tonumber(result.registered) or 0) + (tonumber(result.already) or 0)) > 0)
    if not result.ready then return false, "独立资源未注册：" .. tostring(result.detail or result.state) end
    return true
end

-- LoadAsset searches the registry first. Follow UE4SS's bundled BPModLoader:
-- construct AssetData for the exact package/export and call GetAsset directly.
-- This does not require a registry entry or passing a soft pointer through Lua.
function Adapter:load_texture(path)
    if valid(self.textures[path]) then return self.textures[path] end
    if self.failed_textures[path] then return nil, self.failed_textures[path] end
    local started = os.clock()
    local registered, reason = self:register_independent_packages()
    if not registered then return nil, reason end
    local ok, texture = pcall(StaticFindObject, path)
    if ok and valid(texture) then self.textures[path] = texture; return texture end
    local asset_ok, asset_result = pcall(function()
        local package_path, export = path:match("^(/Game/.+)%.([^./]+)$")
        assert(package_path and export, "Invalid package/export path")
        local helpers = StaticFindObject("/Script/AssetRegistry.Default__AssetRegistryHelpers")
        assert(valid(helpers), "AssetRegistryHelpers unavailable")
        local add = assert(EFindName and EFindName.FNAME_Add, "FNAME_Add unavailable")
        return helpers:GetAsset({PackageName = FName(package_path, add), AssetName = FName(export, add)})
    end)
    if asset_ok and valid(asset_result) then self.textures[path] = asset_result; return asset_result end
    local reference_path = "unavailable"
    local direct_ok, direct_result = pcall(function()
        local library = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
        assert(valid(library), "KismetSystemLibrary unavailable")
        local soft_path = library:MakeSoftObjectPath(path)
        local reference = library:Conv_SoftObjPathToSoftObjRef(soft_path)
        pcall(function() reference_path = library:Conv_SoftObjectReferenceToString(reference):ToString() end)
        return library:LoadAsset_Blocking(reference)
    end)
    if direct_ok and valid(direct_result) then self.textures[path] = direct_result; return direct_result end
    local registry_ok, registry_result = pcall(LoadAsset, path)
    if registry_ok and valid(registry_result) then self.textures[path] = registry_result; return registry_result end
    local failure = "无法加载独立贴图 " .. path .. "；直接资源加载=" .. tostring(asset_ok and "返回空对象" or asset_result)
        .. "；软引用路径=" .. reference_path .. "；软引用加载=" .. tostring(direct_ok and "返回空对象" or direct_result)
        .. "；注册表加载=" .. tostring(registry_ok and "未找到" or registry_result)
    self.failed_textures[path] = failure
    self.last_load = {path = path, seconds = os.clock() - started, success = false}
    return nil, failure
end

function Adapter:preparation(ctx)
    ctx.phase = "preparation"
    ctx.offline_verified = os.getenv("EOS_USE_ANTICHEATCLIENTNULL") == "1"
    return ctx
end

local function normalized(value) return value:upper():gsub("[^A-Z0-9]", "") end
-- Read only the player's detail panel, excluding aircraft-list/wingman text.
function Adapter:selected_aircraft(widget, ids)
    local prefix = name(widget):match("^[^ ]+ (.+)$")
    if not prefix then return end
    local labels = {}
    for id in pairs(ids) do
        local suffix = id:match("_([%w]+)$")
        if suffix and suffix:match("%a") then labels[id] = normalized(suffix) end
    end
    for _, plane in ipairs(self.aircraft) do
        if plane.name and plane.name ~= plane.id then labels[plane.id] = normalized(plane.name) end
    end
    local selected = {}
    for _, block in ipairs(self:objects("TextBlock")) do
        local path = name(block)
        if path:find(prefix .. ".", 1, true) and path:find("WBP_MenuCommon_HangarDetail_000", 1, true)
            and not path:find(".SquadronWidget.", 1, true) and widget_visible(block) then
            pcall(function()
                local raw = block:GetText():ToString():upper():gsub("^[%s|]+", ""):gsub("[%s|]+$", "")
                local value = normalized(raw)
                for id, label in pairs(labels) do
                    if #label >= 3 and (value == label or normalized(raw:match("^(.-)%s") or "") == label) then
                        selected[id] = true
                    end
                end
            end)
        end
    end
    local result
    for id in pairs(selected) do if result then return end; result = id end
    return result
end

function Adapter:context()
    local widgets = {}
    local discovery = {candidate_widgets = 0, visible_widgets = 0, hangar_bodies = 0, visible_bodies = 0}
    self.discovery = discovery
    if not self:selection_page_visible() then
        self.last_context = nil; return nil, "当前不是选择机体页面"
    end
    for _, class in ipairs(self.config.hangar_widget_candidates or {}) do
        for _, widget in ipairs(self:objects(class)) do
            discovery.candidate_widgets = discovery.candidate_widgets + 1
            if (selection_classes[class] or not class:match("^WBP_Menu_Hangar_")) and widget_visible(widget) then widgets[#widgets + 1] = widget end
        end
    end
    discovery.visible_widgets = #widgets
    -- The full settings page owns the right-hand information panel; nested
    -- selection widgets may have a small or clipped local canvas.
    table.sort(widgets, function(a, b)
        local function rank(w)
            return name(w):match("^WBP_Menu_Hangar_AircraftSettings_000_C ") and 1 or 0
        end
        return rank(a) > rank(b)
    end)
    if #widgets == 0 then self.last_context = nil; return nil, "未找到可见的出发准备界面" end
    local found, ids = {}, {}
    for _, component in ipairs(self:objects("SkeletalMeshComponent")) do
        local path = name(component)
        if path:find("/Game/Maps/Hangar/", 1, true) and path:match("%.PlaneBodyMesh$") then
            discovery.hangar_bodies = discovery.hangar_bodies + 1
            pcall(function()
                local id = name(component:GetSkeletalMeshAsset()):match("(PP%d%d%d%d_[%w]+)")
                if id then ids[id] = true end
            end)
        end
        if display_body_state(component) then
                discovery.visible_bodies = discovery.visible_bodies + 1
                local good, mesh = pcall(function() return component:GetSkeletalMeshAsset() end)
                if not good or not valid(mesh) then pcall(function() mesh = component.SkeletalMesh end) end
                local id = name(mesh):match("(PP%d%d%d%d_[%w]+)")
                if id then
                    found[#found + 1] = {aircraft_id = id, component = component,
                        widget = widgets[1], fingerprint = self:fingerprint(component, mesh),
                        ui_fingerprint = name(widgets[1]) .. "|" .. id, model_ready = true, interactive = true}
                end
        end
    end
    local selected_id = self:selected_aircraft(widgets[1], ids)
    if selected_id then
        local matching = {}
        for _, ctx in ipairs(found) do if ctx.aircraft_id == selected_id then matching[#matching + 1] = ctx end end
        found = matching
    end
    -- Several display actors can remain loaded or locally visible. Only accept
    -- a unique recent rendered body when visibility alone remains ambiguous.
    if #found > 1 then
        local rendered = {}
        for _, ctx in ipairs(found) do
            local ok, recent = pcall(function() return ctx.component:WasRecentlyRendered(0.3) end)
            if ok and recent then rendered[#rendered + 1] = ctx end
        end
        if #rendered == 1 then found = rendered end
    end
    if #found == 1 then self.last_context = found[1]; self.last_aircraft_id = found[1].aircraft_id; return self:preparation(found[1]) end
    -- Retain the UI during display-actor swaps; cached identity is display only.
    local previous = self.last_context
    local id = selected_id or (previous and name(previous.widget) == name(widgets[1]) and previous.aircraft_id) or nil
    local ctx = {aircraft_id = id, widget = widgets[1], model_ready = false, interactive = false,
        ui_fingerprint = name(widgets[1]) .. "|" .. (id or "pending")}
    self.last_context = ctx
    return self:preparation(ctx), "当前飞机模型正在更新"
end

function Adapter:fingerprint(component, mesh)
    local address = ""
    pcall(function() address = tostring(component:GetAddress()) end)
    return name(component) .. "|" .. name(mesh) .. "|" .. address
end

-- LivePlayerPlane is the game's player-aircraft class. Do not require APawn
-- methods: custom aircraft actors can be driven without Pawn possession.
-- Explicit non-local/AI flags still veto writes. Without those interfaces only
-- one non-hangar LivePlayerPlane with one owned body is accepted, offline only.
function Adapter:mission_context()
    local discovery = {state = "waiting-player", players = 0, bodies = 0, rejected = 0}
    self.mission_discovery = discovery
    if self.config.mission_switch_enabled == false or os.getenv("EOS_USE_ANTICHEATCLIENTNULL") ~= "1" then
        discovery.state = "disabled"; return nil, discovery.state
    end
    local candidates, seen = {}, {}
    for _, plane in ipairs(self:objects("LivePlayerPlane")) do
        local path = name(plane)
        if not path:find("/Game/Maps/Hangar/", 1, true) and not path:find("Default__", 1, true) then
            local player_ok, player = pcall(function() return plane:IsPlayerControlled() end)
            local local_ok, is_local = pcall(function() return plane:IsLocallyControlled() end)
            if (player_ok and player == false) or (local_ok and is_local == false) then
                discovery.rejected = discovery.rejected + 1
            else
                discovery.players = discovery.players + 1
                local got_body, body = pcall(function() return plane.PlaneBodyMesh end)
                local function inspect(component, explicit_body)
                    if not valid(component) then return end
                    local component_path = name(component)
                    if seen[component_path] or (not explicit_body and not component_path:match("%.PlaneBodyMesh$"))
                        or component_path:find("/Game/Maps/Hangar/", 1, true) then return end
                    local owner_ok, owner = pcall(function() return component:GetOwner() end)
                    if not owner_ok or name(owner) ~= path then return end
                    local mesh_ok, mesh = pcall(function() return component:GetSkeletalMeshAsset() end)
                    if not mesh_ok or not valid(mesh) then pcall(function() mesh = component.SkeletalMesh end) end
                    local id = name(mesh):match("(PP%d%d%d%d_[%w]+)")
                    if not id then return end
                    seen[component_path] = true
                    candidates[#candidates + 1] = {aircraft_id = id, component = component, pawn = plane,
                        fingerprint = self:fingerprint(component, mesh), phase = "mission", offline_verified = true,
                        model_ready = true, interactive = true}
                end
                if got_body and valid(body) then inspect(body, true)
                else
                    local ok, err = pcall(function()
                        local components = plane:GetComponentsByClass(StaticFindObject("/Script/Engine.SkeletalMeshComponent"))
                        if type(components) == "table" then for _, component in ipairs(components) do inspect(component) end
                        elseif components then components:ForEach(function(_, item) inspect(item:get()) end) end
                    end)
                    if not ok then discovery.detail = tostring(err) end
                end
            end
        end
    end
    discovery.bodies = #candidates
    if discovery.players == 1 and #candidates == 1 then
        discovery.state, discovery.aircraft_id = "ready", candidates[1].aircraft_id
        discovery.component = name(candidates[1].component)
        return candidates[1]
    end
    if discovery.players > 1 or #candidates > 1 then discovery.state = "ambiguous-player"
    elseif discovery.players == 1 then discovery.state = "waiting-body" end
    return nil, discovery.state
end

-- Native skin/weathering changes can replace materials on an existing actor.
-- Compare the actual attached materials and texture parameters, not just its name.
function Adapter:is_applied(ctx, skin)
    if not valid(ctx.component) then return false end
    local state = self.applied[ctx.fingerprint]
    if skin.id == "original" then return not state end
    if not state or state.id ~= skin.id then return false end
    local ok, matches = pcall(function()
        for index, material in pairs(state.materials) do
            if not valid(material) or name(ctx.component:GetMaterial(index)) ~= name(material) then return false end
        end
        for _, item in ipairs(state.parameters) do
            local texture = ctx.component:GetMaterial(item.index):K2_GetTextureParameterValue(FName(item.parameter))
            if not valid(texture) or name(texture) ~= item.texture then return false end
        end
        return true
    end)
    return ok and matches == true
end

function Adapter:material_snapshot(ctx, bindings)
    local result, seen = {}, {}
    for _, binding in ipairs(bindings or {}) do
        local key = binding.material_index .. "|" .. binding.parameter
        if not seen[key] then
            seen[key] = true
            local material = ctx.component:GetMaterial(binding.material_index)
            local texture = material:K2_GetTextureParameterValue(FName(binding.parameter))
            local item = {slot = binding.material_index, material = name(material), parameter = binding.parameter, texture = name(texture)}
            pcall(function() item.width = texture:Blueprint_GetSizeX(); item.height = texture:Blueprint_GetSizeY() end)
            result[#result + 1] = item
        end
    end
    return result
end

function Adapter:apply(ctx, skin)
    if ctx.model_ready == false or ctx.interactive == false then return false, "当前飞机模型正在更新" end
    if not self.config.runtime_switch_enabled then
        return false, "菜单接口版：实际贴图切换等待游戏内接入"
    end
    if (ctx.phase ~= "preparation" and ctx.phase ~= "mission") or ctx.offline_verified ~= true then
        return false, "换肤需要离线出发准备界面，请使用原来的离线启动选项"
    end
    if not valid(ctx.component) or skin.aircraft_id ~= ctx.aircraft_id then
        return false, "飞机对象已变化"
    end
    local current, reason
    if ctx.phase == "mission" then current = self:mission_context() else current, reason = self:context() end
    if not current or current.model_ready == false or current.fingerprint ~= ctx.fingerprint then return false, reason or "飞机已变化" end
    local key, component = ctx.fingerprint, ctx.component
    if not self.components[key] then
        self:prune()
        local count = 0; for _ in pairs(self.components) do count = count + 1 end
        if count >= 8 then return false, "机体切换缓存已满，请返回主菜单后重试" end
    end
    self.components[key] = component
    local previous_records, previous_state = self.originals[key], self.applied[key]
    local previous_parameters = self.native_parameters[key]
    local native_parameters = {}
    for index, params in pairs(previous_parameters or {}) do
        native_parameters[index] = {}; for parameter, texture in pairs(params) do native_parameters[index][parameter] = texture end
    end
    local records = {}
    for index, original in pairs(previous_records or {}) do records[index] = original end
    -- If the game replaced a managed slot, that new native material becomes
    -- the restore target; never restore an obsolete native skin/weathering MID.
    if previous_state then
        for index, managed in pairs(previous_state.materials) do
            local material = component:GetMaterial(index)
            if valid(material) and name(material) ~= name(managed) then
                records[index] = material; native_parameters[index] = nil
            end
        end
    end
    -- Native code can update an MID in place instead of replacing its slot.
    -- Preserve those newer parameters when handing authority back to the game.
    -- Never copy the MOD texture itself into the native restore target.
    local native_updates = {}
    if previous_state then
        for _, item in ipairs(previous_state.parameters) do
            local managed = previous_state.materials[item.index]
            local attached = component:GetMaterial(item.index)
            if valid(managed) and name(attached) == name(managed) then
                local got, texture = pcall(function() return attached:K2_GetTextureParameterValue(FName(item.parameter)) end)
                if got and valid(texture) and name(texture) ~= item.texture then
                    native_parameters[item.index] = native_parameters[item.index] or {}
                    native_parameters[item.index][item.parameter] = name(texture)
                    if valid(records[item.index]) then
                        native_updates[item.index] = native_updates[item.index] or {}
                        native_updates[item.index][item.parameter] = texture
                    end
                end
            end
        end
    end
    -- The engine can collect the detached native MID. The attached managed MID
    -- is a copy of all native parameters with only our texture bindings changed.
    -- Reconstruct a native-equivalent MID from it and restore those bindings.
    -- No root flags or raw UObject memory writes are used.
    for index, original in pairs(records) do
        if valid(original) then
            -- The game's own MID may also have changed while detached. Read
            -- its current baseline rather than enforcing an obsolete snapshot.
            for parameter in pairs(native_parameters[index] or {}) do
                local got, texture = pcall(function() return original:K2_GetTextureParameterValue(FName(parameter)) end)
                if not got or not valid(texture) then return false, "原生贴图参数暂不可用" end
                if not (native_updates[index] and native_updates[index][parameter]) then
                    native_parameters[index][parameter] = name(texture)
                end
            end
        end
        if not valid(original) then
            local managed = previous_state and previous_state.materials[index]
            local attached = component:GetMaterial(index)
            if not valid(managed) or name(attached) ~= name(managed) then return false, "原材质不可用，等待游戏重建机体" end
            local recovered, replacement = pcall(function()
                local mid = self:clone_material(component, managed)
                for parameter, texture_name in pairs(native_parameters[index] or {}) do
                    local path = texture_name:match("^[^ ]+ (.+)$") or texture_name
                    local texture = StaticFindObject(path)
                    if not valid(texture) and path:sub(1, 6) == "/Game/" then texture = LoadAsset(path) end
                    assert(valid(texture), "原生贴图不可用：" .. path)
                    mid:SetTextureParameterValue(FName(parameter), texture)
                    assert(name(mid:K2_GetTextureParameterValue(FName(parameter))) == texture_name, "原生贴图重建失败")
                end
                return mid
            end)
            if not recovered then return false, tostring(replacement) end
            records[index] = replacement
        end
    end
    -- Keep the game's original MID identity: its skin controller can retain
    -- that exact object. Changes to its parameters belong to this transaction.
    local native_undo = {}
    local function commit_native_updates()
        for index, params in pairs(native_updates) do
            local original = records[index]
            assert(valid(original), "原生材质已失效")
            native_undo[index] = {}
            for parameter, texture in pairs(params) do
                native_undo[index][parameter] = original:K2_GetTextureParameterValue(FName(parameter))
                assert(valid(native_undo[index][parameter]), "原生参数不可回滚")
                original:SetTextureParameterValue(FName(parameter), texture)
                assert(name(original:K2_GetTextureParameterValue(FName(parameter))) == name(texture), "原生参数未恢复")
            end
        end
    end
    local function undo_native_updates()
        for index, params in pairs(native_undo) do
            local original = records[index]
            assert(valid(original), "原生材质已销毁")
            for parameter, texture in pairs(params) do original:SetTextureParameterValue(FName(parameter), texture) end
        end
    end
    if skin.id == "original" then
        if not next(records) then
            if previous_state then return false, "管理器覆盖缺少恢复记录，等待游戏重建机体" end
            return true, "原版涂装由游戏控制", function() end
        end
        local previous = {}
        local success, err = pcall(function()
            commit_native_updates()
            for index, original in pairs(records) do
                assert(valid(original), "原材质已失效")
                previous[index] = component:GetMaterial(index)
                component:SetMaterial(index, original)
                assert(name(component:GetMaterial(index)) == name(original), "原生材质未恢复")
                for parameter, texture in pairs(native_parameters[index] or {}) do
                    local restored = component:GetMaterial(index):K2_GetTextureParameterValue(FName(parameter))
                    assert(valid(restored) and name(restored) == texture, "原生贴图未恢复")
                end
            end
        end)
        local function undo()
            assert(valid(component), "机体已销毁，不能回滚材质")
            for index, material in pairs(previous) do component:SetMaterial(index, material) end
            undo_native_updates()
            self.originals[key], self.applied[key] = previous_records, previous_state
            self.native_parameters[key] = previous_parameters
        end
        if not success then pcall(undo); return false, tostring(err) end
        self.originals[key], self.applied[key] = nil, nil
        self.native_parameters[key] = nil
        return true, "已交还原版涂装控制（STD）", undo
    end
    if type(skin.bindings) ~= "table" or #skin.bindings == 0 then return false, "皮肤没有材质绑定" end
    local prepared, previous = {}, {}
    -- Resolve every replacement before changing any material.
    for _, binding in ipairs(skin.bindings) do
        if type(binding.material_index) ~= "number" or binding.material_index % 1 ~= 0
            or binding.material_index < 0 or binding.material_index > 127 then return false, "材质槽编号不正确" end
        if type(binding.parameter) ~= "string" or binding.parameter == "" then return false, "缺少贴图参数名" end
        local prefix = skin.resource_root
        if type(prefix) ~= "string" or prefix == "" then return false, "缺少独立资源根路径" end
        if type(binding.texture) ~= "string" or binding.texture:sub(1, #prefix) ~= prefix
            or binding.texture:find("..", 1, true) then return false, "皮肤必须使用独立资源路径" end
        local texture, load_error = self:load_texture(binding.texture)
        if not valid(texture) then return false, load_error end
        local good, is_texture = pcall(function() return texture:IsA(StaticFindObject("/Script/Engine.Texture")) end)
        if not good or not is_texture then return false, "资源不是贴图" end
        if not valid(component) then return false, "贴图加载期间机体已销毁" end
        local material = component:GetMaterial(binding.material_index)
        if not valid(material) then return false, "材质槽不存在" end
        prepared[#prepared + 1] = {binding = binding, texture = texture}
        previous[binding.material_index] = material
    end
    -- A different skin may use different slots. Restore old-only slots as part
    -- of this same transaction instead of leaving fragments of the last skin.
    for index in pairs(records) do previous[index] = previous[index] or component:GetMaterial(index) end
    local function undo()
        assert(valid(component), "机体已销毁，不能回滚材质")
        for index, material in pairs(previous) do component:SetMaterial(index, material) end
        undo_native_updates()
        self.originals[key], self.applied[key] = previous_records, previous_state
        self.native_parameters[key] = previous_parameters
    end
    local mids, parameters = {}, {}
    local ok, err = pcall(function()
        assert(valid(component), "机体已销毁")
        commit_native_updates()
        for index, original in pairs(records) do
            assert(valid(original), "原材质已失效")
            component:SetMaterial(index, original)
        end
        for _, item in ipairs(prepared) do
            local index = item.binding.material_index
            if not mids[index] then
                -- Use a fresh instance so undo never points to a material mutated in place.
                local source = records[index] or previous[index]
                local mid = self:clone_material(component, source)
                assert(valid(mid), "无法创建独立材质实例")
                mids[index] = mid
                component:SetMaterial(index, mid)
                assert(name(component:GetMaterial(index)) == name(mid), "独立材质未附加")
            end
            local parameter = FName(item.binding.parameter)
            local original_texture = mids[index]:K2_GetTextureParameterValue(parameter)
            assert(valid(original_texture), "贴图参数不存在")
            native_parameters[index] = native_parameters[index] or {}
            native_parameters[index][item.binding.parameter] = native_parameters[index][item.binding.parameter] or name(original_texture)
            mids[index]:SetTextureParameterValue(parameter, item.texture)
            local written = mids[index]:K2_GetTextureParameterValue(parameter)
            assert(valid(written) and name(written) == name(item.texture), "贴图参数未更新")
            parameters[#parameters + 1] = {index = index, parameter = item.binding.parameter, texture = name(item.texture)}
        end
    end)
    if not ok then pcall(undo); return false, "切换已撤销：" .. tostring(err) end
    for index, material in pairs(previous) do records[index] = records[index] or material end
    self.originals[key] = records
    self.applied[key] = {id = skin.id, aircraft_id = ctx.aircraft_id, materials = mids, parameters = parameters}
    self.native_parameters[key] = native_parameters
    return true, "已应用：" .. skin.name, undo
end

function Adapter:probe()
    local lines = {"AC8SkinManager probe v0.1"}
    for _, block in ipairs(all("TextBlock")) do
        if name(block):find("WBP_MenuCommon_HangarDetail_000", 1, true) and widget_visible(block) then
            pcall(function()
                lines[#lines + 1] = "DetailText=" .. block:GetText():ToString() .. " " .. name(block)
            end)
        end
    end
    -- Include visible widget names even when the known candidates do not match.
    local count = 0
    for _, widget in ipairs(all("UserWidget")) do
        local ok, shown = pcall(function() return widget:IsVisible() end)
        if ok and shown and count < 100 then
            count = count + 1
            local viewport = false
            pcall(function() viewport = widget:IsInViewport() end)
            lines[#lines + 1] = "VisibleWidget viewport=" .. tostring(viewport) .. " " .. name(widget)
            pcall(function() lines[#lines + 1] = "VisibleRoot=" .. name(widget.WidgetTree.RootWidget) end)
        end
    end
    for _, class in ipairs(self.config.hangar_widget_candidates or {}) do
        for _, widget in ipairs(all(class)) do
            local visible, viewport = false, false
            pcall(function() visible = widget:IsVisible() end)
            pcall(function() viewport = widget:IsInViewport() end)
            lines[#lines + 1] = "Widget visible=" .. tostring(visible) .. " viewport=" .. tostring(viewport)
                .. " chain_visible=" .. tostring(widget_visible(widget)) .. " " .. name(widget)
            pcall(function() lines[#lines + 1] = "Root=" .. name(widget.WidgetTree.RootWidget) end)
            pcall(function() lines[#lines + 1] = "Parent=" .. name(widget:GetParent()) end)
        end
    end
    for _, component in ipairs(all("SkeletalMeshComponent")) do
        if name(component):match("%.PlaneBodyMesh$") then
            lines[#lines + 1] = "Body=" .. name(component)
            local shown, why = display_body_state(component)
            lines[#lines + 1] = "DisplayVisible=" .. tostring(shown) .. " reason=" .. why
            pcall(function() lines[#lines + 1] = "RecentlyRendered=" .. tostring(component:WasRecentlyRendered(0.3)) end)
            pcall(function() lines[#lines + 1] = "Mesh=" .. name(component:GetSkeletalMeshAsset()) end)
            pcall(function()
                for index = 0, math.min(component:GetNumMaterials() - 1, 63) do
                    local material = component:GetMaterial(index)
                    lines[#lines + 1] = "Material[" .. index .. "]=" .. name(material)
                    for _ = 1, 5 do
                        if not valid(material) then break end
                        pcall(function()
                            material.TextureParameterValues:ForEach(function(_, item)
                                local value = item:get()
                                lines[#lines + 1] = "Parameter=" .. value.ParameterInfo.Name:ToString()
                                    .. " Texture=" .. name(value.ParameterValue)
                            end)
                        end)
                        local ok, parent = pcall(function() return material.Parent end)
                        if not ok then break end
                        material = parent
                    end
                end
            end)
        end
    end
    return table.concat(lines, "\n")
end

Adapter.valid = valid
return Adapter
