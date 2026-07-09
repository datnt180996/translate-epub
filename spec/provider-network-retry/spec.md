# Provider Network Retry

## Purpose

Translation API calls can fail because the upstream provider or network closes
the connection before sending a response. A real example is:

`Server disconnected without sending a response.`

This is usually temporary, so the app should retry before marking the chapter
as failed.

## Behavior

- Provider calls still use `TRANSLATION_MAX_RETRIES`.
- Retry already covered provider finish-reason errors, timeouts, and selected
  HTTP status errors.
- Retry now also covers `httpx.TransportError`, including remote disconnects,
  connect/read/write errors, and protocol-level network failures.
- If every retry fails, the original error is still surfaced and the chapter is
  marked `error` as before.

## Related Files

- `app/services/providers/minimax.py`
- `tests/test_translation_quality.py`

## Limitations

- This does not guarantee success if the provider keeps disconnecting.
- If a disconnect happens repeatedly after all retries are exhausted, the user
  still needs to retry the chapter later or switch provider/model.

## Verification

- `tests/test_translation_quality.py` includes a fake provider client that
  raises `RemoteProtocolError` once, then succeeds on retry.
