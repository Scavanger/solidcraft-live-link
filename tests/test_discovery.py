import os
import time

from solidcraft_link import discovery

TOKEN = "ab" * 32


def test_the_newest_discovery_file_names_the_port(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "xdg" / "solidcraft" / "control"
    for d, port in ((old, 27878), (new, 27880)):
        d.mkdir(parents=True)
        (d / "current.port").write_text(f"{port}\n")
        (d / f"{port}.token").write_text(TOKEN + "\n")
    past = time.time() - 100
    os.utime(old / "current.port", (past, past))
    env = {"SOLIDCRAFT_CONTROL_DIR": str(old), "XDG_DATA_HOME": str(tmp_path / "xdg")}
    assert discovery.find(env=env, home=tmp_path, platform="linux") == (27880, TOKEN)


def test_a_given_port_reads_only_its_token(tmp_path):
    (tmp_path / "27890.token").write_text(TOKEN)
    env = {"SOLIDCRAFT_CONTROL_DIR": str(tmp_path)}
    assert discovery.find(27890, env=env, home=tmp_path, platform="linux") == (27890, TOKEN)
    assert discovery.find(27891, env=env, home=tmp_path, platform="linux") == (27891, None)


def test_nothing_running_gives_the_default_port(tmp_path):
    assert discovery.find(env={}, home=tmp_path, platform="linux") == (discovery.DEFAULT_PORT, None)


def test_bad_files_are_ignored(tmp_path):
    (tmp_path / "current.port").write_text("not a port")
    (tmp_path / "27878.token").write_text("short")
    env = {"SOLIDCRAFT_CONTROL_DIR": str(tmp_path)}
    assert discovery.find(env=env, home=tmp_path, platform="linux") == (27878, None)


def test_folders_per_system(tmp_path):
    win = discovery.control_dirs(env={"LOCALAPPDATA": str(tmp_path)}, home=tmp_path, platform="win32")
    assert win[0] == tmp_path / "SolidCraft" / "control"
    mac = discovery.control_dirs(env={}, home=tmp_path, platform="darwin")
    assert mac == [tmp_path / "Library" / "Application Support" / "SolidCraft" / "control"]
    linux = discovery.control_dirs(env={}, home=tmp_path, platform="linux")
    assert linux == [tmp_path / ".local" / "share" / "solidcraft" / "control"]
    packaged = tmp_path / "Packages" / "SolidCraft_x" / "LocalCache" / "Local" / "SolidCraft" / "control"
    packaged.mkdir(parents=True)
    assert packaged in discovery.control_dirs(env={"LOCALAPPDATA": str(tmp_path)}, home=tmp_path, platform="win32")
