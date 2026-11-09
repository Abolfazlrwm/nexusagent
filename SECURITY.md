# Security Policy

## Supported versions

NexusAgent is a young project. Only the latest published release receives
security fixes.

| Version | Supported |
| ------- | --------- |
| 0.4.x   | ✅        |
| < 0.4   | ❌        |

## Reporting a vulnerability

Please **do not report security issues through public GitHub issues**.

Use GitHub's private vulnerability reporting for this repository:

1. Go to the **Security** tab of https://github.com/Abolfazlrwm/nexusagent
2. Select **Report a vulnerability**
3. Describe the issue, how to reproduce it, and its impact

You will get a response as soon as possible — typically within a few days.
If the report is accepted, a fix will be developed privately and released
with a coordinated disclosure, and you will be credited (unless you prefer
otherwise).

## Scope notes

NexusAgent is a runtime library: it executes the Providers and Tools you
give it. When integrating it, keep the following in mind:

- `NEXUS_API_KEY` (or `Settings.api_key`) is sent as a Bearer token to the
  configured HTTP endpoint. It is never logged, and `Settings`/`ProviderConfig`
  `repr()`s deliberately mask it.
- The built-in `http` provider performs network requests only when it
  actually runs. Treat the configured endpoint as trusted input, and use
  HTTPS endpoints in production.
- Tools run arbitrary Python code by definition. Only register tools from
  code you trust.
