#!/bin/sh
# `sshd` sidecar: sshd-lite, installed on the PVC by the dotfiles `paseo` class, run as
# the pod's own user. Sessions inherit this container's env (PATH, GH_TOKEN, the
# service account's KUBERNETES_SERVICE_*), so there is nothing to hand over.
set -eu

key="${HOME}/.ssh/paseo_sshd_ed25519_key"
mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"
# On the PVC, so clients keep trusting the host across restarts.
[ -f "$key" ] || ssh-keygen -q -t ed25519 -N "" -C paseo-sshd -f "$key"

# Wait rather than exit: a crashlooping sidecar takes the pod, and the web UI with
# it, out of Ready.
until command -v sshd-lite >/dev/null 2>&1; do
	echo "sshd: sshd-lite not installed (dotfiles paseo class); retrying in 60s" >&2
	sleep 60
done

exec sshd-lite --port 2222 --keyfile "$key" --workdir "$HOME" --keepalive 30 \
	--sftp --tcp-forwarding --mosh /etc/paseo/authorized_keys
