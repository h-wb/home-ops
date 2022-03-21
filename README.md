# Troubleshoot:

upgrade retries exhaust :
- flux delete hr -n NAMESPACE HRNAME
- flux reconcile kustomization apps


# TO DO :

- Terraform to create ubuntu VM on proxmox with ssh key/no passwd connection
- Terraform to handle OVH DNS and cert-manag configuration (instead of Cloudfare config)
- Add command to install prerequisites
- Update readme
