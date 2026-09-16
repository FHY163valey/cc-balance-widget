# Security

This utility reads a local CC Switch database and executes saved JavaScript usage
scripts. Use only scripts you trust. Node's VM context is not a malicious-code
sandbox; timeouts, output limits, and URL checks are reliability boundaries,
not a guarantee of containment.

The supported request contract is same-origin HTTPS GET without redirects.
Requests carry the selected provider's credentials. No additional telemetry is
implemented. The database is opened read-only, not migrated or repaired.

Credentials are passed to the runner via stdin, never process arguments. Error
messages exposed by the runner are fixed codes, not raw HTTP bodies or scripts.
Settings/cache contain local paths, provider IDs, last-success times and amounts.
They are local plaintext and should be treated as personal data.

Do not publish credentials, databases or credential-bearing script excerpts in
issues. For a suspected vulnerability, use GitHub private vulnerability reporting
if enabled; otherwise contact the maintainer privately before sharing details.
Rotate any accidentally exposed key with its supplier.

No administrator privilege, UIAccess signing or security-desktop bypass is used.
The preview candidate is not an audited security product.
