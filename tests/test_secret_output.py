"""`get` is used inside $(...) by the shell scripts; it must not leak the key."""
import cpd_config as C


def test_get_api_key_is_withheld_by_default(config_file, capsys):
    config_file(url="https://x", api_key="SUPER-SECRET-KEY")
    rc = C.main(["get", "api_key"])
    out = capsys.readouterr()
    assert "SUPER-SECRET-KEY" not in out.out
    assert rc != 0 or "reveal" in (out.out + out.err).lower()


def test_get_api_key_with_reveal_prints_it(config_file, capsys):
    config_file(url="https://x", api_key="SUPER-SECRET-KEY")
    C.main(["get", "api_key", "--reveal"])
    assert "SUPER-SECRET-KEY" in capsys.readouterr().out


def test_show_always_masks_the_key(config_file, capsys):
    config_file(url="https://x", api_key="SUPER-SECRET-KEY")
    C.main(["show"])
    assert "SUPER-SECRET-KEY" not in capsys.readouterr().out


def test_other_keys_are_unaffected(config_file, capsys):
    config_file(url="https://x", space_id="space-123")
    C.main(["get", "space_id"])
    assert "space-123" in capsys.readouterr().out
