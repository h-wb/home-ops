#!/bin/bash
# `sshd` sidecar, from david-driscoll/home-operations. The image ships only
# openssh-client and the pod runs as 1000, so this downloads bookworm's server .debs
# into private apt state, unpacks them onto an emptyDir and runs that sshd
# unprivileged. It can only ever log in `paseo`, the only user here anyway.
#
# Never exit while the download fails: a crashlooping sidecar takes the whole pod out
# of Ready, and the web UI with it.
set -euo pipefail

ROOT=/opt/sshd/root
STATE=/opt/sshd/state
PORT=2222
SSH_DIR=/home/paseo/.ssh
HOST_KEY=$SSH_DIR/paseo_sshd_ed25519_key
AUTHORIZED_KEYS=/etc/paseo/authorized_keys
LIB=$ROOT/lib/x86_64-linux-gnu:$ROOT/usr/lib/x86_64-linux-gnu
INSTALLED=/opt/sshd/installed

# openssh-server's runtime libs the image lacks.
PACKAGES=(openssh-server openssh-sftp-server libwrap0 libnsl2 libtirpc3)

apt_private() {
  apt-get \
    -o Dir::State::Lists="$STATE/lists" \
    -o Dir::Cache="$STATE/cache" \
    -o Debug::NoLocking=1 \
    -o APT::Sandbox::User="$(id -un)" \
    "$@"
}

# errexit does not apply inside a function used as an `until` condition.
install_sshd() {
  rm -rf "$ROOT" "$STATE" "$INSTALLED"
  mkdir -p "$ROOT" "$STATE/lists/partial" "$STATE/cache/archives/partial" "$STATE/debs" || return 1
  apt_private -qq update || return 1
  # Same source upload as the image's client, so it links against the libs it carries.
  local version deb
  version=$(dpkg-query -W -f='${Version}' openssh-client) || return 1
  cd "$STATE/debs" || return 1
  if ! apt_private -qq download "openssh-server=$version" "openssh-sftp-server=$version"; then
    echo "sshd: openssh-server $version is gone from the archive; taking the newest" >&2
    apt_private -qq download openssh-server openssh-sftp-server || return 1
  fi
  apt_private -qq download "${PACKAGES[@]:2}" || return 1
  for deb in *.deb; do dpkg-deb -x "$deb" "$ROOT" || return 1; done
  cd / || return 1
  [[ -x $ROOT/usr/sbin/sshd && -x $ROOT/usr/lib/openssh/sftp-server ]] || return 1
  if LD_LIBRARY_PATH=$LIB ldd "$ROOT/usr/sbin/sshd" "$ROOT/usr/lib/openssh/sftp-server" | grep 'not found'; then
    echo "sshd: unresolved libraries above; add their packages to PACKAGES" >&2
    return 1
  fi
  touch "$INSTALLED"
}

until [[ -f $INSTALLED ]] || install_sshd; do
  echo "sshd: install failed, retrying in 60s" >&2
  sleep 60
done

# Host key on the home volume so clients keep trusting it across restarts. chmod every
# start: the fsGroup pass can add group bits, and sshd refuses a readable host key.
mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"
[[ -f $HOST_KEY ]] || ssh-keygen -q -t ed25519 -N "" -C "paseo-sshd" -f "$HOST_KEY"
chmod 600 "$HOST_KEY"

# sshd scrubs the environment; hand sessions the container's own. KUBERNETES_SERVICE_*
# is what in-cluster kubectl needs alongside the mounted service account token.
env | grep -E '^(HOME|PATH|TZ|GH_TOKEN|GIT_EMAIL|LITELLM_API_KEY|KUBERNETES_SERVICE_(HOST|PORT))=' \
  > "$SSH_DIR/environment"
chmod 600 "$SSH_DIR/environment"

cat > /opt/sshd/sshd_config <<EOF
Port $PORT
HostKey $HOST_KEY
PidFile none
AllowUsers paseo
AuthorizedKeysFile $AUTHORIZED_KEYS
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PermitUserEnvironment yes
AllowTcpForwarding local
X11Forwarding no
ClientAliveInterval 30
Subsystem sftp $ROOT/usr/lib/openssh/sftp-server
EOF

export LD_LIBRARY_PATH=$LIB
# sshd re-execs itself, so it must be started by absolute path.
exec "$ROOT/usr/sbin/sshd" -D -e -f /opt/sshd/sshd_config
