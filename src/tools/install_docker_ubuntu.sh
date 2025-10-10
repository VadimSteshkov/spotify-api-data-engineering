#!/usr/bin/env bash
# install_docker_ubuntu.sh
# Installs official Docker Engine on Ubuntu 22.04/24.04. Idempotent.

#chmod +x install_docker_ubuntu.sh
#sudo ./install_docker_ubuntu.sh
#newgrp docker


set -euo pipefail

RED=$(printf '\033[31m'); YLW=$(printf '\033[33m'); GRN=$(printf '\033[32m'); NC=$(printf '\033[0m')
need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "${RED}Missing $1${NC}"; exit 1; }; }

echo "${YLW}==> Checking OS...${NC}"
. /etc/os-release || { echo "${RED}No /etc/os-release; unsupported OS.${NC}"; exit 1; }
[ "${ID:-}" = "ubuntu" ] || { echo "${RED}This script supports Ubuntu only.${NC}"; exit 1; }

echo "${YLW}==> Ensure root/sudo...${NC}"
[ "$EUID" -eq 0 ] || { echo "${RED}Run as root: sudo bash $0${NC}"; exit 1; }

echo "${YLW}==> Removing conflicting packages (if any)...${NC}"
apt-get remove -y docker-desktop docker.io docker-doc docker-compose docker-compose-v2 containerd runc || true
apt-get purge  -y docker-desktop || true
rm -rf /var/lib/docker /var/lib/containerd || true

echo "${YLW}==> Prerequisites...${NC}"
apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release

echo "${YLW}==> Add Docker’s official GPG key & repo...${NC}"
install -m 0755 -d /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
fi

ARCH="$(dpkg --print-architecture)"
CODENAME="$(lsb_release -cs)"
REPO_LINE="deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${CODENAME} stable"
echo "${REPO_LINE}" > /etc/apt/sources.list.d/docker.list

apt-get update -y

echo "${YLW}==> Install Docker Engine + Buildx + Compose plugin...${NC}"
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "${YLW}==> Enable & start service...${NC}"
systemctl enable docker
systemctl restart docker

echo "${YLW}==> Verify...${NC}"
need_cmd docker
docker --version || true
docker compose version || true

# optional: hello-world
if docker run --rm hello-world >/dev/null 2>&1; then
  echo "${GRN}hello-world: OK${NC}"
else
  echo "${YLW}Skipping hello-world (no network or blocked).${NC}"
fi

# add invoking user to docker group
if [ -n "${SUDO_USER:-}" ] && id "${SUDO_USER}" >/dev/null 2>&1; then
  usermod -aG docker "${SUDO_USER}" || true
  echo "${GRN}User ${SUDO_USER} added to 'docker' group.${NC}"
  echo "${YLW}Re-login or run: newgrp docker${NC}"
fi

echo "${GRN} Docker Engine installed successfully.${NC}"

