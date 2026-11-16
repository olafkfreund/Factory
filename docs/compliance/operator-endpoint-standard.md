# Operator Endpoint Standard

- **Policy owner:** Security Owner (CISO function) — see [roles.md](roles.md)
- **Review cadence:** Annually, and when a host is added or replaced
- **Frameworks:** ISO/IEC 27001:2022 A.8.1 (user endpoint devices), A.7.7 (clear desk and
  clear screen), A.7.9 (assets off premises); SOC 2 CC6.4, CC6.7; NYDFS 500.7
  (conditional, see [nydfs-part500-mapping.md](nydfs-part500-mapping.md))
- **Issue:** Factory#3696

Operator laptops hold the agenix decrypting identity and GitHub credentials, so they are
in the ISMS scope. This standard sets the requirements. It does not state that any host
meets them: the evidence column says how each is proven, and the attestation at the end
is filled in per host by the Security Owner. A.8.1, A.7.7 and A.7.9 stay Planned until
the standard and the evidence for each host exist.

## Scope

Every machine a person uses to administer the fleet, push to its repositories, or
hold its credentials, including laptops and the workstation that runs the cluster.

## Requirements

| # | Requirement | Evidence the owner attaches |
|---|---|---|
| E1 | Full-disk encryption on every internal disk that holds key material or repository checkouts | `lsblk -o NAME,TYPE,FSTYPE,MOUNTPOINT` showing a crypt layer; for NixOS hosts the file and option that sets it (for example `boot.initrd.luks.devices` in the host configuration) |
| E2 | Automatic screen lock after at most 10 minutes idle, and a lock on lid close or suspend | The NixOS or desktop configuration that sets the idle timeout and lock, or a screenshot of the setting |
| E3 | Operating system and packages patched: security updates applied within the [remediation SLA](remediation-sla.md) windows, and no end-of-life OS | Lock file or generation age, update configuration, or `uname -r` and release date |
| E4 | Key material lives only in approved places: the agenix identity in the user's protected key file (mode 0600), GitHub credentials in a credential helper or agent, never in a shared drive, chat or an unencrypted backup | Path check and the configuration that places it; a statement that none are elsewhere |
| E5 | GitHub account uses MFA (security key or TOTP) and commits to the fleet are signed ([signed-commits-and-sod.md](signed-commits-and-sod.md)) | Screenshot of the GitHub setting, or `git log --show-signature` on a recent commit |
| E6 | No other person has an unlocked session on the device; separate OS account per person | Account list |
| E7 | Loss or theft: report within the incident-response timelines, rotate the agenix identity and revoke GitHub tokens ([encryption-key-mgmt.md](policies/encryption-key-mgmt.md), [incident-response.md](policies/incident-response.md)) | Procedure cited, no evidence needed until an event |
| E8 | Clear desk and clear screen: no credentials or decrypted secrets on paper or left on screen when away | Operator acknowledgement on the attestation |

Where the NixOS configuration sets a requirement, the configuration is the evidence:
cite the repository, file, option and commit, not a screenshot.

## Per-host attestation

> TEMPLATE: not a record. One per host per review. Leave every field empty until the
> check has been performed; attach the evidence for each requirement.

| Field | Value |
|---|---|
| Host name and owner | |
| Date checked | |
| E1 evidence | |
| E2 evidence | |
| E3 evidence | |
| E4 evidence | |
| E5 evidence | |
| E6 evidence | |
| E7 acknowledged | |
| E8 acknowledged | |
| Exceptions and compensating controls | |
| Checked by | |
| Signature | |
