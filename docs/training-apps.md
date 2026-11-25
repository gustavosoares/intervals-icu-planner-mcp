# Training apps and activities

[← Back to README](../README.md)

## Syncing to your training apps

intervals.icu sends planned workouts to the apps you connect under
**Settings → Connections**:

- **Zwift** and **MyWhoosh**: the day's planned workouts show up in the app's
  workout list, ready to ride.
- **Garmin Connect**: workouts land on the Garmin Connect calendar and reach
  your device on its next sync.

Only the **next 7 days** are synced, not the whole plan. If you push 12 weeks,
the apps show this week's sessions, and later weeks appear as the window moves
forward. If a workout is missing in the app, check that it falls within the
next 7 days, then re-sync or reopen the app. Changes you push again are picked
up the same way.

### Turn ERG mode off for sprints

Ride sprint intervals in resistance or slope mode instead. In ERG the trainer
holds the target wattage, so you can't sprint above it. Short all-out efforts
like the 10-second sprints in `W04_Z2_60_Neuromuscular_Sprints.zwo` only work
when you control the power. The target in the file is a placeholder.

## Reading your activities

`get_activities` lists completed rides with intervals.icu's numbers: moving
time, distance, training load, average and normalized power, intensity factor
and average heart rate. Combined with `get_fitness` (CTL, ATL and Form) and
`get_planned`, Claude can compare what was planned with what was ridden.

One limitation: **activities that reached intervals.icu through Strava can't
be read via the API** (Strava's terms forbid it). They're listed as
"Strava import: details not available via API". Connect Garmin, Zwift,
MyWhoosh etc. to intervals.icu directly to see them.
