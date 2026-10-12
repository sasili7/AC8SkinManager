-- Restore the saved choice to each new aircraft instance. Menu visibility is
-- independent of mission restoration; failures during streaming use backoff.
local Reconcile = {}
Reconcile.__index = Reconcile
function Reconcile.new() return setmetatable({}, Reconcile) end
function Reconcile:reset() self.token, self.failures, self.next_attempt = nil, 0, 0 end
function Reconcile:update(adapter, core, config, ctx, log, now)
    if not config.runtime_switch_enabled or not ctx or ctx.model_ready == false or not ctx.aircraft_id then return end
    local selected = core.saved.selections[ctx.aircraft_id]
    if not selected then return end
    local row
    if selected == "original" then row = {id = "original", aircraft_id = ctx.aircraft_id}
    else
        for _, skin in ipairs(core.catalog.skins) do
            if skin.id == selected and skin.aircraft_id == ctx.aircraft_id and skin.status == "ready" then row = skin; break end
        end
    end
    if not row then return end
    local token = (ctx.phase or "preparation") .. "|" .. ctx.fingerprint .. "|" .. selected
    if token ~= self.token then self:reset(); self.token = token end
    if adapter:is_applied(ctx, row) then
        core.applied_skin = selected; self.failures, self.next_attempt = 0, 0
        self.status = {state = "applied", phase = ctx.phase, aircraft_id = ctx.aircraft_id, skin = selected}
        return true
    end
    core.applied_skin = ""
    now = now or os.time()
    if now < self.next_attempt then return end
    local success, message = adapter:apply(ctx, row)
    if success then
        core.applied_skin = selected; self.failures, self.next_attempt = 0, 0
    else
        self.failures = self.failures + 1
        self.next_attempt = now + math.min(15, 3 * 2 ^ math.min(self.failures - 1, 3))
    end
    if message then core.status = message end
    self.status = {state = success and "applied" or "retry", phase = ctx.phase, aircraft_id = ctx.aircraft_id,
        skin = selected, attempts = self.failures, next_attempt = self.next_attempt, message = message}
    if log and (not success or ctx.phase == "mission") then
        local identity = token .. "|" .. tostring(success) .. "|" .. tostring(message)
        if self.last_log ~= identity then
            self.last_log = identity; log((ctx.phase == "mission" and "任务涂装：" or "涂装恢复：") .. tostring(message))
        end
    end
    return success
end
return Reconcile
