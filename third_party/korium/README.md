# Korium Komblete built-in theme

Graphics by **Berion**, original theme script by **KrahJohlito and Ripto**.
The built-in port is preserved from NathanNeurotic/Open-PS2-Loader's Korium
branch at the exact revision in `UPSTREAM.json`. Original config comments and
credits are retained in `assets.zip`; each file and the archive have SHA-256
digests. The repository's AFL-3.0 license applies to this downstream port.

`tools/assets.py` reads this archive for Korium and RetroAchievements builds.
It does not overwrite the IncebtIon source graphics or configs. Backgrounds
keep their existing enum positions; additional PS1 and players textures are
appended before the guarded RA mark. Update the archive and manifest together
when deliberately importing another tested upstream theme revision.
