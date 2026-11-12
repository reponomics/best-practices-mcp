# Third-party notices and provenance

Best Practices MCP is an independent project maintained by Reponomics. It is not affiliated with, sponsored by, endorsed by, or an official project of OpenSSF, the Linux Foundation, or the OpenSSF Best Practices Badge (BadgeApp) project or its contributors. References and retained notices identify compatibility and provenance, not endorsement.

## OpenSSF Best Practices Badge (BadgeApp)

The packaged criteria catalog and retained upstream source materials derive from [ossf/best-practices-badge](https://github.com/ossf/best-practices-badge), revision `868e1677339a3fdb48851b0c2ae8862c553115eb`, under the MIT license. The original notice identifies:

> Copyright (c) 2015-2016 The Linux Foundation, the Institute for Defense Analyses, and other project contributors.

The complete upstream license is retained in `src/best_practices_mcp/data/BADGEAPP-LICENSE.txt`, in the installed package as `best_practices_mcp/data/BADGEAPP-LICENSE.txt`, and alongside each vendored source snapshot. The packaged provenance manifest records source inputs and hashes. Synthetic HTML test controls retain a concise record of the upstream source paths consulted during derivation. Copied Ruby implementation files and Rails templates are not included.

## Live project-entry data

Public BadgeApp project records supply their own attribution and license metadata. The MCP preserves these values in observation metadata. The license for this project's original code does not replace the license or attribution of those records or reproduced project-entry content. Historical upstream naming in an attribution field is preserved as supplied.

## Contributor Covenant

`CODE_OF_CONDUCT.md` adapts [Contributor Covenant 3.0](https://www.contributor-covenant.org/version/3/0/), stewarded by the Organization for Ethical Source and licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). It specifies this project's reporting contact and maintainers, adopts the suggested enforcement ladder, and uses Community Moderators consistently. The adapted code of conduct remains under CC BY-SA 4.0; the MIT license for original project code does not replace those terms.

## Dependencies

Python and development-only Node dependencies are installed separately under their respective licenses; their code is not vendored into this distribution. The dependency manifests identify direct requirements and the development lockfiles record resolved versions. Retain the notices accompanying those separately installed packages when redistributing them.
