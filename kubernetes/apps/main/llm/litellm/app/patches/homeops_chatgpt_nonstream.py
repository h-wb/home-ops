"""Workaround for BerriAI/litellm#37039: chatgpt/* non-streaming requests fail with
"Unknown items in responses API response: []".

The ChatGPT (Codex) backend only streams, and its final `response.completed` event
carries an empty `output`; the content lives in the `output_item.done` /
`output_text.done` events before it. LiteLLM's Responses->Chat bridge drains the
stream for a non-streaming caller but reads only that final event.

This wraps the stream the bridge drains, records those events with LiteLLM's own
recovery helpers, and backfills `output` only when the final response has none.
Streaming requests never reach this code. Loaded as a proxy callback
(`litellm_settings.callbacks`), which is just the hook that gets it imported.

Needed by karakeep, the one consumer that calls a chatgpt/* model without streaming.
Jory's setup has no such patch because everything he points at ChatGPT streams.

Fail-safe: if LiteLLM's internals have moved, it logs once and changes nothing (and
karakeep's tagging then fails until this is fixed). Delete this file and its callback
entry once the upstream fix ships.
"""

import logging

from litellm.integrations.custom_logger import CustomLogger

log = logging.getLogger("LiteLLM Proxy")

_ITEM_DONE = "response.output_item.done"
_TEXT_DONE = "response.output_text.done"


def _as_dict(obj):
    if isinstance(obj, dict):
        return obj
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        try:
            return dump(exclude_none=True)
        except Exception:
            return None
    return None


def _event_type(event):
    value = event.get("type") if isinstance(event, dict) else getattr(event, "type", None)
    return str(getattr(value, "value", value))


def _install():
    from litellm.completion_extras.litellm_responses_transformation import handler
    from litellm.responses.sse_output_recovery import record_output_item_chunk, record_output_text_chunk
    from litellm.types.llms.openai import ResponsesAPIResponse

    bridge = handler.ResponsesToCompletionBridgeHandler
    if getattr(bridge, "_homeops_nonstream_patch", False):
        return

    class Recorder:
        """Iterates like the wrapped stream while keeping its output items."""

        def __init__(self, inner):
            self._inner = inner
            self._iter = None
            self._items = {}
            self._text_items = {}
            self._backfilled = False

        def _record(self, event):
            try:
                kind = _event_type(event)
                if kind not in (_ITEM_DONE, _TEXT_DONE):
                    return
                chunk = _as_dict(event)
                if chunk is None:
                    return
                if kind == _ITEM_DONE:
                    record_output_item_chunk(parsed_chunk=chunk, output_items=self._items)
                else:
                    record_output_text_chunk(
                        parsed_chunk=chunk, output_items=self._items, text_only_items=self._text_items
                    )
            except Exception:  # never let bookkeeping break a request
                log.debug("homeops chatgpt patch: could not record a stream event", exc_info=True)

        def __iter__(self):
            self._iter = iter(self._inner)
            return self

        def __next__(self):
            event = next(self._iter)
            self._record(event)
            return event

        def __aiter__(self):
            self._iter = self._inner.__aiter__()
            return self

        async def __anext__(self):
            event = await self._iter.__anext__()
            self._record(event)
            return event

        @property
        def completed_response(self):
            completed = getattr(self._inner, "completed_response", None)
            if completed is None or self._backfilled:
                return completed
            self._backfilled = True
            try:
                response = getattr(completed, "response", None)
                if response is None or getattr(response, "output", None):
                    return completed
                merged = {**self._text_items, **self._items}
                if not merged:
                    return completed
                payload = _as_dict(response) or {}
                payload["output"] = [item for _, item in sorted(merged.items())]
                try:
                    rebuilt = ResponsesAPIResponse(**payload)
                except Exception:
                    rebuilt = ResponsesAPIResponse.model_construct(**payload)
                try:
                    completed.response = rebuilt
                except Exception:
                    object.__setattr__(completed, "response", rebuilt)
            except Exception:
                log.warning("homeops chatgpt patch: backfill failed, passing the response through", exc_info=True)
            return completed

        def __getattr__(self, name):
            return getattr(self._inner, name)

    original_sync = bridge._collect_response_from_stream
    original_async = bridge._collect_response_from_stream_async

    def collect_sync(self, stream_iter):
        return original_sync(self, Recorder(stream_iter))

    async def collect_async(self, stream_iter):
        return await original_async(self, Recorder(stream_iter))

    bridge._collect_response_from_stream = collect_sync
    bridge._collect_response_from_stream_async = collect_async
    bridge._homeops_nonstream_patch = True
    log.info("homeops chatgpt patch: non-streaming backfill installed (BerriAI/litellm#37039)")


try:
    _install()
except Exception:
    log.warning("homeops chatgpt patch: LiteLLM internals changed, patch NOT applied", exc_info=True)


class _Hook(CustomLogger):
    """No-op callback: importing this module is the point."""


patch_instance = _Hook()
