namespace RiftBoundTracker.App.Data;

// Singleton row (Id is always 1). Access is earned by typing the current day's RiftCode once (see
// RuneDailyPasscode) and only holds for the day it was granted - GrantedOn is compared against
// today's date on every read, so this resets itself at midnight with no cleanup job needed.
public class EmulatorAccessEntity
{
    public int Id { get; set; } = 1;
    public bool HasAccess { get; set; }
    public DateOnly? GrantedOn { get; set; }
}
