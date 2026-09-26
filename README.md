[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/callerpj/Flagdage_DK)
![GitHub all releases](https://img.shields.io/github/downloads/callerpj/Flagdage_DK/total)
![GitHub last commit](https://img.shields.io/github/last-commit/callerpj/Flagdage_DK)
![GitHub code size in bytes](https://img.shields.io/github/languages/code-size/callerpj/Flagdage_DK)
[![Buy me a coffee](https://img.shields.io/static/v1.svg?label=Buy%20me%20a%20coffee&message=🥨&color=black&logo=buy%20me%20a%20coffee&logoColor=white&labelColor=6f4e37)](https://www.buymeacoffee.com/callerpj)


# Flagdage_DK

Sensor with official flagdays in Denmark, with an option to add your own (birthdays etc.)

## BREAKING CHANGES
The integration has been rewritten and received some TLC and improvements.
+ fork of [![J-Lindvig](https://github.com)](https://github.com)'s FlagDays_DK and renamed to **flagdage_dk**. See [Migrate from flagdays_dk](#migrate-from-flagdays_dk) below if you're upgrading.
+ Configuration no longer lives in `configuration.yaml`. Everything is now set up and changed through Home Assistant's UI (a **config flow**). See [Setup](#setup) and [Changing settings later](#changing-settings-later) below.
+ The integration now survives New Year's Eve on its own: once the year changes, it automatically reloads itself and rebuilds the full list of flagdays (default, Easter-based, your own, and sensor-sourced) for the new year — no restart needed.

For installation instructions [see this guide](https://hacs.xyz/docs/faq/custom_repositories).

!OBS if you are migrating from Flagdays_DK read [Migrate from flagdays_dk](#migrate-from-flagdays_dk) below first and then restart Homeassistant

## Setup
1. In Home Assistant, go to **Settings → Devices & services → Add integration** and search for **Flagdage DK**.
2. Fill in the basic settings:

   | Field | Description |
   |---|---|
   | **Offset** | Minutes before flag up/down time, used e.g. for automation triggers. Default: 10 |
   | **Include** | Name of a special (commonwealth) flag (e.g. `Erfalasorput`, `Merkið`) or a string that's part of a flagday's name, so it's kept even though its flag isn't the Dannebrog. You can pick a suggestion or type your own. |
   | **Exclude – defaults** | Tick any of the built-in options to hide those flagdays: **Kongelige** (royal birthdays), **Udsendte** (Denmark's deployed), **Religiøs** (religious flagdays), or **all** (hide every default flagday, keep only your own/sensor-based ones). |
   | **Exclude – custom** | Any further text that should be excluded if it's part of a flagday's name. Add or remove entries freely. |

3. Confirm — the integration is created, without any custom flagdays yet. Everything else (adding your own flagdays, using sensors as a source) is done afterwards via **Configure**, described below.

## Changing settings later
Open the integration's entry and click **Configure**. You get a menu with four options:

### Settings
Change offset, include and exclude at any time, same fields as during setup.

### Add custom flagday
Add one flagday at a time:

| Field | Required | Description |
|---|---|---|
| **Name** | yes | The flagday's name. Must be unique among your custom flagdays. |
| **Date** | yes | `day-month-year` (e.g. `10-6-1975`) if you want the age calculated, or `day-month` (e.g. `1-8`) for a yearly recurring date without an age. |
| **Date end** | no | For a prolonged event spanning several days (e.g. a whole month), the last day as `day-month` (e.g. `31-8`). Must be in the same year and not before the start date. |
| **Flag** | no | Name of a special flag to use for this flagday (e.g. `Pride`, `Jolly Roger`). Leave empty for the regular Dannebrog. |
| **Add another** | — | Tick this to keep the form open and add several flagdays in a row. |

The date is validated as you go — an invalid date or a name you already used shows an error right on the form instead of silently failing.

### Remove custom flagdays
Pick one or more of your existing custom flagdays from a list (showing name, date, and flag) and remove them.

### Sensors as source
Use existing Home Assistant sensors (or groups of sensors) as flagdays — handy for e.g. birthday sensors from the *Anniversaries* integration:

| Field | Description |
|---|---|
| **Sensors / groups** | Pick one or more `sensor.*` or `group.*` entities. A group's member sensors are used individually; the sensor's friendly name becomes the flagday's name. |
| **Attribute names holding the date** | Which attribute(s) to look for a date in, e.g. `date` or `anniversary_date`. The first attribute found (in this order) that holds a date is used. Default: `date` |

Changes picked up from a sensor's attributes (e.g. a birth year edited afterwards) only take effect after the integration reloads — either automatically (at the New Year, see above) or via **Configure → Settings → Submit**, which also reloads it.

## Migrate from flagdays_dk
The original integration used to be called `flagdays_dk`. If you're migrating from that version:

1. Home Assistant only recognizes an integration for a key that matches an installed component's domain. If you still have a `flagdays_dk:` block in your `configuration.yaml` from before the config-flow rewrite, rename it to `flagdage_dk:` (the rest of the block stays the same), then restart Home Assistant. Your settings will be imported once, automatically, as a config entry named "Flagdage DK". Afterwards you can delete the YAML block entirely.
2. Any old config entry still named "FlagDays DK" (from a previous UI-based setup under the old domain) should be removed manually afterwards, since it's no longer used.

## State and attributes
State is the next flag ction date and time

flagday_name is the name of the next flagday.

<img width="637" height="567" alt="^flagdage_dk_values" src="https://github.com/user-attachments/assets/1b14d334-a217-4a74-888d-c909df9c5555" />


### Attributes

| Attribute name             | Description                        |
|----------------------------|------------------------------------|
| flagday_name                | Name of the flagday                |
| days                       | Number of days to the flagday      |
| flag                       | Name of flag to use                |
| years                      | Age to come, if calculated         |
| flag_up_time               | Time to hoist the flag             |
| flag_down_time             | Time to pull the flag              |
| half_mast                  | True/False/Time for full mast      |
| concurrent_flagdays        | Other flagdays on the same date    |
| future_flagdays            | List of flagdays in the future     |
| attribution                | Name of the creator                |
