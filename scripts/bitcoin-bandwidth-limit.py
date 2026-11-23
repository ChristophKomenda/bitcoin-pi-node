#!/usr/bin/env python3
"""Limit a single Docker Bitcoin Core container via Linux tc and IFB.

Run on the Raspberry Pi host as root:
    sudo python3 bitcoin_bandwidth_limit.py apply --mbit 5
    sudo python3 bitcoin_bandwidth_limit.py status
    sudo python3 bitcoin_bandwidth_limit.py remove

Requires docker, iproute2 (tc/ip), nsenter, and kernel IFB support.
Limits are per direction, not a combined total. Container recreation loses
the rules; run apply again after Docker Compose recreates the container.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

IFB = "ifbbtc0"
ETH = "eth0"


def cmd(*argv, check=True):
    proc = subprocess.run(argv, text=True, capture_output=True)
    if check and proc.returncode:
        raise RuntimeError(
            f"Command failed: {' '.join(argv)}\n"
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout.strip()


def namespace(pid, *argv, check=True):
    return cmd("nsenter", "-t", str(pid), "-n", *argv, check=check)


def info(container):
    raw = cmd("docker", "inspect", "--format",
              "{{json .State}}|{{.HostConfig.NetworkMode}}", container)
    state, netmode = raw.split("|", 1)
    data = json.loads(state)
    pid = int(data.get("Pid") or 0)
    if not data.get("Running") or pid <= 0:
        raise RuntimeError(f"Container '{container}' is not running")
    if netmode == "host":
        raise RuntimeError("Refusing host-network mode: would limit host traffic.")
    namespace(pid, "ip", "link", "show", "dev", ETH)
    return pid


def has_ifb(pid):
    return subprocess.run(
        ["nsenter", "-t", str(pid), "-n", "ip", "link", "show", "dev", IFB],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode == 0


def get_qdiscs(pid):
    return namespace(pid, "tc", "qdisc", "show", "dev", ETH)


def ingress_present(pid):
    return any(
        line.startswith("qdisc ingress ") or line.startswith("qdisc clsact ")
        for line in get_qdiscs(pid).splitlines()
    )


def show(pid):
    print(f"\nContainer network namespace PID: {pid}")
    for dev in (ETH, IFB):
        if dev == IFB and not has_ifb(pid):
            print(f"\n{dev}: not present")
            continue
        print(f"\n{dev} qdiscs:")
        print(namespace(pid, "tc", "-s", "qdisc", "show", "dev", dev) or "(none)")
    if ingress_present(pid):
        print(f"\n{ETH} ingress filters:")
        print(namespace(pid, "tc", "filter", "show", "dev", ETH, "ingress") or "(none)")


def apply(pid, mbps):
    if mbps <= 0 or mbps > 100000:
        raise ValueError("--mbit must be greater than zero")

    # Avoid modifying an existing incoming-traffic policy we did not create.
    if ingress_present(pid) and not has_ifb(pid):
        raise RuntimeError(
            f"{ETH} already has ingress/clsact rules. Refusing to overwrite."
        )

    if not has_ifb(pid):
        if shutil.which("modprobe"):
            cmd("modprobe", "ifb", check=False)
        namespace(pid, "ip", "link", "add", IFB, "type", "ifb")

    namespace(pid, "ip", "link", "set", IFB, "up")

    rate = f"{mbps:g}mbit"
    # Container eth0 egress = upload to peers.
    namespace(pid, "tc", "qdisc", "replace", "dev", ETH,
              "root", "tbf", "rate", rate, "burst", "64kb", "latency", "100ms")

    # Container eth0 ingress = download from peers.
    namespace(pid, "tc", "qdisc", "replace", "dev", IFB,
              "root", "tbf", "rate", rate, "burst", "64kb", "latency", "100ms")

    if not ingress_present(pid):
        namespace(pid, "tc", "qdisc", "add", "dev", ETH, "handle", "ffff:", "ingress")

    existing_filters = namespace(pid, "tc", "filter", "show", "dev", ETH, "ingress")
    if existing_filters:
        # `tc filter replace ... matchall` without an explicit handle fails
        # with EEXIST on subsequent calls. Keep the existing filter if it
        # already redirects to our IFB, otherwise refuse to alter other rules.
        if "matchall" not in existing_filters or (f"dev {IFB}" not in existing_filters and f"to device {IFB}" not in existing_filters):
            raise RuntimeError(
                "Existing ingress filter is not the expected Bitcoin IFB redirect. "
                "Refusing to change someone else's traffic policy."
            )
        print("Existing Bitcoin ingress redirect retained.")
    else:
        namespace(pid, "tc", "filter", "add", "dev", ETH,
                  "parent", "ffff:", "protocol", "all", "pref", "49152",
                  "matchall", "action", "mirred", "egress", "redirect", "dev", IFB)

    print(f"Applied: upload <= {rate}, download <= {rate} (per direction).")
    show(pid)


def remove(pid):
    if not has_ifb(pid):
        raise RuntimeError(
            f"{IFB} not found; refusing to delete potentially unrelated tc rules."
        )
    # Only use this on a container configured by this tool.
    namespace(pid, "tc", "qdisc", "del", "dev", ETH, "ingress", check=False)
    namespace(pid, "tc", "qdisc", "del", "dev", ETH, "root", check=False)
    namespace(pid, "ip", "link", "del", IFB)
    print("Removed bandwidth limits from this container.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["apply", "status", "remove"])
    parser.add_argument("--container", default="bitcoin",
                        help="Docker container name (default: bitcoin)")
    parser.add_argument("--mbit", type=float, default=5.0,
                        help="Mbps in each direction (default: 5)")
    args = parser.parse_args()

    if os.geteuid() != 0:
        parser.error("Run with sudo/root")
    for program in ("docker", "nsenter", "tc", "ip"):
        if not shutil.which(program):
            parser.error(f"Missing '{program}'; install iproute2/util-linux as needed")
    try:
        pid = info(args.container)
        if args.action == "apply":
            apply(pid, args.mbit)
        elif args.action == "remove":
            remove(pid)
        else:
            show(pid)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
