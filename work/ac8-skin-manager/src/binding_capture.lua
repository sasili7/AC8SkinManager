-- Explicit read-only capture; no scans unless an author requests them.
local Capture = {}
Capture.__index = Capture
local function valid(o)
    local ok, value = pcall(function() return o and o:IsValid() end)
    return ok and value == true
end
local function name(o)
    local ok, value = pcall(function() return valid(o) and o:GetFullName() or "" end)
    return ok and value or ""
end
local function write(path, value, json)
    local raw = json.encode(value)
    assert(#raw <= 262144, "Binding record too large / 材质记录过大")
    local file = assert(io.open(path, "wb"))
    local ok, err = file:write(raw); local closed, close_err = file:close()
    assert(ok and closed, err or close_err)
end
function Capture.new(root, adapter, json)
    return setmetatable({root = root, adapter = adapter, json = json}, Capture)
end
function Capture:profile(expected)
    local ctx, why = self.adapter:context()
    assert(ctx and ctx.phase == "preparation" and ctx.offline_verified == true and ctx.model_ready ~= false
        and valid(ctx.component), "Select the aircraft offline / 请离线进入选机页：" .. tostring(why or ""))
    assert(not expected or expected == ctx.aircraft_id, "Aircraft mismatch / 游戏选中机型与导入包不一致")
    assert(ctx.aircraft_id:match("^PP%d%d%d%d_[a-z0-9]+$"), "Invalid aircraft")
    assert(not self.adapter.applied[ctx.fingerprint], "Select STD before capture / 请先选择 STD 原生材质再读取")
    local count = ctx.component:GetNumMaterials()
    assert(type(count) == "number" and count > 0 and count <= 128, "Invalid material count")
    local materials, total = {}, 0
    for slot = 0, count - 1 do
        local material = ctx.component:GetMaterial(slot)
        local row = {slot = slot, material = name(material), parameters = {}}
        local current, seen, names = material, {}, {}
        for _ = 1, 8 do
            if not valid(current) or seen[name(current)] then break end
            seen[name(current)] = true
            pcall(function()
                current.TextureParameterValues:ForEach(function(_, item)
                    if #row.parameters >= 64 or total >= 2048 then return end
                    local value = item:get()
                    local parameter = value.ParameterInfo.Name:ToString()
                    if type(parameter) ~= "string" or parameter == "" or #parameter > 120 or names[parameter] then return end
                    local ok, texture = pcall(function() return material:K2_GetTextureParameterValue(FName(parameter)) end)
                    if not ok or not valid(texture) then texture = value.ParameterValue end
                    local path = name(texture):match("^[^ ]+ (.+)$") or name(texture)
                    if path:sub(1,6) ~= "/Game/" or path:find("/AC8SkinManager/",1,true) then return end
                    names[parameter] = true
                    row.parameters[#row.parameters + 1] = {parameter = parameter, texture = path}
                    total = total + 1
                end)
            end)
            local ok, parent = pcall(function() return current.Parent end)
            if not ok then break end
            current = parent
        end
        materials[#materials + 1] = row
    end
    assert(total > 0, "No texture parameters captured / 未读取到贴图参数")
    local now = self.adapter:context()
    assert(now and now.fingerprint == ctx.fingerprint and now.aircraft_id == ctx.aircraft_id, "Aircraft changed / 读取时飞机已切换")
    return {schema_version = 1, kind = "ac8-material-bindings", aircraft_id = ctx.aircraft_id,
        game_sha256 = "51510e2a520565dbe81fb0d569e95cd4393077acaaa859371489b80b8128829f",
        native = true, captured_at = os.time(), mesh = name(ctx.component:GetSkeletalMeshAsset()), materials = materials}
end
function Capture:save(expected)
    local profile = self:profile(expected)
    write(self.root .. "BindingProfiles/" .. profile.aircraft_id .. ".json", profile, self.json)
    return profile
end
function Capture:poll()
    local request_path = self.root .. "binding-request.json"
    local file = io.open(request_path, "rb")
    if not file then return false end
    local raw = file:read(4097); file:close()
    local ok, request = pcall(self.json.decode, raw or "")
    if not ok or #raw > 4096 or type(request) ~= "table" or request.schema_version ~= 1
        or type(request.token) ~= "string" or not request.token:match("^[a-f0-9]+$") or #request.token ~= 32
        or type(request.aircraft_id) ~= "string" or not request.aircraft_id:match("^PP%d%d%d%d_[a-z0-9]+$") then return false end
    if self.last_token == request.token then return false end
    self.last_token = request.token
    local good, result = pcall(function() return self:save(request.aircraft_id) end)
    local err = not good and tostring(result) or nil
    if err then err = err:match(":%d+: (.+)$") or err end
    pcall(write, self.root .. "binding-response.json", {token = request.token, ok = good,
        profile = good and result or nil, error = err}, self.json)
    os.remove(request_path)
    return true
end
return Capture
