# Ops Notes

## WeChat account constraint: MQ AGI实验室

As of 2026-04-28, the current public account used for integration testing has these backend properties:

- account name: `MQ AGI实验室`
- account type: `公众号`
- subject type: `个人`
- WeChat certification status: `未认证`

Observed backend facts:

- In `账号设置 -> 账号详情`, the backend shows `认证情况 -> 未认证`.
- The `申请微信认证` page shows `微信认证 -> 无法开通`.
- The same account has a separate `个人认证` entry with `视频号快速认证` and `手动认证`, but that is not the same as full WeChat certification for official account API capability.

Practical API result on this account:

- `stable_token`: works after `AppSecret` is enabled and API IP whitelist is configured.
- `draft/add`: works.
- `message/mass/preview`: fails with `48001 api unauthorized`.

Current operating policy for this account:

- Supported workflow:
  - local HTML preview
  - cover upload
  - draft creation
  - manual review and manual publish in mp backend
- Do not assume these are available:
  - phone preview via `message/mass/preview`
  - full automated publish via privileged publish APIs

If full automated preview/publish is required, switch to an eligible account with the needed platform capability rather than continuing to optimize around this personal account.
