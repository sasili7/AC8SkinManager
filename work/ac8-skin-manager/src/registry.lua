-- Public extension API v1: independent JSON manifests, not shared config edits.
local Registry = {}
local Presentation = require("presentation")
local function identifier(value)
    return type(value) == "string" and #value > 0 and #value <= 64
        and value:match("^[a-z0-9][a-z0-9_%-]*$") ~= nil
end
function Registry.normalize(manifest)
    assert(type(manifest) == "table" and manifest.schema_version == 1, "不支持的 skin.json 版本")
    assert(identifier(manifest.provider_id) and identifier(manifest.id), "provider_id/id 格式不正确")
    assert(type(manifest.aircraft_id) == "string" and manifest.aircraft_id:match("^PP%d%d%d%d_[a-z0-9]+$"), "机型编号不正确")
    assert(type(manifest.name) == "string" and #manifest.name > 0 and #manifest.name <= 239, "皮肤名称不正确")
    assert(type(manifest.author) == "string", "缺少作者")
    assert(manifest.status == "ready" or manifest.status == "draft", "status 必须为 ready 或 draft")
    local prefix = "/Game/AC8SkinManager/Skins/" .. manifest.provider_id .. "/"
        .. manifest.aircraft_id .. "/" .. manifest.id .. "/"
    local bindings, seen = {}, {}
    for _, binding in ipairs(manifest.bindings or {}) do
        assert(binding.target == "body", "v1 仅支持 body 材质目标")
        assert(type(binding.material_index) == "number" and binding.material_index % 1 == 0
            and binding.material_index >= 0 and binding.material_index <= 127, "材质槽不正确")
        assert(type(binding.parameter) == "string" and #binding.parameter > 0 and #binding.parameter <= 120, "贴图参数名不正确")
        assert(type(binding.texture) == "string" and #binding.texture > #prefix
            and binding.texture:sub(1, #prefix) == prefix and not binding.texture:find("..", 1, true)
            and not binding.texture:find("\\", 1, true), "资源必须位于本作者/本机型/本皮肤的独立路径")
        local key = binding.material_index .. ":" .. binding.parameter
        assert(not seen[key], "重复的材质参数绑定")
        seen[key] = true
        bindings[#bindings + 1] = binding
    end
    assert(manifest.status ~= "ready" or #bindings > 0, "ready 皮肤必须包含实际贴图绑定")
    return {
        id = manifest.provider_id .. "__" .. manifest.aircraft_id .. "__" .. manifest.id,
        local_id = manifest.id, provider_id = manifest.provider_id, aircraft_id = manifest.aircraft_id,
        name = manifest.name, author = manifest.author, description = manifest.description or "",
        status = manifest.status == "ready" and "ready" or "requires_conversion",
        resource_root = prefix, bindings = bindings,
        button = Presentation.normalize(manifest.button, manifest.name),
    }
end
function Registry.collect(documents, log)
    local skins, ids, textures = {}, {}, {}
    for _, document in ipairs(documents) do
        local ok, result = pcall(Registry.normalize, document.data)
        if ok and ids[result.id] then ok, result = false, "重复皮肤编号，保留先注册的皮肤" end
        if ok then
            for _, binding in ipairs(result.bindings) do
                if textures[binding.texture] then ok, result = false, "贴图资源路径与已注册皮肤冲突"; break end
            end
        end
        if ok then
            ids[result.id] = true
            for _, binding in ipairs(result.bindings) do textures[binding.texture] = true end
            skins[#skins + 1] = result
        elseif log then log((document.path or "skin.json") .. ": " .. tostring(result)) end
    end
    table.sort(skins, function(a, b) return a.id < b.id end)
    return skins
end
function Registry.discover(root, json, log)
    local documents, visited = {}, 0
    local function walk(directory, depth)
        if type(directory) ~= "table" or depth > 4 then return end
        visited = visited + 1
        if visited > 2048 then return end
        for _, file in pairs(directory.__files or {}) do
            if file.__name and file.__name:lower() == "skin.json" then
                local stream = io.open(file.__absolute_path, "rb")
                if stream then
                    local content = stream:read(262145); stream:close()
                    if content and #content <= 262144 then
                        local ok, data = pcall(json.decode, content:gsub("^\239\187\191", ""))
                        if ok then documents[#documents + 1] = {data = data, path = file.__absolute_path}
                        elseif log then log("JSON 格式错误：" .. file.__absolute_path) end
                    elseif log then
                        log((content and "skin.json 超过 256KB：" or "skin.json 为空或无法读取：") .. file.__absolute_path)
                    end
                end
            end
        end
        local keys = {}
        for key, value in pairs(directory) do
            if type(key) == "string" and key:sub(1, 2) ~= "__" and type(value) == "table" then keys[#keys + 1] = key end
        end
        table.sort(keys)
        for _, key in ipairs(keys) do walk(directory[key], depth + 1) end
    end
    walk(root, 0)
    table.sort(documents, function(a, b) return a.path:lower() < b.path:lower() end)
    return Registry.collect(documents, log)
end
return Registry
