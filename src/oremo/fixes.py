"""Registry of behaviour changing bug fixes.

Every fix that changes how the original OREMO 3.0-b190106 behaved is
switchable.  A fix is active when ``fix.<ID>=1`` is written in
oremo-setting.ini, otherwise the original behaviour is reproduced.
DEFAULTS holds the value used when the ini file has no entry.
"""

FIXES = [
    ("F01", "crash_guards"),
    ("F02", "estimate_keeps_current_wave"),
    ("F03", "bind_autorecstop"),
    ("F04", "bind_replace_old"),
    ("F05", "settings_cancel_only_settings"),
    ("F06", "use_actual_sample_rate"),
    ("F07", "bgm_unit_sample"),
    ("F08", "init_file_roundtrip"),
    ("F09", "persist_audio_settings"),
    ("F10", "ust_skip_rest"),
    ("F11", "onsa_while_playing"),
    ("F12", "record_key_release_modifier"),
    ("F13", "samplerate_change_keeps_current"),
    ("F14", "comment_dialog_cancel_keeps"),
    ("F15", "otoini_check_cancel"),
    ("F16", "mfcc_range_same_wav_only"),
]

IDS = [f[0] for f in FIXES]

# Approved by the user: all fixes on except F06 (keeps the original's
# sample-rate handling in analysis).
DEFAULTS = {fid: fid != "F06" for fid in IDS}
