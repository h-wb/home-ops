<div align="center">

<img src="https://raw.githubusercontent.com/h-wb/home-ops/main/docs/src/assets/icons/logo.png" align="center" width="144px" height="144px"/>


### My Homelab Repository

_... automated via [Flux](https://fluxcd.io), [Renovate](https://github.com/renovatebot/renovate) and [GitHub Actions](https://github.com/features/actions)_ 🤖

</div>

---

## Overview

This is a monorepository for my home Kubernets clusters. I try to adhere to Infrastructure as Code (IaC) and Gitops practices using tools like [Ansible](https://www.ansible.com/), [Kubernetes](https://kubernetes.io/), [Flux](https://github.com/fluxcd/flux2), [Renovate](https://github.com/renovatebot/renovate), and [GitHub Actions](https://github.com/features/actions).

This was built with the purpose of learning Kubernetes and Gitops while serving my various self-hosted applications.

---

## Kubernetes

There is a template over at [onedr0p/cluster-template](https://github.com/onedr0p/cluster-template) if you want to try and follow along with some of the practices I use here.

I would recommend looking at [onedr0p/home-ops](https://github.com/onedr0p/home-ops) or [joryirving/home-ops](https://github.com/joryirving/home-ops) for more polished repositories.

You could find this one useful if you're looking for informations about:
- Longhorn
- OVH (*archived*)
- Bitwarden (CLI)

### Installation

My Kubernetes cluster is deployed with [Talos](https://www.talos.dev). This is a semi-hyper-converged cluster - workloads and block storage are sharing the same available resources on my nodes while I have a separate [TrueNAS SCALE](https://www.truenas.com/truenas-scale/) server with ZFS for NFS/SMB shares, bulk file storage and backups.

### Core components

- [actions-runner-controller](https://github.com/actions/actions-runner-controller): Self-hosted Github runners.
- [cert-manager](https://github.com/cert-manager/cert-manager): Creates SSL certificates for services in my cluster.
- [cilium](https://github.com/cilium/cilium): Internal Kubernetes container networking interface.
- [cloudflared](https://github.com/cloudflare/cloudflared): Enables Cloudflare secure access to certain ingresses.
- [external-dns](https://github.com/kubernetes-sigs/external-dns): Automatically syncs ingress DNS records to a DNS provider.
- [external-secrets](https://github.com/external-secrets/external-secrets/): Managed Kubernetes secrets using [Bitwarden](https://bitwarden.com/).
- [ingress-nginx](https://github.com/kubernetes/ingress-nginx): Kubernetes ingress controller using NGINX as a reverse proxy and load balancer.
- [longhorn](https://github.com/longhorn/longhorn): Distributed block storage for peristent storage.
- [sops](https://github.com/getsops/sops): Managed secrets for Kubernetes and Terraform which are commited to Git.
- [volsync](https://github.com/backube/volsync): Backup and recovery of persistent volume claims.

### GitOps

[Flux](https://github.com/fluxcd/flux2) watches the clusters in my [kubernetes](./kubernetes/) folder (see Directories below) and makes the changes to my clusters based on the state of my Git repository.

The way Flux works for me here is it will recursively search the `kubernetes/${cluster}/apps` folder until it finds the most top level `kustomization.yaml` per directory and then apply all the resources listed in it. That `kustomization.yaml` will generally only have a namespace resource and one or many Flux kustomizations (`ks.yaml`). Under the control of those Flux kustomizations there will be a `HelmRelease` or other resources related to the application which will be applied.

[Renovate](https://github.com/renovatebot/renovate) watches my **entire** repository throught the rules defined in `.github/renovate` looking for dependency updates. When they are found a PR is automatically created. When some PRs are merged Flux applies the changes to my cluster.

### Directories

This Git repository contains the following directories under [Kubernetes](./kubernetes/).

```sh
📁 kubernetes
├── 📁 main               # main cluster (based in France)
│   ├── 📁 apps           # applications
│   ├── 📁 bootstrap      # bootstrap procedures
│   ├── 📁 flux            # core flux configuration
│   └── 📁 templates      # re-useable components
└── 📁 dev                # dev cluster (based in Canada)
    ├── 📁 apps           # applications
    ├── 📁 bootstrap      # bootstrap procedures
    ├── 📁 flux            # core flux configuration
    └── 📁 templates      # re-useable components
```

---

## Cloud Dependencies

While most of my infrastructure and workloads are self-hosted I do rely upon the cloud for certain key parts of my setup. This saves me from having to worry about two things. (1) Dealing with chicken/egg scenarios and (2) services I critically need whether my cluster is online or not.

The alternative solution to these two problems would be to host a Kubernetes cluster in the cloud and deploy applications like [HCVault](https://www.vaultproject.io/), [Vaultwarden](https://github.com/dani-garcia/vaultwarden), [ntfy](https://ntfy.sh/), and [Gatus](https://gatus.io/). However, maintaining another cluster and monitoring another group of workloads is a lot more time and effort than I am willing to put in.

| Service                                     | Use                                                               | Cost           |
|---------------------------------------------|-------------------------------------------------------------------|----------------|
| [Bitwarden](https://bitwarden.com/)         | Secrets with [External Secrets](https://external-secrets.io/)     | Free        |
| [OVH](https://www.ovhcloud.com)             | Domain registrar                                                  | 3.58€/yr        |
| [Cloudflare](https://www.cloudflare.com/)     | Domain and Tunnels                                                | Free       |
| [GitHub](https://github.com/)               | Hosting this repository and continuous integration/deployments    | Free           |
|                                             |                                                                   | Total: 3.58€/yr |

---

## DNS

### Home DNS

[k8s_gateway](https://github.com/ori-edge/k8s_gateway) acts as a single external DNS interface into the cluster to any Kubernetes resources. A home DNS server can be configured to forward DNS queries from a domain to the gateay but as i'm connecting to my clusters remotelym i'm just adding the `k8s_gateway` address as DNS server to my VPN configuration.

### Public DNS

[external-dns](https://github.com/kubernetes-sigs/external-dns) is deployed in my cluster and configured to sync DNS records to [Cloudflare](https://www.cloudflare.com/). The only ingress this `external-dns` instance looks at to gather DNS records to put in `Cloudflare` are ones that have an ingress class name of `external` and contain an ingress annotation `external-dns.alpha.kubernetes.io/target`.

---

## 🔧 Hardware

### Main Kubernetes Cluster

| Name  | Device         | CPU       | OS Disk   | Data Disk | RAM  | OS    | Purpose           |
|-------|----------------|-----------|-----------|-----------|------|-------|-------------------|
| k8s-1 | Intel NUC13ANHI7   | i7-1360P | 128GB SSD | 500GB NVME  | 64GB | Talos | Kubernetes Control-plane |
| k8s-2 | Intel NUC12WSHI7   | i7-1260P | 128GB SSD | 500GB NVME  | 64GB | Talos | Kubernetes Control-plane |
| k8s-3 | Intel NUC12WSHI7   | i7-1260P | 128GB SSD | 500GB NVME  | 64GB | Talos | Kubernetes Control-plane |

### Dev Kubernetes Cluster

| Name  | Device         | CPU       | OS Disk   | Data Disk | RAM  | OS    | Purpose           |
|-------|----------------|-----------|-----------|-----------|------|-------|-------------------|
| hyperv-1 | Gaming PC   | Ryzen 3600X | 2TB NVME | -  | 64GB | Hyper-V | Kubernetes Control-plane |

### Supporting Hardware

| Name   | Device         | CPU           | OS Disk    | Data Disk  | RAM   | OS           | Purpose        |
|--------|----------------|---------------|------------|------------|-------|--------------|----------------|
| NAS    | Supermicro 4U        | **?**     | **?**   | 60B | 32GB | TrueNAS Scale       | NAS/NFS/Backup |
| PiKVM  | Raspberry Pi4  | Cortex A72    | 64GB mSD   | -          | 4GB   | PiKVM (Arch) | KVM            |

---

## 🤝 Thanks

A big thanks to [onedr0p](https://github.com/onedr0p) and his [cluster-template](https://github.com/onedr0p/cluster-template), [joryirving](https://github.com/joryirving), and the whole [Home Operations](https://discord.gg/home-operations) Discord community to have helped me build this repository.


## 📜 Changelog

See my _awful_ [commit history](https://github.com/h-wb/home-ops/commits/main)

---

## 🔏 License

See [LICENSE](./LICENSE)